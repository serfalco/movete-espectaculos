"""Generador estático de la edición semanal En Vivo de MoVeTe.

Entrada: eventos.json generado por movete-scraper.
Salida:
  - <out>/index.html
  - <out>/<slug>/index.html

Ejemplo:
  python generar_edicion.py eventos.json ../Movete-info/en-vivo
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from edicion import (
    MESES_ABR,
    en_esta_semana,
    etiqueta_dia,
    etiqueta_rango,
    jueves_de_edicion,
    slug_edicion,
)
from venues import venue_masivo

CAT_LABEL = {
    "teatro": "Teatro",
    "musica": "Música",
    "stand-up": "Stand-up",
    "danza": "Danza",
    "cine": "Cine",
    "infantil": "Infantil",
    "taller": "Taller",
    "a-plasticas": "Artes plásticas",
    "impro": "Impro",
    "otros": "Otros",
}


def esc(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def parse_fecha(s: str) -> datetime:
    # Acepta "YYYY-MM-DD HH:MM:SS" o ISO básico.
    s = s.replace("T", " ")[:19]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def cat_label(cat: str) -> str:
    return CAT_LABEL.get(cat, cat.replace("-", " ").title())


def render_evento(ev: dict) -> str:
    f = parse_fecha(ev["fecha"])
    cat = ev.get("categoria", "otros")
    titulo = esc(ev.get("titulo", ""))
    lugar = esc(ev.get("lugar", ""))
    hora = f.strftime("%H:%M")
    url = ev.get("url", "")
    meta = " · ".join(p for p in [f"{hora} hs", lugar] if p.strip())
    titulo_html = f'<a href="{esc(url)}" rel="nofollow noopener">{titulo}</a>' if url else titulo

    return f"""
      <article class="event-card" data-cat="{esc(cat)}">
        <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
        <h3>{titulo_html}</h3>
        <p class="event-meta">{meta}</p>
        <p class="event-cat">{esc(cat_label(cat))}</p>
      </article>
    """


def render_esta_semana(eventos_semana: list[dict]) -> str:
    por_dia: dict[date, list[dict]] = defaultdict(list)
    for ev in eventos_semana:
        por_dia[parse_fecha(ev["fecha"]).date()].append(ev)

    bloques = []
    for dia in sorted(por_dia):
        filas = "\n".join(render_evento(ev) for ev in sorted(por_dia[dia], key=lambda e: e["fecha"]))
        bloques.append(
            f"""
            <section class="day-block">
              <h3>{esc(etiqueta_dia(dia))}</h3>
              <div class="event-grid">{filas}</div>
            </section>
            """
        )

    if not bloques:
        return '<p class="empty">No hay eventos cargados para esta semana todavía.</p>'

    return "\n".join(bloques)


def render_lo_que_se_viene(eventos: list[dict], jueves: date) -> str:
    futuros = []
    vistos = set()

    for ev in eventos:
        if not ev.get("fecha"):
            continue
        if en_esta_semana(ev["fecha"], jueves):
            continue
        vm = venue_masivo(ev.get("lugar", ""))
        if not vm:
            continue
        clave = (ev.get("titulo", "").lower(), ev["fecha"][:10])
        if clave in vistos:
            continue
        vistos.add(clave)
        futuros.append((ev, vm))

    if not futuros:
        return '<p class="empty">Sin grandes eventos anunciados por ahora.</p>'

    futuros.sort(key=lambda x: x[0]["fecha"])
    filas = []
    for ev, (_clave_venue, nombre_venue) in futuros[:16]:
        f = parse_fecha(ev["fecha"])
        filas.append(
            f"""
            <article class="event-card future-card">
              <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
              <h3>{esc(ev.get('titulo', ''))}</h3>
              <p class="event-meta">{esc(nombre_venue)}</p>
              <p class="event-cat">Gran evento</p>
            </article>
            """
        )

    return f'<div class="event-grid">{"".join(filas)}</div>'


def categorias_presentes(eventos_semana: list[dict]) -> list[str]:
    cats = []
    for ev in eventos_semana:
        c = ev.get("categoria", "otros")
        if c not in cats:
            cats.append(c)
    return cats


def generar(eventos_json_path: str | Path, salida_dir: str | Path, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    jueves = jueves_de_edicion(hoy)
    slug = slug_edicion(jueves)
    salida_dir = Path(salida_dir)
    edicion_dir = salida_dir / slug
    edicion_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(Path(eventos_json_path).read_text(encoding="utf-8"))

    # Cine vive en su propia sección /cine/.
    eventos = [ev for ev in data.get("eventos", []) if ev.get("categoria") != "cine"]
    semana = [ev for ev in eventos if ev.get("fecha") and en_esta_semana(ev["fecha"], jueves)]
    semana.sort(key=lambda e: e["fecha"])

    cats = categorias_presentes(semana)
    botones_cat = "\n".join(
        f'<button class="filter-chip" data-filter="{esc(c)}">{esc(cat_label(c))}</button>' for c in cats
    )

    rango = etiqueta_rango(jueves)
    html_doc = PLANTILLA.format(
        slug=slug,
        rango=esc(rango),
        total=len(semana),
        botones_cat=botones_cat,
        bloque_semana=render_esta_semana(semana),
        bloque_futuro=render_lo_que_se_viene(eventos, jueves),
        generado=esc(data.get("generado", "")),
        anio=jueves.year,
    )

    salida_edicion = edicion_dir / "index.html"
    salida_edicion.write_text(html_doc, encoding="utf-8")
    shutil.copyfile(salida_edicion, salida_dir / "index.html")

    return {"slug": slug, "esta_semana": len(semana), "rango": rango, "salida": str(salida_edicion)}


PLANTILLA = """<!doctype html>
<html lang="es-AR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agenda de espectáculos en La Plata · {rango} · MoVeTe</title>
  <meta name="description" content="Agenda de espectáculos en La Plata: teatro, stand up, música, danza y eventos en vivo. Edición {rango}.">
  <link rel="stylesheet" href="/assets/css/movete.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">MoVeTe<span>●</span></a>
    <nav>
      <a href="/cine/">Cine</a>
      <a href="/en-vivo/">En vivo</a>
    </nav>
  </header>

  <main>
    <section class="hero compact">
      <p class="eyebrow">La Plata · Edición semanal</p>
      <h1>Agenda de espectáculos en La Plata</h1>
      <p class="lead">Edición {rango} · {total} eventos esta semana.</p>
      <div class="actions">
        <a class="button" href="#esta-semana">Esta semana</a>
        <a class="button secondary" href="#lo-que-se-viene">Lo que se viene</a>
      </div>
    </section>

    <section class="filters">
      <button class="filter-chip" data-filter="todos">Todos</button>
      {botones_cat}
    </section>

    <section id="esta-semana" class="section-block">
      <h2>Esta semana</h2>
      <p>Agenda del {rango}</p>
      {bloque_semana}
    </section>

    <section id="lo-que-se-viene" class="section-block">
      <h2>Lo que se viene</h2>
      <p>Grandes eventos anunciados en estadios, teatros y venues masivos.</p>
      {bloque_futuro}
    </section>

    <section class="ad-box">
      <p class="ad-label">Espacio promocional</p>
      <h2>Tres Empanadas Comedia</h2>
      <p>Stand up en La Plata. Shows a la gorra, todos los viernes.</p>
      <a class="button small" href="https://tresempanadas.com.ar/reservas">Reservar</a>
    </section>
  </main>

  <footer class="site-footer">
    <p>MoVeTe · Agenda cultural del Gran La Plata · Edición {slug}</p>
    <p>Datos actualizados {generado}</p>
  </footer>
</body>
</html>
"""


if __name__ == "__main__":
    eventos_json = sys.argv[1] if len(sys.argv) > 1 else "eventos.json"
    salida = sys.argv[2] if len(sys.argv) > 2 else "../Movete-info/en-vivo"
    resultado = generar(eventos_json, salida)
    print(resultado)
