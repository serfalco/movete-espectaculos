"""MoVeTe — Newsletter semanal automático.

Arma el aviso de la semana desde eventos.json (misma lógica que la edición) y
lo envía por la API de Buttondown. Pensado para correr en el workflow semanal,
después de generar el sitio. NO requiere intervención manual.

Uso:
    python generar_newsletter.py --eventos eventos.json          # arma y ENVÍA
    python generar_newsletter.py --eventos eventos.json --dry-run # solo imprime

La API key se lee de la variable de entorno BUTTONDOWN_API_KEY (en el workflow
viene del secret del repo). El estado del envío se controla con NEWSLETTER_STATUS
(por defecto 'about_to_send' = envía; poné 'draft' para dejarlo como borrador y
revisarlo en Buttondown antes de mandarlo).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date

from edicion import jueves_de_edicion, en_esta_semana, etiqueta_rango, MESES_ABR
from generar_edicion import (
    cargar_eventos,
    normalizar_categorias,
    parse_fecha,
    cat_label,
    evento_titulo,
    evento_lugar,
    elegir_destacado_under,
)
from venues import venue_canonico, venue_masivo

BASE = "https://movete.info"
API = "https://api.buttondown.com/v1/emails"


def eventos_de_la_semana(eventos: list[dict], jueves: date) -> list[dict]:
    evs = [
        e for e in normalizar_categorias(eventos)
        if e.get("categoria") != "cine" and e.get("fecha")
        and en_esta_semana(e["fecha"], jueves)
    ]
    evs.sort(key=lambda e: e.get("fecha", ""))
    return evs


DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# Rubros del mail, en orden: (categorias que entran, titulo, cuantos).
RUBROS = [
    (("teatro", "impro"), "🎭 Teatro", 4),
    (("musica",), "🎵 Música", 4),
    (("stand-up", "humor"), "😂 Stand up", 3),
    (("danza", "infantil"), "💃 Danza e infantil", 2),
]
TITULOS_VACIOS = {"sin datos", "sin titulo", "sin título", "evento"}
FUENTES_CON_ENTRADAS = ("livepass", "passline", "plateauno", "eventbrite")


def _puntaje(ev: dict) -> int:
    """Que tan 'para recomendar' es un evento. Sala grande, entradas a la
    venta, fin de semana e imagen suman; no es un ranking editorial, solo
    evita que el mail se llene con lo primero que cae en la semana."""
    p = 0
    if venue_masivo(evento_lugar(ev)):
        p += 3
    if ev.get("fuente") in FUENTES_CON_ENTRADAS:
        p += 2
    if ev.get("imagen"):
        p += 1
    if parse_fecha(ev["fecha"]).weekday() in (4, 5, 6):  # vie, sab, dom
        p += 2
    return p


def _elegir(candidatos: list[dict], n: int) -> list[dict]:
    """Los n mejores, sin repetir titulo ni sala y repartidos entre dias.

    Una sola funcion por sala en cada rubro: sin eso un teatro grande con
    mucha programacion (o el mismo show cargado con dos titulos) ocupa todo.
    """
    elegidos: list[dict] = []
    titulos: set[str] = set()
    salas: set[str] = set()
    por_dia: dict[str, int] = {}
    # Titulos de relleno que algunas fuentes publican cuando no tienen nombre.
    candidatos = [e for e in candidatos
                  if evento_titulo(e).strip().casefold() not in TITULOS_VACIOS]
    pool = sorted(candidatos, key=lambda e: (-_puntaje(e), e["fecha"]))
    while pool and len(elegidos) < n:
        mejor = max(
            pool,
            key=lambda e: _puntaje(e) - 2 * por_dia.get(e["fecha"][:10], 0),
        )
        pool.remove(mejor)
        t = evento_titulo(mejor).casefold().strip()
        vc = venue_canonico(evento_lugar(mejor))
        sala = vc["slug"] if vc else evento_lugar(mejor).casefold().strip()
        if t in titulos or sala in salas:
            continue
        titulos.add(t)
        salas.add(sala)
        por_dia[mejor["fecha"][:10]] = por_dia.get(mejor["fecha"][:10], 0) + 1
        elegidos.append(mejor)
    return sorted(elegidos, key=lambda e: e["fecha"])


def _linea_evento(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    cuando = f"{DIAS_CORTOS[f.weekday()]} {f.day}"
    return f"- {cuando} · **{evento_titulo(ev)}** — {evento_lugar(ev)}"


def armar_email(eventos: list[dict], jueves: date) -> tuple[str, str]:
    rango = etiqueta_rango(jueves)
    semana = eventos_de_la_semana(eventos, jueves)
    destacado = elegir_destacado_under(
        [e for e in normalizar_categorias(eventos) if e.get("fecha")], jueves
    )

    subject = f"MoVeTe · Qué hacer en La Plata · semana {rango}"

    partes = [f"**Semana {rango}** · lo que no te podés perder, por rubro.\n"]

    if destacado:
        f = parse_fecha(destacado["fecha"])
        partes.append(
            f"⭐ **No te lo pierdas:** {evento_titulo(destacado)} — "
            f"{evento_lugar(destacado)} · {DIAS_CORTOS[f.weekday()]} {f.day}\n"
        )

    for cats, titulo, n in RUBROS:
        elegidos = _elegir([e for e in semana if e.get("categoria") in cats], n)
        if elegidos:
            partes.append(f"**{titulo}**")
            partes.append("\n".join(_linea_evento(e) for e in elegidos))
            partes.append("")

    partes.append(
        f"👉 Todo lo demás: [En vivo]({BASE}/en-vivo/) · [Cine]({BASE}/cine/) · "
        f"[Grandes shows]({BASE}/en-vivo/lo-que-se-viene/)"
    )
    partes.append(f"\n_Porque la cultura es encontrarnos._ · [MoVeTe]({BASE})")

    return subject, "\n".join(partes)


def _alertar(msg: str) -> None:
    """Deja el error en _alerta.txt: el último paso del workflow lo lee y pone
    la corrida en rojo, que es lo que hace que GitHub mande un mail. Un
    ::warning:: solo queda enterrado en Actions (así se perdió el envío del
    17/09/2026 sin que nadie se enterara)."""
    print(f"::warning::{msg}")
    ws = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if not ws:
        return
    try:
        with open(os.path.join(ws, "_alerta.txt"), "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def enviar(subject: str, body: str) -> int:
    key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if not key:
        print("::warning::newsletter: falta BUTTONDOWN_API_KEY, no se envía")
        return 0
    status = os.environ.get("NEWSLETTER_STATUS", "about_to_send").strip() or "about_to_send"
    payload = json.dumps({"subject": subject, "body": body, "status": status}).encode("utf-8")
    req = urllib.request.Request(
        API, data=payload, method="POST",
        headers={
            "Authorization": "Token " + key,
            "Content-Type": "application/json",
            # Buttondown exige este header para mandar mails por API
            # (status 'about_to_send'); sin él responde 400
            # "sending_requires_confirmation" y no sale nada.
            "X-Buttondown-Live-Dangerously": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"newsletter: enviado (status API {r.status}, estado '{status}')")
            return 0
    except urllib.error.HTTPError as e:
        cuerpo = e.read(400).decode("utf-8", "ignore")
        _alertar(f"newsletter: la API respondió {e.code} - {cuerpo}")
        return 0  # no corta el workflow; el aviso lo pone en rojo al final
    except Exception as e:  # noqa: BLE001
        _alertar(f"newsletter: error enviando - {e}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera y envía el newsletter semanal de MoVeTe")
    ap.add_argument("--eventos", default="eventos.json")
    ap.add_argument("--dry-run", action="store_true", help="Solo imprime, no envía")
    args = ap.parse_args()

    try:  # consola de Windows suele ser cp1252 y rompe con emojis
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    eventos, _generado = cargar_eventos(args.eventos)
    jueves = jueves_de_edicion(date.today())
    subject, body = armar_email(eventos, jueves)

    if args.dry_run:
        print("=== SUBJECT ===")
        print(subject)
        print("\n=== BODY (markdown) ===")
        print(body)
        return 0

    return enviar(subject, body)


if __name__ == "__main__":
    sys.exit(main())
