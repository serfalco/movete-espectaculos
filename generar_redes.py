"""MoVeTe — Piezas para Instagram y Facebook, armadas solas desde eventos.json.

Corre en el workflow del jueves, después de generar la edición. Deja en
Movete-info/redes/<jueves>/:

  - carrusel-00.jpg ... : "Qué hacer en La Plata este finde" (tapa, hasta 8
    funciones de vie/sáb/dom y cierre). Se publica el jueves.
  - historia-AAAA-MM-DD.jpg : "Hoy en La Plata", una por día de la semana
    (jueves a miércoles), con hasta 4 funciones. Se publica ese día.
  - manifest.json : URLs públicas de las imágenes y los textos de cada red.

No publica nada: eso lo hace publicar_redes.py, que lee el manifest. Así las
piezas se pueden mirar en movete.info/redes/<jueves>/ aunque las cuentas
todavía no existan.

Pensado también para Google: cada texto nombra show, sala y "La Plata", y los
links llevan a la página de la obra (las que ya posicionan), con UTM para
medir cuánta gente llega desde cada red.

Uso:
    python generar_redes.py --eventos eventos.json --salida ../Movete-info/redes
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from edicion import jueves_de_edicion
from generar_edicion import (
    cargar_eventos,
    normalizar_categorias,
    parse_fecha,
    cat_label,
    evento_titulo,
    evento_lugar,
    obra_slug,
    calcular_alias_obras,
    _ALIAS_OBRA,
    _hora,
    _sin_gritos,
)
from generar_newsletter import _elegir, EMOJI_CAT, RUBROS
from imagenes import nombre_local, URL_BASE as URL_AFICHES
from venues import venue_canonico, venue_instagram

BASE = "https://movete.info"
URL_REDES = f"{BASE}/redes"
AQUI = Path(__file__).resolve().parent
FUENTES = AQUI / "fonts"

# Colores de la marca (Movete-info/assets/css/movete.css).
PAPEL = (244, 238, 217)
TINTA = (26, 22, 17)
ACENTO = (178, 53, 41)
VERDE = (179, 189, 51)
GRIS = (98, 90, 80)

ANCHO = 1080
ALTO_POST = 1350      # 4:5, el formato que más pantalla ocupa en el feed
ALTO_HISTORIA = 1920  # 9:16

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

HASHTAGS = "#LaPlata #QuéHacerEnLaPlata #CulturaLaPlata #AgendaCultural"

# Un solo pedido extra por semana, rotando, para no sonar a spam.
LLAMADOS = [
    "Guardalo y mandáselo a quien te acompañe 💌",
    "Seguinos para tener los planes de cada finde 🙌",
    "¿La cartelera en tu mail cada jueves? Newsletter gratis, link en la bio 💌",
]

TOPE_CARRUSEL = 8
TOPE_HISTORIA = 4
EDICIONES_A_GUARDAR = 3


# --- Selección ---------------------------------------------------------------

def _con_fecha(eventos: list[dict]) -> list[dict]:
    return [e for e in normalizar_categorias(eventos)
            if e.get("categoria") != "cine" and e.get("fecha")]


def _del_dia(eventos: list[dict], dia: date) -> list[dict]:
    return [e for e in eventos if str(e["fecha"])[:10] == dia.isoformat()]


def elegir_finde(eventos: list[dict], jueves: date, con_afiche) -> list[dict]:
    """Hasta 8 funciones de vie/sáb/dom, repartidas por rubro y sin repetir sala.

    Primero los rubros del newsletter (teatro, música, stand up, danza e
    infantil), después lo mejor que quede. Si hay suficientes con afiche, solo
    esas: un carrusel sin imágenes no se guarda ni se comparte.
    """
    dias = {jueves + timedelta(days=d) for d in (1, 2, 3)}
    cands = [e for e in eventos if parse_fecha(e["fecha"]).date() in dias]
    con_img = [e for e in cands if con_afiche(e)]
    if len(con_img) >= 5:
        cands = con_img
    cupos = {"teatro": 2, "musica": 2, "stand-up": 2, "danza": 1}
    elegidos: list[dict] = []
    for cats, _titulo, _n in RUBROS:
        n = cupos.get(cats[0], 1)
        elegidos += _elegir([e for e in cands if e.get("categoria") in cats], n)
    resto = [e for e in cands if e not in elegidos]
    elegidos += _elegir(resto, TOPE_CARRUSEL)
    # Repartir entre viernes, sábado y domingo (de a uno por día, por turno),
    # sin repetir sala: sin esto el carrusel se llena con el viernes y el sábado.
    por_dia: dict[str, list[dict]] = {}
    for e in elegidos:  # ya vienen en orden de preferencia
        por_dia.setdefault(str(e["fecha"])[:10], []).append(e)
    vistos: set[str] = set()
    unicos: list[dict] = []
    while len(unicos) < TOPE_CARRUSEL and any(por_dia.values()):
        for dia in sorted(por_dia):
            while por_dia[dia]:
                e = por_dia[dia].pop(0)
                if _clave_sala(e) not in vistos:
                    vistos.add(_clave_sala(e))
                    unicos.append(e)
                    break
            if len(unicos) >= TOPE_CARRUSEL:
                break
    return sorted(unicos, key=lambda e: e["fecha"])


def elegir_dia(eventos: list[dict], dia: date, con_afiche) -> list[dict]:
    cands = _del_dia(eventos, dia)
    con_img = [e for e in cands if con_afiche(e)]
    if len(con_img) >= TOPE_HISTORIA:
        cands = con_img
    return _elegir(cands, TOPE_HISTORIA)


def _clave_sala(ev: dict) -> str:
    vc = venue_canonico(evento_lugar(ev))
    return vc["slug"] if vc else evento_lugar(ev).casefold().strip()


# --- Textos ------------------------------------------------------------------

def _sala(ev: dict) -> str:
    vc = venue_canonico(evento_lugar(ev))
    return (vc or {}).get("nombre") or evento_lugar(ev) or "La Plata"


def _titulo(ev: dict) -> str:
    return _sin_gritos(evento_titulo(ev)).strip()


def _cuando(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    h = _hora(ev)
    return f"{DIAS_CORTOS[f.weekday()]} {f.day}" + (f", {h} h" if h else "")


def _utm(url: str, red: str, campania: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source={red}&utm_medium=social&utm_campaign={campania}"


def _link_obra(ev: dict) -> str:
    oslug = obra_slug(ev)
    return f"{BASE}/en-vivo/obra/{oslug}/" if oslug else f"{BASE}/en-vivo/"


def _mencion(ev: dict, cuentas: dict) -> str:
    """@cuenta de la sala: la de VENUES_INSTAGRAM (venues.py), salvo que
    `cuentas` traiga otra para ese slug.

    Arrobar avisa a la sala: si repostea, llega a su público, y si algún día
    nos linkea desde su web o linktree, ese link sí cuenta para Google.
    """
    vc = venue_canonico(evento_lugar(ev))
    if not vc:
        return ""
    cuenta = cuentas.get(vc["slug"]) or venue_instagram(vc["slug"])
    if not cuenta:
        return ""
    return f" {cuenta if cuenta.startswith('@') else '@' + cuenta}"


def _linea(ev: dict, cuentas: dict, solo_hora: bool = False) -> str:
    emoji = EMOJI_CAT.get(ev.get("categoria") or "", "✨")
    h = _hora(ev)
    cuando = (f"{h} h" if h else "") if solo_hora else _cuando(ev)
    prefijo = f"{emoji} {cuando} · " if cuando else f"{emoji} "
    return f"{prefijo}{_titulo(ev)} — {_sala(ev)}{_mencion(ev, cuentas)}"


def _rango_finde(jueves: date) -> str:
    vie, dom = jueves + timedelta(days=1), jueves + timedelta(days=3)
    if vie.month == dom.month:
        return f"{vie.day} al {dom.day} de {MESES[dom.month - 1]}"
    return f"{vie.day} de {MESES[vie.month - 1]} al {dom.day} de {MESES[dom.month - 1]}"


def texto_carrusel(evs: list[dict], jueves: date, red: str, cuentas: dict) -> str:
    campania = f"finde-{jueves.isoformat()}"
    llamado = LLAMADOS[jueves.isocalendar().week % len(LLAMADOS)]
    lineas = [f"Qué hacer en La Plata este finde, del {_rango_finde(jueves)} 🙌", ""]
    for ev in evs:
        lineas.append(_linea(ev, cuentas))
        if red == "facebook":  # en Facebook los links funcionan
            lineas.append(_utm(_link_obra(ev), red, campania))
    lineas.append("")
    if red == "facebook":
        lineas.append("Toda la cartelera del finde: "
                      + _utm(f"{BASE}/en-vivo/fin-de-semana/", red, campania))
    else:
        lineas.append("Toda la cartelera en movete.info (link en la bio) 👈")
    lineas += [llamado, "", HASHTAGS]
    return "\n".join(lineas)


def texto_dia_facebook(evs: list[dict], dia: date, cuentas: dict) -> str:
    campania = f"hoy-{dia.isoformat()}"
    lineas = [f"Hoy {DIAS[dia.weekday()]} {dia.day} de {MESES[dia.month - 1]} en La Plata:", ""]
    for ev in evs:
        lineas.append(_linea(ev, cuentas, solo_hora=True))
        lineas.append(_utm(_link_obra(ev), "facebook", campania))
    lineas += ["", "Más planes para hoy: " + _utm(f"{BASE}/en-vivo/hoy/", "facebook", campania),
               "", "#LaPlata #QuéHacerEnLaPlata"]
    return "\n".join(lineas)


# --- Dibujo ------------------------------------------------------------------

def _fuente(peso: str, tam: int):
    from PIL import ImageFont
    for ruta in (FUENTES / f"Poppins-{peso}.ttf",
                 Path(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if peso == 'Bold' else ''}.ttf")):
        try:
            return ImageFont.truetype(str(ruta), tam)
        except OSError:
            continue
    return ImageFont.load_default(tam)


def _envolver(draw, texto: str, fuente, ancho: int, max_lineas: int) -> tuple[list[str], bool]:
    """Corta en líneas que entran en `ancho`. Devuelve (líneas, entró_todo)."""
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    for p in palabras:
        prueba = f"{actual} {p}".strip()
        if draw.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
            continue
        if actual:
            lineas.append(actual)
        actual = p
        # Palabra sola más ancha que la caja: se recorta a la fuerza.
        while draw.textlength(actual, font=fuente) > ancho and len(actual) > 1:
            actual = actual[:-1]
    if actual:
        lineas.append(actual)
    if len(lineas) <= max_lineas:
        return lineas, True
    lineas = lineas[:max_lineas]
    ultima = lineas[-1]
    while ultima and draw.textlength(ultima + "…", font=fuente) > ancho:
        ultima = ultima[:-1].rstrip()
    lineas[-1] = ultima + "…"
    return lineas, False


def _titulo_que_entre(draw, texto, peso, ancho, max_lineas, tam_max, tam_min):
    tam = tam_max
    while True:
        f = _fuente(peso, tam)
        lineas, ok = _envolver(draw, texto, f, ancho, max_lineas)
        if ok or tam <= tam_min:
            return f, lineas
        tam -= 4


def _alto_linea(fuente) -> int:
    asc, desc = fuente.getmetrics()
    return int((asc + desc) * 1.05)


def _escribir(draw, xy, lineas, fuente, color) -> int:
    x, y = xy
    for linea in lineas:
        draw.text((x, y), linea, font=fuente, fill=color)
        y += _alto_linea(fuente)
    return y


def _logo(draw, x: int, y: int, tam: int, color, punto=ACENTO) -> None:
    f = _fuente("Bold", tam)
    draw.text((x, y), "MoVeTe", font=f, fill=color)
    w = draw.textlength("MoVeTe", font=f)
    r = tam // 6
    cy = y + int(tam * 0.95)
    draw.ellipse((x + w + 6, cy - r, x + w + 6 + 2 * r, cy + r), fill=punto)


def _chip(draw, x: int, y: int, texto: str, fondo, color, tam: int = 28) -> int:
    f = _fuente("Bold", tam)
    w = draw.textlength(texto, font=f)
    h = int(tam * 1.7)
    draw.rounded_rectangle((x, y, x + w + 40, y + h), radius=h // 2, fill=fondo)
    draw.text((x + 20, y + (h - _alto_linea(f)) // 2), texto, font=f, fill=color)
    return int(x + w + 40)


def _encuadrar(img, w: int, h: int):
    """Afiche entero, sobre una copia ampliada y desenfocada de sí mismo."""
    from PIL import Image, ImageFilter, ImageOps, ImageEnhance
    fondo = ImageOps.fit(img, (w, h), Image.LANCZOS).filter(ImageFilter.GaussianBlur(36))
    fondo = ImageEnhance.Brightness(fondo).enhance(0.55)
    escala = min(w / img.width, h / img.height)
    frente = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.LANCZOS)
    fondo.paste(frente, ((w - frente.width) // 2, (h - frente.height) // 2))
    return fondo


def _sin_afiche(w: int, h: int, ev: dict):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), ACENTO)
    d = ImageDraw.Draw(img)
    for i in range(-h, w, 90):  # rayas suaves, para que no sea un bloque plano
        d.line((i, h, i + h, 0), fill=(190, 66, 54), width=28)
    f, lineas = _titulo_que_entre(d, cat_label(ev.get("categoria") or "otros").upper(),
                                  "Bold", w - 120, 2, 120, 60)
    alto = len(lineas) * _alto_linea(f)
    y = (h - alto) // 2
    for linea in lineas:
        lw = d.textlength(linea, font=f)
        d.text(((w - lw) // 2, y), linea, font=f, fill=PAPEL)
        y += _alto_linea(f)
    return img


class Afiches:
    """Encuentra la copia local del afiche (la que baja la edición)."""

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta

    def ruta(self, ev: dict) -> Path | None:
        url = str(ev.get("imagen") or "").strip()
        if not url.startswith(("http://", "https://")):
            return None
        nombre = url.rsplit("/", 1)[-1] if url.startswith(URL_AFICHES) else nombre_local(url)
        p = self.carpeta / nombre
        return p if p.exists() and p.stat().st_size > 0 else None

    def __call__(self, ev: dict) -> bool:
        return self.ruta(ev) is not None

    def abrir(self, ev: dict):
        from PIL import Image
        p = self.ruta(ev)
        if not p:
            return None
        try:
            with Image.open(p) as im:
                return im.convert("RGB")
        except Exception:  # noqa: BLE001 — archivo roto: se dibuja sin afiche
            return None


def placa_evento(ev: dict, afiches: Afiches, n: int, total: int):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (ANCHO, ALTO_POST), PAPEL)
    alto_img = 820
    afiche = afiches.abrir(ev)
    img.paste(_encuadrar(afiche, ANCHO, alto_img) if afiche else _sin_afiche(ANCHO, alto_img, ev), (0, 0))
    d = ImageDraw.Draw(img)
    x, y = 64, alto_img + 40
    fin_chip = _chip(d, x, y, cat_label(ev.get("categoria") or "otros").upper(), ACENTO, PAPEL)
    f_cuando = _fuente("Bold", 34)
    d.text((fin_chip + 22, y + 6), _cuando(ev).upper(), font=f_cuando, fill=TINTA)
    y += 76
    f_tit, lineas = _titulo_que_entre(d, _titulo(ev), "Bold", ANCHO - 128, 3, 64, 40)
    y = _escribir(d, (x, y), lineas, f_tit, TINTA) + 6
    f_sala = _fuente("Regular", 34)
    sala, _ = _envolver(d, _sala(ev), f_sala, ANCHO - 128, 1)
    _escribir(d, (x, y), sala, f_sala, GRIS)
    # Pie
    f_pie = _fuente("Bold", 30)
    d.text((x, ALTO_POST - 72), "movete.info", font=f_pie, fill=ACENTO)
    cont = f"{n}/{total}"
    d.text((ANCHO - 64 - d.textlength(cont, font=f_pie), ALTO_POST - 72), cont, font=f_pie, fill=GRIS)
    return img


def placa_tapa(evs: list[dict], jueves: date, afiches: Afiches):
    from PIL import Image, ImageDraw, ImageOps
    img = Image.new("RGB", (ANCHO, ALTO_POST), TINTA)
    d = ImageDraw.Draw(img)
    _logo(d, 64, 56, 48, PAPEL)
    f1 = _fuente("Bold", 104)
    y = 210
    for linea in ("Qué hacer", "en La Plata"):
        d.text((64, y), linea, font=f1, fill=PAPEL)
        y += _alto_linea(f1) - 10
    d.text((64, y), "este finde", font=f1, fill=VERDE)
    y += _alto_linea(f1) + 10
    d.text((64, y), _rango_finde(jueves).capitalize(), font=_fuente("Medium", 44), fill=PAPEL)
    # Tira de tres afiches
    # Uno por día primero (vie, sáb, dom), así la tapa muestra todo el finde.
    orden, dias = [], set()
    for e in evs:
        if str(e["fecha"])[:10] not in dias:
            dias.add(str(e["fecha"])[:10])
            orden.append(e)
    orden += [e for e in evs if e not in orden]
    con = [afiches.abrir(e) for e in orden]
    con = [a for a in con if a][:3]
    if con:
        w, h, gap = 300, 400, 26
        x0 = (ANCHO - (len(con) * w + (len(con) - 1) * gap)) // 2
        for i, a in enumerate(con):
            img.paste(ImageOps.fit(a, (w, h), centering=(0.5, 0.3)), (x0 + i * (w + gap), 760))
    # Poppins no trae la flecha: se dibuja.
    f_des = _fuente("Bold", 40)
    texto = "Deslizá"
    xf, yf = ANCHO - 64 - 46, ALTO_POST - 100 + 30
    d.text((xf - 18 - d.textlength(texto, font=f_des), ALTO_POST - 100), texto, font=f_des, fill=VERDE)
    d.line((xf, yf, xf + 40, yf), fill=VERDE, width=7)
    d.polygon([(xf + 46, yf), (xf + 28, yf - 15), (xf + 28, yf + 15)], fill=VERDE)
    return img


def placa_cierre():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (ANCHO, ALTO_POST), ACENTO)
    d = ImageDraw.Draw(img)
    _logo(d, 64, 56, 48, PAPEL, punto=TINTA)
    y = 300
    f1 = _fuente("Bold", 84)
    for linea in ("Toda la cartelera", "de la semana en"):
        d.text((64, y), linea, font=f1, fill=PAPEL)
        y += _alto_linea(f1) - 6
    d.text((64, y), "movete.info", font=_fuente("Bold", 104), fill=TINTA)
    y += 190
    f2 = _fuente("Medium", 40)
    for linea in ("Teatro · Música · Stand up", "Danza · Infantiles · Cine", "",
                  "Seguinos para tener los planes de cada finde.",
                  "Newsletter gratis cada jueves: link en la bio."):
        d.text((64, y), linea, font=f2, fill=PAPEL)
        y += _alto_linea(f2) + 4
    return img


def placa_historia(evs: list[dict], dia: date, afiches: Afiches):
    from PIL import Image, ImageDraw, ImageOps
    img = Image.new("RGB", (ANCHO, ALTO_HISTORIA), PAPEL)
    d = ImageDraw.Draw(img)
    # Arriba y abajo Instagram tapa ~250 px con su interfaz: nada importante ahí.
    d.rectangle((0, 0, ANCHO, 480), fill=TINTA)
    _logo(d, 64, 150, 40, PAPEL)
    d.text((64, 220), "Hoy en La Plata", font=_fuente("Bold", 88), fill=PAPEL)
    d.text((64, 350), f"{DIAS[dia.weekday()].capitalize()} {dia.day} de {MESES[dia.month - 1]}",
           font=_fuente("Medium", 46), fill=VERDE)
    y = 530
    alto_fila = 286
    for ev in evs:
        a = afiches.abrir(ev)
        tw, th = 200, 266
        if a:
            img.paste(ImageOps.fit(a, (tw, th), centering=(0.5, 0.3)), (64, y))
        else:
            img.paste(_sin_afiche(tw, th, ev), (64, y))
        x = 64 + tw + 36
        ancho = ANCHO - x - 64
        fin = _chip(d, x, y, cat_label(ev.get("categoria") or "otros").upper(), ACENTO, PAPEL, 24)
        h = _hora(ev)
        if h:
            d.text((fin + 18, y + 4), f"{h} H", font=_fuente("Bold", 32), fill=TINTA)
        f_tit, lineas = _titulo_que_entre(d, _titulo(ev), "Bold", ancho, 2, 46, 32)
        yy = _escribir(d, (x, y + 64), lineas, f_tit, TINTA)
        f_sala = _fuente("Regular", 30)
        sala, _ = _envolver(d, _sala(ev), f_sala, ancho, 1)
        _escribir(d, (x, yy + 4), sala, f_sala, GRIS)
        y += alto_fila
    f_pie = _fuente("Bold", 50)
    pie = "Más planes en movete.info"
    d.text(((ANCHO - d.textlength(pie, font=f_pie)) // 2, 1690), pie, font=f_pie, fill=ACENTO)
    return img


def _guardar(img, ruta: Path) -> None:
    img.save(ruta, "JPEG", quality=88, optimize=True, progressive=True)


# --- Armado ------------------------------------------------------------------

def generar(eventos_path: str, salida: str | Path, afiches_dir: str | Path,
            hoy: date | None = None, cuentas_path: str | Path | None = None) -> dict:
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[redes] Pillow no está instalado: no se generan piezas")
        return {"omitido": True}

    eventos, _ = cargar_eventos(eventos_path)
    _ALIAS_OBRA.clear()
    _ALIAS_OBRA.update(calcular_alias_obras(normalizar_categorias(eventos)))
    evs = _con_fecha(eventos)
    jueves = jueves_de_edicion(hoy or date.today())
    afiches = Afiches(Path(afiches_dir))
    cuentas: dict = {}
    if cuentas_path and Path(cuentas_path).exists():
        cuentas = {k: v for k, v in json.loads(Path(cuentas_path).read_text("utf-8")).items()
                   if not k.startswith("_") and v}

    salida = Path(salida)
    carpeta = salida / jueves.isoformat()
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    url_base = f"{URL_REDES}/{jueves.isoformat()}"
    manifest: dict = {"edicion": jueves.isoformat(),
                      "generado": datetime.now().isoformat(timespec="seconds"),
                      "carrusel": None, "historias": {}}

    finde = elegir_finde(evs, jueves, afiches)
    if len(finde) >= 3:
        placas = [placa_tapa(finde, jueves, afiches)]
        placas += [placa_evento(e, afiches, i + 1, len(finde)) for i, e in enumerate(finde)]
        placas.append(placa_cierre())
        urls = []
        for i, p in enumerate(placas):
            nombre = f"carrusel-{i:02d}.jpg"
            _guardar(p, carpeta / nombre)
            urls.append(f"{url_base}/{nombre}")
        manifest["carrusel"] = {
            "publicar": jueves.isoformat(),
            "imagenes": urls,
            "instagram": texto_carrusel(finde, jueves, "instagram", cuentas),
            "facebook": texto_carrusel(finde, jueves, "facebook", cuentas),
        }

    for k in range(7):
        dia = jueves + timedelta(days=k)
        del_dia = elegir_dia(evs, dia, afiches)
        if not del_dia:
            continue
        nombre = f"historia-{dia.isoformat()}.jpg"
        _guardar(placa_historia(del_dia, dia, afiches), carpeta / nombre)
        manifest["historias"][dia.isoformat()] = {
            "imagen": f"{url_base}/{nombre}",
            "facebook": texto_dia_facebook(del_dia, dia, cuentas),
        }

    (carpeta / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    _podar(salida)
    return {"edicion": jueves.isoformat(),
            "carrusel": len(manifest["carrusel"]["imagenes"]) if manifest["carrusel"] else 0,
            "historias": len(manifest["historias"])}


def _podar(salida: Path) -> None:
    """Deja solo las últimas ediciones: las imágenes viejas solo pesan en el repo."""
    viejas = sorted(p for p in salida.iterdir() if p.is_dir() and len(p.name) == 10)
    for p in viejas[:-EDICIONES_A_GUARDAR]:
        shutil.rmtree(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="Piezas para redes de MoVeTe")
    ap.add_argument("--eventos", default="eventos.json")
    ap.add_argument("--salida", default="../Movete-info/redes")
    ap.add_argument("--afiches", default="../Movete-info/assets/afiches")
    ap.add_argument("--cuentas", default=None, help="JSON slug→@cuenta que pisa a venues.py")
    ap.add_argument("--hoy", default=None)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    hoy = date.fromisoformat(args.hoy) if args.hoy else None
    print(json.dumps(generar(args.eventos, args.salida, args.afiches, hoy, args.cuentas),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
