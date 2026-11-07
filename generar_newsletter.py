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
import html
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
    evento_url,
    obra_slug,
    calcular_alias_obras,
    _ALIAS_OBRA,
    _hora,
    _sin_gritos,
)
from imagenes import nombre_local, URL_BASE as URL_AFICHES
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


# --- Diseño del mail -------------------------------------------------------
# HTML con estilos en línea y tablas: es lo único que Gmail, Apple Mail y
# Outlook respetan. Antes iba en markdown y Buttondown pegaba las líneas de
# cada rubro en un solo párrafo ("Vie 30 · A — Sala · Sáb 31 · B — ...").
# Colores de la marca (style.css): papel, tinta y naranja.
TINTA = "#0e0d10"
PAPEL = "#f5f1e8"
ACENTO = "#ff5128"
GRIS = "#6b6870"
LINEA = "#e6e0d3"
SANS = "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"
COLOR_RUBRO = {"🎭 Teatro": "#7b5ea7", "🎵 Música": "#2e86ab",
               "😂 Stand up": "#ff5128", "💃 Danza e infantil": "#44bba4"}
# El mail se abre en Buttondown tal cual: sin esta marca lo pasa por markdown.
MODO_HTML = "<!-- buttondown-editor-mode: plaintext -->"


def _e(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def _link(ev: dict) -> str:
    oslug = obra_slug(ev)
    if oslug:
        return f"{BASE}/en-vivo/obra/{oslug}/"
    return evento_url(ev) or f"{BASE}/en-vivo/"


def _imagen(ev: dict) -> str:
    """Solo la copia liviana de movete.info (la que genera la edición en
    ../Movete-info/assets/afiches; se cambia con MOVETE_AFICHES_DIR). Sin
    copia no va imagen: la original puede pesar varios MB o no cargar."""
    url = str(ev.get("imagen") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ""
    if url.startswith(BASE):
        return url
    carpeta = (os.environ.get("MOVETE_AFICHES_DIR", "").strip()
               or os.path.join("..", "Movete-info", "assets", "afiches"))
    if os.path.exists(os.path.join(carpeta, nombre_local(url))):
        return URL_AFICHES + nombre_local(url)
    return ""


EMOJI_CAT = {"teatro": "🎭", "impro": "🎭", "musica": "🎵", "stand-up": "😂",
             "humor": "😂", "danza": "💃", "infantil": "🧸"}


def _banner_generico(ev: dict, url: str) -> str:
    """Portada del destacado cuando no hay afiche: HTML puro, no pesa nada."""
    emoji = EMOJI_CAT.get(ev.get("categoria") or "", "✨")
    return (f'<a href="{_e(url)}" style="text-decoration:none">'
            f'<div style="background:{TINTA};border-radius:10px 10px 0 0;'
            f'padding:26px 18px;text-align:center">'
            f'<div style="font-size:44px;line-height:1">{emoji}</div>'
            f'<div style="font-family:{SERIF};font-size:18px;font-weight:700;'
            f'color:{PAPEL};margin-top:10px">MoVeTe<span style="color:{ACENTO}">.</span>'
            f'</div></div></a>')


def _cuando(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    h = _hora(ev)
    txt = f"{DIAS_CORTOS[f.weekday()]} {f.day}"
    return f"{txt} · {h} h" if h else txt


def _boton(texto: str, url: str, color: str = ACENTO) -> str:
    return (f'<a href="{_e(url)}" style="display:inline-block;background:{color};'
            f'color:#ffffff;font-family:{SANS};font-size:13px;font-weight:700;'
            f'text-decoration:none;padding:8px 14px;border-radius:999px;'
            f'margin:4px 4px 0 0">{_e(texto)}</a>')


def _fila_evento(ev: dict, color: str) -> str:
    img = _imagen(ev)
    url = _link(ev)
    miniatura = (
        f'<td width="64" valign="top" style="padding:12px 12px 12px 0">'
        f'<a href="{_e(url)}"><img src="{_e(img)}" width="64" alt="" '
        f'style="display:block;width:64px;border-radius:6px;border:0"></a></td>'
        if img else
        f'<td width="6" valign="top" style="padding:12px 12px 12px 0">'
        f'<div style="width:6px;height:44px;background:{color};border-radius:3px"></div></td>'
    )
    return (
        f'<tr>{miniatura}'
        f'<td valign="top" style="padding:12px 0;border-bottom:1px solid {LINEA}">'
        f'<div style="font-family:{SANS};font-size:12px;font-weight:700;'
        f'letter-spacing:.04em;text-transform:uppercase;color:{color}">{_e(_cuando(ev))}</div>'
        f'<a href="{_e(url)}" style="display:block;font-family:{SANS};font-size:16px;'
        f'font-weight:700;line-height:1.3;color:{TINTA};text-decoration:none;'
        f'margin:3px 0 2px">{_e(_sin_gritos(evento_titulo(ev)))}</a>'
        f'<div style="font-family:{SANS};font-size:13px;line-height:1.4;color:{GRIS}">'
        f'📍 {_e(evento_lugar(ev))}</div></td></tr>'
    )


def _bloque_rubro(titulo: str, eventos: list[dict]) -> str:
    color = COLOR_RUBRO.get(titulo, ACENTO)
    filas = "".join(_fila_evento(e, color) for e in eventos)
    return (
        f'<tr><td style="padding:22px 20px 4px">'
        f'<div style="font-family:{SANS};font-size:15px;font-weight:800;color:{TINTA};'
        f'padding-bottom:6px;border-bottom:2px solid {color}">{_e(titulo)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'border="0">{filas}</table></td></tr>'
    )


def _bloque_destacado(ev: dict) -> str:
    img = _imagen(ev)
    url = _link(ev)
    foto = (f'<a href="{_e(url)}"><img src="{_e(img)}" width="520" alt="" '
            f'style="display:block;width:100%;max-width:520px;height:auto;'
            f'border-radius:10px 10px 0 0;border:0"></a>' if img
            else _banner_generico(ev, url))
    return (
        f'<tr><td style="padding:20px 20px 0">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:#ffffff;border-radius:10px;border:1px solid {LINEA}">'
        f'<tr><td>{foto}</td></tr><tr><td style="padding:16px 18px 18px">'
        f'<div style="font-family:{SANS};font-size:11px;font-weight:800;letter-spacing:.08em;'
        f'color:{ACENTO}">⭐ NO TE LO PIERDAS</div>'
        f'<a href="{_e(url)}" style="display:block;font-family:{SERIF};font-size:22px;'
        f'font-weight:700;line-height:1.25;color:{TINTA};text-decoration:none;margin:6px 0 4px">'
        f'{_e(_sin_gritos(evento_titulo(ev)))}</a>'
        f'<div style="font-family:{SANS};font-size:14px;color:{GRIS}">'
        f'{_e(_cuando(ev))} · {_e(evento_lugar(ev))}</div>'
        f'<div style="padding-top:10px">{_boton("Ver detalles", url)}</div>'
        f'</td></tr></table></td></tr>'
    )


def armar_email(eventos: list[dict], jueves: date) -> tuple[str, str]:
    rango = etiqueta_rango(jueves)
    # Mismos links que la edición: la variante de un título apunta a la
    # página principal de la obra (ver calcular_alias_obras).
    _ALIAS_OBRA.clear()
    _ALIAS_OBRA.update(calcular_alias_obras(normalizar_categorias(eventos)))
    semana = eventos_de_la_semana(eventos, jueves)
    destacado = elegir_destacado_under(
        [e for e in normalizar_categorias(eventos) if e.get("fecha")], jueves
    )

    subject = f"MoVeTe · Qué hacer en La Plata · semana {rango}"

    filas = [
        f'<tr><td style="background:{TINTA};padding:22px 20px;border-radius:12px 12px 0 0">'
        f'<div style="font-family:{SERIF};font-size:26px;font-weight:700;color:{PAPEL}">'
        f'MoVeTe<span style="color:{ACENTO}">.</span></div>'
        f'<div style="font-family:{SANS};font-size:13px;color:#cfc9bd;margin-top:4px">'
        f'Qué hacer en La Plata · semana {_e(rango)}</div></td></tr>'
    ]
    if destacado:
        filas.append(_bloque_destacado(destacado))

    for cats, titulo, n in RUBROS:
        elegidos = _elegir([e for e in semana if e.get("categoria") in cats], n)
        if elegidos:
            filas.append(_bloque_rubro(titulo, elegidos))

    filas.append(
        f'<tr><td align="center" style="padding:26px 20px 8px">'
        f'<div style="font-family:{SANS};font-size:13px;color:{GRIS};padding-bottom:6px">'
        f'Toda la cartelera, día por día:</div>'
        + _boton("🎤 En vivo", f"{BASE}/en-vivo/", TINTA)
        + _boton("🎬 Cine", f"{BASE}/cine/", TINTA)
        + _boton("🏟️ Grandes shows", f"{BASE}/en-vivo/lo-que-se-viene/", TINTA)
        + '</td></tr>'
    )
    filas.append(
        f'<tr><td align="center" style="padding:14px 20px 24px;font-family:{SERIF};'
        f'font-size:14px;font-style:italic;color:{GRIS}">Porque la cultura es encontrarnos. · '
        f'<a href="{BASE}" style="color:{ACENTO};text-decoration:none">movete.info</a></td></tr>'
    )

    cuerpo = (
        f'{MODO_HTML}\n'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{PAPEL}"><tr><td align="center" style="padding:12px 8px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="max-width:560px;background:{PAPEL}">'
        + "".join(filas) +
        '</table></td></tr></table>'
    )
    return subject, cuerpo


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
        print("\n=== BODY (html) ===")
        print(body)
        return 0

    return enviar(subject, body)


if __name__ == "__main__":
    sys.exit(main())
