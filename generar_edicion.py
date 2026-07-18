"""Generador estático de En Vivo para MoVeTe.

Lee eventos.json, genera una edición semanal jueves→miércoles y escribe:

- /index.html portada vigente de En Vivo
- /YYYY-MM-DD/index.html edición archivada

Ejemplo local:

python generar_edicion.py --eventos eventos.json --output ../Movete-info/en-vivo
"""

from __future__ import annotations

import argparse
import html
import json
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from edicion import (
    MESES_ABR,
    en_esta_semana,
    etiqueta_dia,
    etiqueta_rango,
    jueves_de_edicion,
    slug_edicion,
)
from venues import venue_info, venue_masivo, venue_canonico, venue_slug


CAT_LABEL = {
    "teatro": "Teatro",
    "musica": "Música",
    "stand-up": "Stand Up",
    "danza": "Danza",
    "cine": "Cine",
    "infantil": "Infantil",
    "taller": "Taller",
    "a-plasticas": "Artes plásticas",
    "impro": "Impro",
    "humor": "Humor",
    "otros": "Otros",
}

CATEGORY_ORDER = [
    "stand-up",
    "teatro",
    "musica",
    "danza",
    "infantil",
    "taller",
    "impro",
    "humor",
    "a-plasticas",
    "otros",
]

CAT_INTRO_MAIN = (
    "Qué hacer en La Plata esta semana: teatro, música en vivo, stand up, "
    "danza y más espectáculos. Una cartelera cultural nueva cada jueves."
)

CAT_INTRO = {
    "teatro": "Teatro en La Plata esta semana: obras, unipersonales, salas independientes y funciones para agendar.",
    "musica": "Música en vivo en La Plata: recitales, bandas, conciertos y shows para salir esta semana.",
    "stand-up": "Stand up en La Plata: shows de comedia, ciclos y funciones para reírse esta semana.",
    "danza": "Danza en La Plata: espectáculos, funciones y propuestas escénicas de la semana.",
    "infantil": "Espectáculos infantiles en La Plata: teatro, títeres y propuestas para disfrutar en familia.",
    "taller": "Talleres y cursos culturales en La Plata: clínicas, encuentros y capacitaciones de la semana.",
    "impro": "Impro en La Plata: shows de improvisación, humor y teatro espontáneo para esta semana.",
    "humor": "Humor en vivo en La Plata: comedia, monólogos y propuestas para salir a reírse.",
    "a-plasticas": "Artes plásticas en La Plata: muestras, exposiciones, fotografía y artes visuales.",
    "otros": "Más cosas para hacer en La Plata: actividades culturales, encuentros y propuestas de la semana.",
}


def normalizar_categorias(eventos: list[dict]) -> list[dict]:
    """Conserva compatibilidad con datos viejos sin publicar Actividades."""
    return [
        {**ev, "categoria": "otros"}
        if ev.get("categoria") == "actividades"
        else ev
        for ev in eventos
    ]


