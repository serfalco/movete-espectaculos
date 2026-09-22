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

BASE = "https://movete.info"
API = "https://api.buttondown.com/v1/emails"
MAX_PLANAZOS = 8


def eventos_de_la_semana(eventos: list[dict], jueves: date) -> list[dict]:
    evs = [
        e for e in normalizar_categorias(eventos)
        if e.get("categoria") != "cine" and e.get("fecha")
        and en_esta_semana(e["fecha"], jueves)
    ]
    evs.sort(key=lambda e: e.get("fecha", ""))
    return evs


def _linea_evento(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    cuando = f"{f.day} {MESES_ABR[f.month]} {f.strftime('%H:%M')}hs"
    titulo = evento_titulo(ev)
    lugar = evento_lugar(ev)
    cat = cat_label(ev.get("categoria", "otros"))
    return f"- **{cuando}** · {titulo} — {lugar} _({cat})_"


def armar_email(eventos: list[dict], jueves: date) -> tuple[str, str]:
    rango = etiqueta_rango(jueves)
    semana = eventos_de_la_semana(eventos, jueves)
    destacado = elegir_destacado_under(
        [e for e in normalizar_categorias(eventos) if e.get("fecha")], jueves
    )

    subject = f"MoVeTe · Qué hacer en La Plata · semana {rango}"

    partes = [
        f"## Qué hacer en La Plata\nSemana **{rango}**. Estos son algunos planazos; "
        f"la cartelera completa está en [movete.info]({BASE}).\n",
    ]

    if destacado:
        f = parse_fecha(destacado["fecha"])
        partes.append(
            "### ⭐ No te lo pierdas\n"
            f"**{evento_titulo(destacado)}** — {evento_lugar(destacado)} · "
            f"{f.day} {MESES_ABR[f.month]}\n"
        )

    if semana:
        partes.append("### Algunos planazos de la semana")
        partes.append("\n".join(_linea_evento(e) for e in semana[:MAX_PLANAZOS]))
        partes.append("")

    partes.append(
        "### Mirá todo\n"
        f"- 🎭 [En Vivo]({BASE}/en-vivo/) — teatro, música, stand up y más\n"
        f"- 🎬 [Cine]({BASE}/cine/) — cartelera de la semana\n"
        f"- 🔥 [Grandes shows anunciados]({BASE}/en-vivo/lo-que-se-viene/)\n"
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
