"""Generador estático de En Vivo para MoVeTe.

Lee eventos.json, genera una edición semanal jueves→miércoles y escribe:

- <output>/index.html              portada vigente de En Vivo
- <output>/<YYYY-MM-DD>/index.html edición archivada

Ejemplo local:

python generar_edicion.py --eventos eventos.json --output ../Movete-info/en-vivo
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
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
    "humor": "Humor",
    "otros": "Otros",
}


def esc(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def parse_fecha(s: str) -> datetime:
    s = str(s or "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19 if "H" in fmt else 10], fmt)
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
    lugar = esc(evento_lugar(ev))
    hora = f.strftime("%H:%M")
    url = esc(evento_url(ev))
    meta = " · ".join(p for p in [f"{hora} hs", lugar] if p.strip())

    titulo_html = f'<a href="{url}">{titulo}</a>' if url else titulo

    return f"""
      <article class="event-card" data-category="{esc(cat)}">
        <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
        <h3>{titulo_html}</h3>
        <p class="event-meta">{esc(meta)}</p>
        <span class="event-cat">{esc(cat_label(cat))}</span>
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
        return '<div class="note-box"><p>No hay eventos cargados para esta semana todavía.</p></div>'

    bloques = []
    for dia in sorted(por_dia):
        filas = "\n".join(render_evento(ev) for ev in sorted(por_dia[dia], key=lambda e: e.get("fecha", "")))
        bloques.append(
            f"""
            <section class="day-block">
              <h2>{esc(etiqueta_dia(dia))}</h2>
              <div class="event-list">{filas}</div>
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
        return '<div class="note-box"><p>Sin grandes eventos anunciados por ahora.</p></div>'

    futuros.sort(key=lambda x: x[0].get("fecha", ""))
    cards = []
    for ev, (_clave_venue, nombre_venue) in futuros[:16]:
        f = parse_fecha(ev["fecha"])
        url = esc(evento_url(ev))
        titulo = esc(evento_titulo(ev))
        titulo_html = f'<a href="{url}">{titulo}</a>' if url else titulo
        cards.append(
            f"""
            <article class="event-card">
              <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
              <h3>{titulo_html}</h3>
              <p class="event-meta">{esc(nombre_venue)}</p>
              <span class="event-cat">Gran evento</span>
            </article>
            """
        )
    return f'<div class="event-list">{"".join(cards)}</div>'


def categorias_presentes(eventos_semana: list[dict]) -> list[str]:
    cats: list[str] = []
    for ev in eventos_semana:
        c = ev.get("categoria", "otros")
        if c not in cats:
            cats.append(c)
    return cats


def cargar_eventos(path: str | Path) -> tuple[list[dict], str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data, ""
    return data.get("eventos", []), data.get("generado", "")


def render_html(eventos: list[dict], generado: str, hoy: date | None = None) -> tuple[str, dict]:
    hoy = hoy or date.today()
    jueves = jueves_de_edicion(hoy)
    slug = slug_edicion(jueves)

    eventos = [ev for ev in eventos if ev.get("categoria") != "cine" and ev.get("fecha")]
    semana = [ev for ev in eventos if en_esta_semana(ev["fecha"], jueves)]
    semana.sort(key=lambda e: e.get("fecha", ""))

    cats = categorias_presentes(semana)
    botones_cat = "\n".join(
        f'<a class="filter-chip" href="#" data-filter="{esc(c)}">{esc(cat_label(c))}</a>' for c in cats
    )

    rango = etiqueta_rango(jueves)
    html_doc = PLANTILLA.format(
        slug=esc(slug),
        rango=esc(rango),
        total=len(semana),
        botones_cat=botones_cat,
        bloque_semana=render_esta_semana(semana),
        bloque_futuro=render_lo_que_se_viene(eventos, jueves),
        generado=esc(generado),
        anio=jueves.year,
    )
    return html_doc, {"slug": slug, "rango": rango, "esta_semana": len(semana)}


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

    return {
        **info,
        "salida_actual": str(current_index),
        "salida_archivo": str(archive_index),
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
  <title>Agenda de espectáculos en La Plata · {rango} · MoVeTe</title>
  <meta name="description" content="Agenda de espectáculos en La Plata: teatro, música, stand up, danza y eventos en vivo. Edición {rango}.">
  <link rel="stylesheet" href="/assets/css/movete.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="/">MoVeTe<span>●</span></a>
    <nav class="site-nav">
      <a href="/cine/">Cine</a>
      <a href="/en-vivo/">En vivo</a>
    </nav>
  </header>

  <main>
    <section class="hero">
      <p class="eyebrow">En vivo · Edición {slug}</p>
      <h1>Agenda de espectáculos en La Plata</h1>
      <p class="lead">Edición {rango}. Teatro, música, stand up, danza y eventos en vivo.</p>
      <div class="actions">
        <a class="button" href="#esta-semana">Esta semana</a>
        <a class="button secondary" href="#lo-que-se-viene">Lo que se viene</a>
      </div>
    </section>

    <section class="note-box section-block">
      <p class="eyebrow">Esta edición</p>
      <h2>{total} eventos esta semana</h2>
      <p>Las ediciones anteriores quedan archivadas y la portada de En Vivo muestra siempre la edición vigente.</p>
    </section>

    <nav class="filters" aria-label="Filtros de categoría">
      <a class="filter-chip" href="#">Todas</a>
      {botones_cat}
    </nav>

    <section id="esta-semana" class="section-block">
      <p class="eyebrow">Agenda semanal</p>
      <h2>Esta semana</h2>
      {bloque_semana}
    </section>

    <section id="lo-que-se-viene" class="section-block">
      <p class="eyebrow">Anticipadas</p>
      <h2>Lo que se viene</h2>
      <p>Grandes eventos anunciados en estadios y teatros mayores, para mirar con tiempo.</p>
      {bloque_futuro}
    </section>

    <section class="crosslink note-box section-block">
      <p class="eyebrow">También en MoVeTe</p>
      <h2>Cartelera de cine</h2>
      <p>Películas, salas y funciones de la semana en La Plata.</p>
      <a class="button small" href="/cine/">Ver cine</a>
    </section>

    <div data-ads></div>
  </main>

  <footer class="site-footer">
    <p>MoVeTe · Agenda cultural del Gran La Plata · Edición {slug}</p>
    <p>Datos actualizados {generado}</p>
  </footer>
  <script src="/assets/js/ads.js"></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