def esc(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def parse_fecha(s: str) -> datetime:
    s = str(s or "").strip()
    for fmt, largo in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(s[:largo], fmt)
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: {s}")


def cat_label(cat: str) -> str:
    return CAT_LABEL.get(cat or "otros", (cat or "otros").replace("-", " ").title())


def evento_url(ev: dict) -> str:
    return ev.get("url") or ev.get("link") or ""


def evento_lugar(ev: dict) -> str:
    return ev.get("lugar") or ev.get("venue") or ev.get("Venue Name") or ""


def evento_titulo(ev: dict) -> str:
    return ev.get("titulo") or ev.get("title") or ev.get("Title") or "Sin título"


def evento_fijo_stand_up(referencia: date) -> dict:
    dias_hasta_viernes = (4 - referencia.weekday()) % 7
    viernes = referencia + timedelta(days=dias_hasta_viernes)
    return {
        "titulo": "Sociedad Platense de Stand Up",
        "fecha": f"{viernes.isoformat()} 21:30:00",
        "lugar": "Tres Empanadas Comedia",
        "categoria": "stand-up",
        "url": "https://tresempanadas.com.ar/reservas",
        "destacado": True,
    }


def agregar_evento_fijo_stand_up(eventos: list[dict], referencia: date) -> list[dict]:
    fijo = evento_fijo_stand_up(referencia)
    fecha_fija = fijo["fecha"][:10]
    sin_duplicado = [
        ev for ev in eventos
        if not (
            (
                "sociedad platense de stand up" in evento_titulo(ev).casefold()
                or "tres empanadas" in evento_titulo(ev).casefold()
                or "tres empanadas" in evento_lugar(ev).casefold()
            )
            and str(ev.get("fecha", ""))[:10] == fecha_fija
        )
    ]
    return [fijo, *sin_duplicado]


def render_evento(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    cat = ev.get("categoria", "otros")
    titulo = esc(evento_titulo(ev))
    datos_lugar = venue_info(evento_lugar(ev))
    lugar = esc(datos_lugar["nombre"])
    direccion = str(ev.get("direccion") or datos_lugar["direccion"] or "").strip()
    hora = f.strftime("%H:%M")
    url = esc(evento_url(ev))
    # Si la sala esta en el catalogo, su nombre linkea a su pagina propia.
    vc = venue_canonico(evento_lugar(ev))
    lugar_html = f'<a href="/en-vivo/sala/{vc["slug"]}/">{lugar}</a>' if vc else lugar
    meta = " · ".join(p for p in [f"{hora} hs", lugar_html] if p.strip())
    titulo_html = f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>' if url else titulo
    mapa_html = ""
    if direccion:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(direccion)}"
        mapa_html = f"""
      <a class="map-link event-map-link" href="{esc(maps_url)}" target="_blank" rel="noopener"
         aria-label="Cómo llegar a {lugar} en Google Maps">
        <img class="map-icon" src="/assets/icons/google-maps.svg" alt="">
        <span class="map-copy">
          <span class="map-label">Cómo llegar</span>
          <span class="map-address">{esc(direccion)}</span>
        </span>
      </a>"""

    return f"""
    <article class="event-card" data-category="{esc(cat)}">
      <div class="event-card-topline">
        <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
        <p class="pill">{esc(cat_label(cat))}</p>
      </div>
      <h3>{titulo_html}</h3>
      <p class="event-meta">{meta}</p>
      {mapa_html}
    </article>
    """


def render_esta_semana(eventos_semana: list[dict]) -> str:
    por_dia: dict[date, list[dict]] = defaultdict(list)

    for ev in eventos_semana:
        try:
            por_dia[parse_fecha(ev["fecha"]).date()].append(ev)
        except Exception:
            continue

    if not por_dia:
        return '<p class="empty">No hay eventos cargados para esta semana todavía.</p>'

    bloques = []

    dias_ordenados = sorted(
        por_dia,
        key=lambda dia: (
            0 if any(ev.get("destacado") for ev in por_dia[dia]) else 1,
            dia,
        ),
    )

    for dia in dias_ordenados:
        filas = "\n".join(
            render_evento(ev)
            for ev in sorted(
                por_dia[dia],
                key=lambda e: (0 if e.get("destacado") else 1, e.get("fecha", "")),
            )
        )
        bloques.append(
            f"""
            <section class="day-block" data-filter-section>
              <h2>{esc(etiqueta_dia(dia))}</h2>
              <div class="grid cards">{filas}</div>
            </section>
            """
        )

    return "\n".join(bloques)


def render_lo_que_se_viene(eventos: list[dict], jueves: date) -> str:
    futuros = []
    vistos = set()

    for ev in eventos:
        fecha = ev.get("fecha", "")
        if not fecha or en_esta_semana(fecha, jueves):
            continue

        vm = venue_masivo(evento_lugar(ev))
        if not vm:
            continue

        clave = (evento_titulo(ev).lower().strip(), fecha[:10])
        if clave in vistos:
            continue

        vistos.add(clave)
        futuros.append((ev, vm))

    if not futuros:
        return '<p class="empty">Sin grandes eventos anunciados por ahora.</p>'

    futuros.sort(key=lambda x: x[0].get("fecha", ""))

    cards = []
    for ev, (_clave_venue, nombre_venue) in futuros[:16]:
        f = parse_fecha(ev["fecha"])
        cat = ev.get("categoria", "otros")
        url = esc(evento_url(ev))
        titulo = esc(evento_titulo(ev))
        titulo_html = f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>' if url else titulo
        cards.append(
            f"""
            <article class="event-card future" data-category="{esc(cat)}">
              <div class="event-card-topline">
                <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
                <p class="pill">{esc(cat_label(cat))}</p>
              </div>
              <h3>{titulo_html}</h3>
              <p class="event-meta">{esc(nombre_venue)}</p>
            </article>
            """
        )

    return f'<div class="grid cards">{"".join(cards)}</div>'


def categorias_presentes(eventos_semana: list[dict]) -> list[str]:
    cats: list[str] = []
    for ev in eventos_semana:
        c = ev.get("categoria", "otros")
        if c not in cats:
            cats.append(c)
    prioridad = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    return sorted(cats, key=lambda cat: (prioridad.get(cat, len(prioridad)), cat_label(cat)))


def cargar_eventos(path: str | Path) -> tuple[list[dict], str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, ""
    return data.get("eventos", []), data.get("generado", "")


def contar_categorias_semana(eventos: list[dict], jueves: date) -> dict:
    """Cuenta eventos por categoría dentro de la semana de la edición."""
    cuenta: dict[str, int] = {}
    for ev in eventos:
        if en_esta_semana(ev.get("fecha", ""), jueves):
            cat = ev.get("categoria", "otros")
            cuenta[cat] = cuenta.get(cat, 0) + 1
    return cuenta


def elegir_antiheroes(eventos: list[dict], jueves: date, cuentas: dict, n: int = 3) -> list[dict]:
    """Los antihéroes: eventos de las categorías más chicas de la semana
    (1-2 eventos), elegidos al azar. Le damos la vidriera a lo menos masivo."""
    chicas = {c for c, q in cuentas.items() if 0 < q <= 2 and c != "otros"}
    pool = [
        ev for ev in eventos
        if en_esta_semana(ev.get("fecha", ""), jueves)
        and ev.get("categoria", "otros") in chicas
    ]
    if not pool:
        return []
    rng = random.Random("antiheroes-" + jueves.isoformat())
    rng.shuffle(pool)
    return pool[:n]


def render_antiheroes(eventos_ah: list[dict]) -> str:
    if not eventos_ah:
        return ""
    cards = "\n".join(render_evento(ev) for ev in eventos_ah)
    return f"""
    <section id="antiheroes" class="section antiheroes" aria-label="Antihéroes de la semana">
      <p class="eyebrow antiheroes-eyebrow">★ Antihéroes de la semana</p>
      <h2>Los que casi nadie mira</h2>
      <p class="antiheroes-sub">Lo más chico y menos masivo de la semana, elegido al azar. Bancá la escena. 💛</p>
      <div class="grid cards">{cards}</div>
    </section>
    """


def category_nav(categoria_activa: str | None = None, cuentas: dict | None = None) -> str:
    """Menú dinámico: solo las categorías con eventos esta semana. Las grandes
    van de botón; las chicas (y 'otros') se agrupan en 'Más'."""
    cuentas = cuentas or {}
    presentes = [c for c in CATEGORY_ORDER if cuentas.get(c, 0) > 0]

    botones = [c for c in presentes if cuentas.get(c, 0) >= 3 and c != "otros"]
    if len(botones) < 3:
        for c in sorted(presentes, key=lambda x: -cuentas.get(x, 0)):
            if c not in botones and c != "otros" and len(botones) < 3:
                botones.append(c)
    botones = [c for c in CATEGORY_ORDER if c in botones]
    en_mas = [c for c in presentes if c not in botones]
    if categoria_activa and categoria_activa not in botones and categoria_activa not in en_mas:
        en_mas.append(categoria_activa)

    def link(c):
        activa = c == categoria_activa
        return '<a class="filter-button{}" href="/en-vivo/{}/"{}>{}</a>'.format(
            " is-active" if activa else "",
            esc(c),
            ' aria-current="page"' if activa else "",
            esc(cat_label(c)),
        )

    links = [
        '<a class="filter-button{}" href="/en-vivo/"{}>Todas</a>'.format(
            " is-active" if categoria_activa is None else "",
            ' aria-current="page"' if categoria_activa is None else "",
        )
    ]
    links += [link(c) for c in botones]
    if en_mas:
        extra_activo = categoria_activa in en_mas
        links.append(
            '<details class="category-more">'
            f'<summary class="filter-button{" is-active" if extra_activo else ""}">Más</summary>'
            f'<div class="category-more-menu">{"".join(link(c) for c in en_mas)}</div>'
            '</details>'
        )
    return "\n".join(links)


def _es_finde(fecha_str, jueves) -> bool:
    """True si el evento cae sábado o domingo."""
    try:
        f = datetime.strptime(str(fecha_str)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return f.weekday() in (5, 6)


def elegir_destacado_under(eventos: list[dict], jueves: date) -> dict | None:
    """Elige AL AZAR (estable por semana) un evento de teatro independiente
    del finde, en sala chica, para darle la vidriera a lo under.

    Filosofía: para el ojo humano, lo chico. Cada semana le toca a uno
    distinto, elegido al azar entre la escena independiente.
    """
    def candidatos(solo_finde: bool, solo_teatro: bool) -> list[dict]:
        out = []
        for ev in eventos:
            fecha = ev.get("fecha", "")
            if not fecha or not en_esta_semana(fecha, jueves):
                continue
            if solo_teatro and ev.get("categoria", "otros") != "teatro":
                continue
            lugar = evento_lugar(ev)
            if venue_masivo(lugar):
                continue  # las salas masivas no son "lo chico"
            if (
                "tres empanadas" in lugar.casefold()
                or "tres empanadas" in evento_titulo(ev).casefold()
            ):
                continue  # el show propio va como promo, no como destacado editorial
            if solo_finde and not _es_finde(fecha, jueves):
                continue
            out.append(ev)
        return out

    pool = (
        candidatos(solo_finde=True, solo_teatro=True)
        or candidatos(solo_finde=False, solo_teatro=True)
        or candidatos(solo_finde=True, solo_teatro=False)
        or candidatos(solo_finde=False, solo_teatro=False)
    )
    if not pool:
        return None
    return random.Random(jueves.isoformat()).choice(pool)


def render_destacado_under(ev: dict | None) -> str:
    if not ev:
        return ""
    f = parse_fecha(ev["fecha"])
    datos = venue_info(evento_lugar(ev))
    lugar = esc(datos["nombre"])
    direccion = str(ev.get("direccion") or datos["direccion"] or "").strip()
    titulo = esc(evento_titulo(ev))
    url = esc(evento_url(ev))
    titulo_html = (
        f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>' if url else titulo
    )
    hora = f.strftime("%H:%M")
    cuando = f"{etiqueta_dia(f.date())} · {hora} hs"
    mapa = ""
    if direccion:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(direccion)}"
        mapa = (
            f'<a class="map-link" href="{esc(maps_url)}" target="_blank" rel="noopener" '
            f'aria-label="Cómo llegar a {lugar} en Google Maps">'
            '<img class="map-icon" src="/assets/icons/google-maps.svg" alt="">'
            '<span class="map-copy"><span class="map-label">Cómo llegar</span>'
            f'<span class="map-address">{esc(direccion)}</span></span></a>'
        )
    return f"""
    <section class="destacado-under" aria-label="Destacado de la semana">
      <p class="destacado-eyebrow">◆ Destacado de la semana · Teatro independiente</p>
      <article class="destacado-card">
        <p class="destacado-when">{esc(cuando)}</p>
        <h2 class="destacado-title">{titulo_html}</h2>
        <p class="destacado-venue">{lugar}</p>
        {mapa}
      </article>
    </section>
"""


def render_schema_eventos(eventos_semana: list[dict]) -> str:
    """JSON-LD (Schema.org) con los eventos de la semana, para que Google los
    entienda y los muestre como resultados ricos."""
    items = []
    for i, ev in enumerate(eventos_semana[:40], 1):
        try:
            f = parse_fecha(ev["fecha"])
        except Exception:
            continue
        datos = venue_info(evento_lugar(ev))
        lugar_ld = {"@type": "Place", "name": datos["nombre"]}
        addr = str(ev.get("direccion") or datos["direccion"] or "").strip()
        if addr:
            lugar_ld["address"] = addr
        ev_ld = {
            "@type": "Event",
            "name": evento_titulo(ev),
            "startDate": f.isoformat(),
            "eventStatus": "https://schema.org/EventScheduled",
            "location": lugar_ld,
        }
        url = evento_url(ev)
        if url:
            ev_ld["url"] = url
        items.append({"@type": "ListItem", "position": i, "item": ev_ld})
    if not items:
        return ""
    data = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": items}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def render_html(
    eventos: list[dict],
    generado: str,
    hoy: date | None = None,
    categoria: str | None = None,
) -> tuple[str, dict]:
    hoy = hoy or date.today()
    eventos = normalizar_categorias(eventos)
    if categoria == "actividades":
        categoria = "otros"
    jueves = jueves_de_edicion(hoy)
    slug = slug_edicion(jueves)

    eventos = [ev for ev in eventos if ev.get("categoria") != "cine" and ev.get("fecha")]
    cuentas = contar_categorias_semana(eventos, jueves)
    bloque_destacado = (
        render_destacado_under(elegir_destacado_under(eventos, jueves))
        if not categoria else ""
    )
    bloque_antiheroes = (
        render_antiheroes(elegir_antiheroes(eventos, jueves, cuentas))
        if not categoria else ""
    )
    if categoria:
        eventos = [ev for ev in eventos if ev.get("categoria", "otros") == categoria]
    if categoria == "stand-up":
        eventos = agregar_evento_fijo_stand_up(eventos, jueves + timedelta(days=1))
    semana = [
        ev for ev in eventos
        if ev.get("destacado") or en_esta_semana(ev["fecha"], jueves)
    ]
    semana.sort(key=lambda e: (0 if e.get("destacado") else 1, e.get("fecha", "")))

    rango = etiqueta_rango(jueves)
    categoria_label = cat_label(categoria) if categoria else ""
    seo_titles = {
        "teatro": f"Teatro en La Plata esta semana · Obras, salas y funciones · MoVeTe",
        "musica": f"Música en vivo en La Plata · Recitales y shows · MoVeTe",
        "stand-up": f"Stand up en La Plata · Shows de comedia esta semana · MoVeTe",
        "otros": f"Más cosas para hacer en La Plata · Cartelera cultural · MoVeTe",
    }
    seo_descriptions = {
        "teatro": f"Cartelera de teatro en La Plata para la semana del {rango}: obras, salas independientes, unipersonales y funciones.",
        "musica": f"Música en vivo en La Plata para la semana del {rango}: recitales, bandas, conciertos y shows.",
        "stand-up": f"Stand up en La Plata para la semana del {rango}: shows de comedia, ciclos y funciones.",
        "otros": f"Más cosas para hacer en La Plata durante la semana del {rango}: actividades culturales, encuentros y propuestas.",
    }
    seo_h1 = {
        "teatro": "Teatro en La Plata esta semana",
        "musica": "Música en vivo en La Plata",
        "stand-up": "Stand up en La Plata",
        "otros": "Más cosas para hacer en La Plata",
    }

    page_title = (
        seo_titles.get(categoria, f"{categoria_label} en La Plata · {rango} · MoVeTe")
        if categoria
        else f"Qué hacer en La Plata esta semana · Teatro, música, stand up y más · MoVeTe"
    )
    page_description = (
        seo_descriptions.get(categoria, f"Cartelera de {categoria_label.lower()} en La Plata. Edición semanal {rango}.")
        if categoria
        else f"Qué hacer en La Plata esta semana: teatro, música en vivo, stand up, danza, talleres y espectáculos. Edición semanal {rango}."
    )
    h1 = seo_h1.get(categoria, f"{categoria_label} en La Plata") if categoria else "Qué hacer en La Plata esta semana"
    eyebrow = f"{categoria_label} · Edición {slug}" if categoria else f"En vivo · Edición {slug}"
    page_url = f"https://movete.info/en-vivo/{categoria}/" if categoria else "https://movete.info/en-vivo/"
    og_image = "https://movete.info/assets/images/cartelera-en-vivo.jpg"
    page_intro = CAT_INTRO_MAIN if not categoria else CAT_INTRO.get(
        categoria, f"Cartelera de {categoria_label.lower()} en La Plata, semana a semana."
    )
    bloque_schema = render_schema_eventos(semana)

    html_doc = PLANTILLA.format(
        slug=esc(slug),
        rango=esc(rango),
        total=len(semana),
        category_nav=category_nav(categoria, cuentas),
        bloque_semana=render_esta_semana(semana),
        bloque_futuro=render_lo_que_se_viene(eventos, jueves),
        generado=esc(generado),
        anio=jueves.year,
        page_title=esc(page_title),
        page_description=esc(page_description),
        h1=esc(h1),
        eyebrow=esc(eyebrow),
        bloque_destacado=bloque_destacado,
        bloque_antiheroes=bloque_antiheroes,
        bloque_schema=bloque_schema,
        page_url=esc(page_url),
        og_image=og_image,
        page_intro=esc(page_intro),
    )

    return html_doc, {
        "slug": slug,
        "rango": rango,
        "esta_semana": len(semana),
        "categoria": categoria or "todas",
    }


def _pagina_categoria_vacia(categoria: str, jueves: date) -> str:
    """Página noindex para una categoría sin eventos esta semana: evita
    404 en links viejos y no genera contenido flaco que a Google no le gusta."""
    label = cat_label(categoria)
    return f"""<!doctype html>
<html lang="es-AR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, follow">
  <link rel="canonical" href="https://movete.info/en-vivo/">
  <title>{esc(label)} en La Plata · MoVeTe</title>
  <meta name="description" content="Esta semana no hay {esc(label.lower())} en la cartelera en vivo de La Plata. Mirá el resto en MoVeTe.">
  <link rel="stylesheet" href="/assets/css/movete.css">
</head>
<body id="top">
  <header class="site-header">
    <a class="brand" href="/">MoVeTe<span>●</span></a>
    <nav class="site-nav" aria-label="Secciones principales">
      <a href="/">Inicio</a>
      <a href="/cine/">Cine</a>
      <a href="/en-vivo/" aria-current="page">En vivo</a>
    </nav>
  </header>
  <main>
    <section class="hero compact">
      <p class="eyebrow">En vivo</p>
      <h1>{esc(label)} en La Plata</h1>
    </section>
    <p class="empty">Esta semana no hay {esc(label.lower())} en cartelera. Volvé a mirar la semana que viene, o descubrí el resto de la movida.</p>
    <p><a class="button small" href="/en-vivo/">Ver toda la cartelera</a></p>
  </main>
</body>
</html>
"""


def generar_sitemap(en_vivo_dir: Path) -> None:
    """Regenera sitemap.xml: páginas fijas, categorías vigentes (indexables) y
    TODAS las ediciones archivadas de cine y en-vivo (URLs permanentes)."""
    root = Path(en_vivo_dir).parent
    base = "https://movete.info"

    def es_fecha(nombre: str) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", nombre))

    urls: list[tuple[str, str]] = [("/", ""), ("/cine/", ""), ("/cine/pelis/", ""), ("/en-vivo/", "")]

    # Categorías de en-vivo con página indexable (se saltan las noindex/vacías)
    envivo = root / "en-vivo"
    if envivo.is_dir():
        for sub in sorted(envivo.iterdir()):
            if not sub.is_dir() or es_fecha(sub.name) or sub.name == "actividades":
                continue
            idx = sub / "index.html"
            if idx.exists() and "noindex" not in idx.read_text(encoding="utf-8")[:900]:
                urls.append((f"/en-vivo/{sub.name}/", ""))

    # Ediciones archivadas (URLs permanentes) de cine y en-vivo
    for seccion in ("cine", "en-vivo"):
        d = root / seccion
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and es_fecha(sub.name):
                urls.append((f"/{seccion}/{sub.name}/", sub.name))

    # Páginas por sala (evergreen, indexables)
    sala_dir = root / "en-vivo" / "sala"
    if sala_dir.is_dir():
        for sub in sorted(sala_dir.iterdir()):
            if sub.is_dir() and (sub / "index.html").exists():
                urls.append((f"/en-vivo/sala/{sub.name}/", ""))

    vistos: set[str] = set()
    lineas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lastmod in urls:
        if loc in vistos:
            continue
        vistos.add(loc)
        if lastmod:
            lineas.append(f"  <url><loc>{base}{loc}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            lineas.append(f"  <url><loc>{base}{loc}</loc></url>")
    lineas.append("</urlset>")
    try:
        (root / "sitemap.xml").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[sitemap] no se pudo escribir: {e}")


def render_pagina_venue(venue: dict, eventos_sala: list[dict], jueves: date) -> str:
    """Pagina evergreen de una sala: /en-vivo/sala/<slug>/."""
    nombre = venue["nombre"]
    slug = venue["slug"]
    direccion = (venue.get("direccion") or "").strip()
    page_url = f"https://movete.info/en-vivo/sala/{slug}/"
    n = len(eventos_sala)

    page_title = f"Qué hay en {nombre} · La Plata · MoVeTe"
    page_description = (
        f"Agenda de {nombre} en La Plata: próximas funciones, shows y eventos."
        + (f" Dirección: {direccion}." if direccion else "")
    )
    eyebrow = "Espacio en La Plata" if venue.get("masivo") else "Sala en La Plata"

    bloque_mapa = ""
    if direccion:
        maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(direccion)}"
        bloque_mapa = f"""
      <a class="map-link event-map-link" href="{esc(maps_url)}" target="_blank" rel="noopener"
         aria-label="Cómo llegar a {esc(nombre)} en Google Maps">
        <img class="map-icon" src="/assets/icons/google-maps.svg" alt="">
        <span class="map-copy">
          <span class="map-label">Cómo llegar</span>
          <span class="map-address">{esc(direccion)}</span>
        </span>
      </a>"""

    if eventos_sala:
        bloque_eventos = "".join(render_evento(e) for e in eventos_sala)
        titulo_agenda = f"Próximas funciones ({n})"
    else:
        bloque_eventos = ('<p class="empty">Por ahora no hay funciones cargadas en '
                          'esta sala. Volvé a mirar la semana que viene.</p>')
        titulo_agenda = "Agenda"

    place = {"@context": "https://schema.org", "@type": "Place",
             "name": nombre, "url": page_url}
    if direccion:
        place["address"] = {"@type": "PostalAddress", "streetAddress": direccion,
                            "addressLocality": "La Plata", "addressRegion": "Buenos Aires",
                            "addressCountry": "AR"}
    schema = '<script type="application/ld+json">' + json.dumps(place, ensure_ascii=False) + "</script>"
    if eventos_sala:
        schema += render_schema_eventos(eventos_sala)

    return PLANTILLA_VENUE.format(
        page_title=esc(page_title),
        page_description=esc(page_description),
        page_url=esc(page_url),
        og_image="https://movete.info/assets/images/cartelera-en-vivo.jpg",
        bloque_schema=schema,
        eyebrow=esc(eyebrow),
        h1=esc(nombre),
        bloque_mapa=bloque_mapa,
        titulo_agenda=esc(titulo_agenda),
        bloque_eventos=bloque_eventos,
        anio=jueves.year,
    )


def generar(eventos_json_path: str, output_dir: str, hoy: date | None = None) -> dict:
    eventos, generado = cargar_eventos(eventos_json_path)
    html_doc, info = render_html(eventos, generado, hoy=hoy)

    jueves = jueves_de_edicion(hoy or date.today())
    eventos_semana = [
        e for e in normalizar_categorias(eventos)
        if e.get("categoria") != "cine" and e.get("fecha")
    ]
    cuentas = contar_categorias_semana(eventos_semana, jueves)

    out = Path(output_dir)
    slug_dir = out / info["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)

    archive_index = slug_dir / "index.html"
    current_index = out / "index.html"

    archive_index.write_text(html_doc, encoding="utf-8")
    current_index.write_text(html_doc, encoding="utf-8")

    salidas_categoria = []
    for categoria in CATEGORY_ORDER:
        if cuentas.get(categoria, 0) > 0 or categoria == "stand-up":
            categoria_html, _ = render_html(
                eventos,
                generado,
                hoy=hoy,
                categoria=categoria,
            )
        else:
            categoria_html = _pagina_categoria_vacia(categoria, jueves)
        categoria_index = out / categoria / "index.html"
        categoria_index.parent.mkdir(parents=True, exist_ok=True)
        categoria_index.write_text(categoria_html, encoding="utf-8")
        salidas_categoria.append(str(categoria_index))

    legacy_dir = out / "actividades"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "index.html").write_text(
        """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="robots" content="noindex">
  <meta http-equiv="refresh" content="0; url=/en-vivo/otros/">
  <link rel="canonical" href="https://movete.info/en-vivo/otros/">
  <title>Otros en La Plata · MoVeTe</title>
</head>
<body><p><a href="/en-vivo/otros/">Ver Otros en MoVeTe</a></p></body>
</html>
""",
        encoding="utf-8",
    )

    # Páginas por sala (evergreen): agrupar todos los eventos futuros por venue
    # del catálogo. Las salas no cataloguadas o genéricas ('La Plata') no generan página.
    eventos_por_sala: dict[str, dict] = {}
    for ev in normalizar_categorias(eventos):
        if ev.get("categoria") == "cine" or not ev.get("fecha"):
            continue
        vc = venue_canonico(evento_lugar(ev))
        if not vc:
            continue
        entrada = eventos_por_sala.setdefault(vc["slug"], {"venue": vc, "eventos": []})
        entrada["eventos"].append(ev)

    salidas_venue = []
    sala_root = out / "sala"
    for slug, data in eventos_por_sala.items():
        evs = sorted(data["eventos"], key=lambda e: e.get("fecha", ""))
        pagina = render_pagina_venue(data["venue"], evs, jueves)
        destino = sala_root / slug / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(pagina, encoding="utf-8")
        salidas_venue.append(str(destino))

    generar_sitemap(out)

    return {
        **info,
        "salida_actual": str(current_index),
        "salida_archivo": str(archive_index),
        "salidas_categoria": salidas_categoria,
        "salidas_venue": salidas_venue,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera En Vivo para MoVeTe")
    parser.add_argument("--eventos", default="eventos.json")
    parser.add_argument("--output", default="../Movete-info/en-vivo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    info = generar(args.eventos, args.output)
    print(json.dumps(info, ensure_ascii=False, indent=2))


PLANTILLA = """<!doctype html>
<html lang="es-AR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <meta name="description" content="{page_description}">
  <link rel="canonical" href="{page_url}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="MoVeTe">
  <meta property="og:title" content="{page_title}">
  <meta property="og:description" content="{page_description}">
  <meta property="og:url" content="{page_url}">
  <meta property="og:image" content="{og_image}">
  <meta name="twitter:card" content="summary_large_image">
  {bloque_schema}
  <link rel="stylesheet" href="/assets/css/movete.css">
</head>
<body id="top">
  <header class="site-header">
    <a class="brand" href="/">MoVeTe<span>●</span></a>
    <nav class="site-nav" aria-label="Secciones principales">
      <a href="/">Inicio</a>
      <a href="/cine/">Cine</a>
      <a href="/en-vivo/" aria-current="page">En vivo</a>
    </nav>
  </header>

  <nav id="categorias" class="pill-row filter-bar edition-filters sticky-category-nav" aria-label="Categorías de la cartelera">
    {category_nav}
  </nav>

  <main>
    <section class="hero compact">
      <p class="eyebrow">{eyebrow}</p>
      <h1>{h1}</h1>
      <p class="lead">{page_intro}</p>
    </section>

    <section class="ad-box sponsor-card">
      <div class="sponsor-kicker">
        <img class="sponsor-logo" src="/assets/images/tres-empanadas-comedia.png" alt="">
        <p class="ad-label">Espacio promocional</p>
      </div>
      <h2>Tres Empanadas Comedia</h2>
      <p>Stand up en La Plata. Shows a la gorra, todos los viernes.</p>
      <a class="button small" href="https://tresempanadas.com.ar/reservas">Más info</a>
    </section>

    {bloque_destacado}

    <div class="section-shortcuts" aria-label="Saltos de la edición">
      <a href="#esta-semana">Esta semana</a>
      <a href="#lo-que-se-viene">Lo que viene</a>
    </div>

    <section id="esta-semana" class="section">
      <p class="eyebrow">Cartelera semanal</p>
      <h2>Qué hay esta semana en La Plata</h2>
      {bloque_semana}
    </section>

    <section id="lo-que-se-viene" class="section">
      <p class="eyebrow">Anticipadas</p>
      <h2>Lo que viene</h2>
      {bloque_futuro}
    </section>

    {bloque_antiheroes}

    <section class="card">
      <p class="tag">También en MoVeTe</p>
      <h2>Cartelera de cine</h2>
      <a href="/cine/">Ver cartelera de cine →</a>
    </section>

    <p class="site-notice">La info puede cambiar. Confirmá horarios y disponibilidad con cada sala o espacio; reservá o sacá entradas según corresponda.</p>
  </main>

  <footer class="site-footer">
    <p class="footer-line">
      <span class="footer-brand">MoVeTe<span>.</span></span>
      <span aria-hidden="true">·</span>
      <span>La Plata</span>
      <span aria-hidden="true">·</span>
      <span>{anio}</span>
      <span aria-hidden="true">·</span>
      <button class="footer-share" type="button" data-share-page title="Avisá que existimos por WhatsApp" aria-label="Avisá que existimos por WhatsApp">Avisá que existimos <img class="share-icon" src="/assets/icons/whatsapp.svg" alt=""></button>
    </p>
  </footer>
  <script src="/assets/js/movete.js" defer></script>
</body>
</html>
"""


PLANTILLA_VENUE = """<!doctype html>
<html lang="es-AR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <meta name="description" content="{page_description}">
  <link rel="canonical" href="{page_url}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="MoVeTe">
  <meta property="og:title" content="{page_title}">
  <meta property="og:description" content="{page_description}">
  <meta property="og:url" content="{page_url}">
  <meta property="og:image" content="{og_image}">
  <meta name="twitter:card" content="summary_large_image">
  {bloque_schema}
  <link rel="stylesheet" href="/assets/css/movete.css">
</head>
<body id="top">
  <header class="site-header">
    <a class="brand" href="/">MoVeTe<span>●</span></a>
    <nav class="site-nav" aria-label="Secciones principales">
      <a href="/">Inicio</a>
      <a href="/cine/">Cine</a>
      <a href="/en-vivo/" aria-current="page">En vivo</a>
    </nav>
  </header>

  <main>
    <section class="hero compact">
      <p class="eyebrow">{eyebrow}</p>
      <h1>{h1}</h1>
      {bloque_mapa}
    </section>

    <section class="section">
      <h2>{titulo_agenda}</h2>
      {bloque_eventos}
    </section>

    <p class="site-notice">La info puede cambiar. Confirmá horarios y disponibilidad con la sala.</p>
    <p style="margin-top:24px"><a href="/en-vivo/">← Volver a la cartelera de En Vivo</a></p>
  </main>

  <footer class="site-footer">
    <p class="footer-line">
      <span class="footer-brand">MoVeTe<span>.</span></span>
      <span aria-hidden="true">·</span>
      <span>La Plata</span>
      <span aria-hidden="true">·</span>
      <span>{anio}</span>
    </p>
  </footer>
  <script src="/assets/js/movete.js" defer></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
