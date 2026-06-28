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
from collections import defaultdict
from datetime import date, datetime
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
from venues import venue_info, venue_masivo


CAT_LABEL = {
    "teatro": "Teatro",
    "musica": "Música",
    "stand-up": "Stand Up",
    "danza": "Danza",
    "cine": "Cine",
    "infantil": "Infantil",
    "taller": "Taller",
    "a-plasticas": "Artes plásticas",
    "actividades": "Actividades",
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
    "actividades",
    "otros",
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


def render_evento(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    cat = ev.get("categoria", "otros")
    titulo = esc(evento_titulo(ev))
    datos_lugar = venue_info(evento_lugar(ev))
    lugar = esc(datos_lugar["nombre"])
    direccion = str(ev.get("direccion") or datos_lugar["direccion"] or "").strip()
    hora = f.strftime("%H:%M")
    url = esc(evento_url(ev))
    meta = " · ".join(p for p in [f"{hora} hs", lugar] if p.strip())
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
      <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
      <h3>{titulo_html}</h3>
      <p class="event-meta">{esc(meta)}</p>
      {mapa_html}
      <p class="pill">{esc(cat_label(cat))}</p>
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

    for dia in sorted(por_dia):
        filas = "\n".join(
            render_evento(ev)
            for ev in sorted(por_dia[dia], key=lambda e: e.get("fecha", ""))
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
        url = esc(evento_url(ev))
        titulo = esc(evento_titulo(ev))
        titulo_html = f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>' if url else titulo
        cards.append(
            f"""
            <article class="event-card future">
              <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
              <h3>{titulo_html}</h3>
              <p class="event-meta">{esc(nombre_venue)}</p>
              <p class="pill">Gran evento</p>
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


def category_nav(
    categoria_activa: str | None = None,
    categorias_disponibles: list[str] | None = None,
) -> str:
    principales = ["stand-up", "teatro", "musica"]
    disponibles = set(categorias_disponibles or [])
    adicionales = [
        cat for cat in CATEGORY_ORDER
        if cat not in principales and (cat in disponibles or cat == categoria_activa)
    ]
    links = [
        '<a class="filter-button{}" href="/en-vivo/"{}>Todas</a>'.format(
            " is-active" if categoria_activa is None else "",
            ' aria-current="page"' if categoria_activa is None else "",
        )
    ]
    for categoria in principales:
        activa = categoria == categoria_activa
        links.append(
            '<a class="filter-button{}" href="/en-vivo/{}/"{}>{}</a>'.format(
                " is-active" if activa else "",
                esc(categoria),
                ' aria-current="page"' if activa else "",
                esc(cat_label(categoria)),
            )
        )
    if adicionales:
        extra_links = []
        for categoria in adicionales:
            activa = categoria == categoria_activa
            extra_links.append(
                '<a class="filter-button{}" href="/en-vivo/{}/"{}>{}</a>'.format(
                    " is-active" if activa else "",
                    esc(categoria),
                    ' aria-current="page"' if activa else "",
                    esc(cat_label(categoria)),
                )
            )
        extra_activo = categoria_activa in adicionales
        links.append(
            '<details class="category-more">'
            f'<summary class="filter-button{" is-active" if extra_activo else ""}">Más</summary>'
            f'<div class="category-more-menu">{"".join(extra_links)}</div>'
            '</details>'
        )
    return "\n".join(links)


def render_html(
    eventos: list[dict],
    generado: str,
    hoy: date | None = None,
    categoria: str | None = None,
) -> tuple[str, dict]:
    hoy = hoy or date.today()
    jueves = jueves_de_edicion(hoy)
    slug = slug_edicion(jueves)

    eventos = [ev for ev in eventos if ev.get("categoria") != "cine" and ev.get("fecha")]
    categorias_disponibles = categorias_presentes(eventos)
    if categoria:
        eventos = [ev for ev in eventos if ev.get("categoria", "otros") == categoria]
    semana = [ev for ev in eventos if en_esta_semana(ev["fecha"], jueves)]
    semana.sort(key=lambda e: e.get("fecha", ""))

    rango = etiqueta_rango(jueves)
    categoria_label = cat_label(categoria) if categoria else ""
    page_title = (
        f"{categoria_label} en La Plata · {rango} · MoVeTe"
        if categoria
        else f"Cartelera en vivo en La Plata · {rango} · MoVeTe"
    )
    page_description = (
        f"Cartelera de {categoria_label.lower()} en La Plata. Edición semanal {rango}."
        if categoria
        else f"Cartelera en vivo de La Plata: teatro, música, stand up, danza, talleres y eventos. Edición semanal {rango}."
    )
    h1 = f"{categoria_label} en La Plata" if categoria else "Cartelera en vivo en La Plata"
    eyebrow = f"{categoria_label} · Edición {slug}" if categoria else f"En vivo · Edición {slug}"

    html_doc = PLANTILLA.format(
        slug=esc(slug),
        rango=esc(rango),
        total=len(semana),
        category_nav=category_nav(categoria, categorias_disponibles),
        bloque_semana=render_esta_semana(semana),
        bloque_futuro=render_lo_que_se_viene(eventos, jueves),
        generado=esc(generado),
        anio=jueves.year,
        page_title=esc(page_title),
        page_description=esc(page_description),
        h1=esc(h1),
        eyebrow=esc(eyebrow),
    )

    return html_doc, {
        "slug": slug,
        "rango": rango,
        "esta_semana": len(semana),
        "categoria": categoria or "todas",
    }


def generar(eventos_json_path: str, output_dir: str, hoy: date | None = None) -> dict:
    eventos, generado = cargar_eventos(eventos_json_path)
    html_doc, info = render_html(eventos, generado, hoy=hoy)

    out = Path(output_dir)
    slug_dir = out / info["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)

    archive_index = slug_dir / "index.html"
    current_index = out / "index.html"

    archive_index.write_text(html_doc, encoding="utf-8")
    current_index.write_text(html_doc, encoding="utf-8")

    salidas_categoria = []
    for categoria in CATEGORY_ORDER:
        categoria_html, _ = render_html(
            eventos,
            generado,
            hoy=hoy,
            categoria=categoria,
        )
        categoria_index = out / categoria / "index.html"
        categoria_index.parent.mkdir(parents=True, exist_ok=True)
        categoria_index.write_text(categoria_html, encoding="utf-8")
        salidas_categoria.append(str(categoria_index))

    return {
        **info,
        "salida_actual": str(current_index),
        "salida_archivo": str(archive_index),
        "salidas_categoria": salidas_categoria,
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
      <div class="actions quick-nav">
        <button class="button small" type="button" data-share-page><img class="share-icon" src="/assets/icons/whatsapp.svg" alt="">Compartir</button>
      </div>
    </section>

    <section class="ad-box live-sponsor">
      <p class="ad-label">Espacio promocional</p>
      <h2>Tres Empanadas Comedia</h2>
      <p>Stand up en La Plata. Shows a la gorra, todos los viernes.</p>
      <a class="button small" href="https://tresempanadas.com.ar/reservas">Reservar</a>
    </section>

    <div class="section-shortcuts" aria-label="Saltos de la edición">
      <a href="#esta-semana">Esta semana</a>
      <a href="#lo-que-se-viene">Lo que viene</a>
    </div>

    <section id="esta-semana" class="section">
      <p class="eyebrow">Cartelera semanal</p>
      <h2>Esta semana</h2>
      {bloque_semana}
    </section>

    <section id="lo-que-se-viene" class="section">
      <p class="eyebrow">Anticipadas</p>
      <h2>Lo que viene</h2>
      {bloque_futuro}
    </section>

    <section class="card">
      <p class="tag">También en MoVeTe</p>
      <h2>Cartelera de cine</h2>
      <a href="/cine/">Ver cartelera de cine →</a>
    </section>

    <p class="site-notice">La info puede cambiar. Confirmá horarios y disponibilidad con cada sala o espacio; reservá o sacá entradas según corresponda.</p>
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <div>
        <p class="footer-title">MoVeTe.info</p>
      </div>
      <div class="footer-links" aria-label="Links del pie">
        <a href="#top">Arriba</a>
        <a href="#esta-semana">Esta semana</a>
        <a href="#lo-que-se-viene">Lo que viene</a>
        <a href="/cine/">Cine</a>
        <button type="button" data-share-page><img class="share-icon" src="/assets/icons/whatsapp.svg" alt="">Compartir</button>
      </div>
    </div>
  </footer>
  <script src="/assets/js/movete.js" defer></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
