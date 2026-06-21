"""Generador de la edición semanal de movete-espectaculos.

Lee eventos.json (salida del scraper) y produce el HTML de una edición:
  - Hero con la fecha de la edición
  - Barra sticky con accesos directos + filtros de categoría
  - "Esta semana": eventos jueves→miércoles, agrupados por día
  - "Lo que se viene": eventos en venues masivos, con link a página propia

Reusa el sistema visual de movete-child (style.css, tokens, colores cat).
"""
import html
import json
from collections import defaultdict
from datetime import date, datetime

from edicion import (
    jueves_de_edicion, slug_edicion, en_esta_semana,
    etiqueta_dia, etiqueta_rango, MESES_ABR,
)
from venues import venue_masivo

# Etiqueta linda por categoría (las claves vienen del scraper)
CAT_LABEL = {
    'teatro': 'Teatro', 'musica': 'Música', 'stand-up': 'Stand-up',
    'danza': 'Danza', 'cine': 'Cine', 'infantil': 'Infantil',
    'taller': 'Taller', 'a-plasticas': 'Artes plásticas', 'impro': 'Impro',
}


def esc(s: str) -> str:
    return html.escape(s or '', quote=True)


def parse_fecha(s: str) -> datetime:
    return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')


def cat_label(cat: str) -> str:
    return CAT_LABEL.get(cat, cat.replace('-', ' ').title())


def render_evento(ev: dict) -> str:
    """Una fila de evento (usa .movete-event-item del CSS existente)."""
    f = parse_fecha(ev['fecha'])
    cat = ev.get('categoria', 'otros')
    titulo = esc(ev['titulo'])
    lugar = esc(ev.get('lugar', ''))
    hora = f.strftime('%H:%M')
    url = ev.get('url', '')

    meta = ' · '.join(p for p in [hora + ' hs', lugar] if p.strip())
    titulo_html = f'<a href="{esc(url)}" target="_blank" rel="noopener">{titulo}</a>' if url else titulo

    return f'''      <div class="movete-event-item" data-cat="{esc(cat)}">
        <div class="movete-event-date">
          <span class="day">{f.day}</span>
          <span class="month">{MESES_ABR[f.month]}</span>
        </div>
        <div>
          <h3 class="movete-event-title">{titulo_html}</h3>
          <div class="movete-event-meta">{meta}</div>
        </div>
        <span class="movete-event-cat" style="background:var(--cat-{esc(cat)},#393e41);color:#fff">{esc(cat_label(cat))}</span>
      </div>'''


def render_esta_semana(eventos_semana: list) -> str:
    """Eventos agrupados por día (Jueves 25, Viernes 26...)."""
    por_dia = defaultdict(list)
    for ev in eventos_semana:
        por_dia[parse_fecha(ev['fecha']).date()].append(ev)

    bloques = []
    for dia in sorted(por_dia):
        filas = '\n'.join(render_evento(ev) for ev in sorted(
            por_dia[dia], key=lambda e: e['fecha']))
        bloques.append(f'''    <div class="dia-grupo">
      <h3 class="dia-titulo">{esc(etiqueta_dia(dia))}</h3>
      <div class="movete-event-list">
{filas}
      </div>
    </div>''')

    if not bloques:
        return '    <p class="movete-hoy-empty">No hay eventos cargados para esta semana todavía.</p>'
    return '\n'.join(bloques)


def render_lo_que_se_viene(eventos: list, jueves: date) -> str:
    """Eventos futuros en venues masivos, fuera de esta semana."""
    futuros = []
    vistos = set()
    for ev in eventos:
        if en_esta_semana(ev['fecha'], jueves):
            continue
        vm = venue_masivo(ev.get('lugar', ''))
        if not vm:
            continue
        clave = (ev['titulo'].lower(), ev['fecha'][:10])
        if clave in vistos:
            continue
        vistos.add(clave)
        futuros.append((ev, vm))

    if not futuros:
        return '    <p class="movete-hoy-empty">Sin grandes eventos anunciados por ahora.</p>'

    futuros.sort(key=lambda x: x[0]['fecha'])
    filas = []
    for ev, (clave_venue, nombre_venue) in futuros:
        f = parse_fecha(ev['fecha'])
        filas.append(f'''      <div class="movete-event-item" data-cat="{esc(ev.get('categoria','otros'))}">
        <div class="movete-event-date">
          <span class="day">{f.day}</span>
          <span class="month">{MESES_ABR[f.month]}</span>
        </div>
        <div>
          <h3 class="movete-event-title">{esc(ev['titulo'])}</h3>
          <div class="movete-event-meta">{esc(nombre_venue)}</div>
        </div>
        <span class="movete-event-cat" style="background:var(--accent);color:#fff">Gran evento</span>
      </div>''')

    return f'''    <div class="movete-event-list">
{chr(10).join(filas)}
    </div>'''


def categorias_presentes(eventos_semana: list) -> list:
    cats = []
    for ev in eventos_semana:
        c = ev.get('categoria', 'otros')
        if c not in cats:
            cats.append(c)
    return cats


def generar(eventos_json_path: str, salida_path: str, hoy: date = None):
    hoy = hoy or date.today()
    jueves = jueves_de_edicion(hoy)
    slug = slug_edicion(jueves)

    with open(eventos_json_path, encoding='utf-8') as f:
        data = json.load(f)
    # Cine vive en su propia sección /cine/ — fuera de espectáculos.
    eventos = [ev for ev in data['eventos'] if ev.get('categoria') != 'cine']

    semana = [ev for ev in eventos if en_esta_semana(ev['fecha'], jueves)]
    semana.sort(key=lambda e: e['fecha'])

    cats = categorias_presentes(semana)
    botones_cat = '\n'.join(
        f'        <button class="filtro-cat" data-cat="{esc(c)}">{esc(cat_label(c))}</button>'
        for c in cats)

    bloque_semana = render_esta_semana(semana)
    bloque_futuro = render_lo_que_se_viene(eventos, jueves)
    rango = etiqueta_rango(jueves)

    html_doc = PLANTILLA.format(
        slug=slug,
        rango=esc(rango),
        total=len(semana),
        botones_cat=botones_cat,
        bloque_semana=bloque_semana,
        bloque_futuro=bloque_futuro,
        generado=data.get('generado', ''),
        anio=jueves.year,
    )

    with open(salida_path, 'w', encoding='utf-8') as f:
        f.write(html_doc)

    return {'slug': slug, 'esta_semana': len(semana),
            'rango': rango, 'salida': salida_path}


PLANTILLA = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qué hacer en La Plata · {rango} · MoVeTe</title>
<meta name="description" content="Agenda de espectáculos del Gran La Plata, {rango}. Teatro, música, stand-up y los grandes eventos que se vienen.">
<link rel="stylesheet" href="style.css">
<style>
/* --- Solo lo NUEVO de la edición; el resto sale de style.css --- */
.movete-edicion-hero {{
  background: var(--ink); color: var(--paper);
  padding: 64px 24px 40px; text-align: center;
  position: relative; overflow: hidden;
}}
.movete-edicion-hero::before {{
  content:""; position:absolute; inset:0;
  background: radial-gradient(ellipse at 70% 50%, rgba(255,81,40,0.12) 0%, transparent 70%);
}}
.movete-edicion-hero h1 {{
  font-family: var(--ff-serif); font-weight: 900;
  font-size: clamp(36px, 7vw, 84px); margin: 0 0 14px; color: var(--paper);
  position: relative;
}}
.movete-edicion-hero h1 .italic {{ font-style: italic; color: var(--accent); }}
.movete-edicion-hero .rango {{
  font-family: var(--ff-mono); font-size: 13px; text-transform: uppercase;
  letter-spacing: 0.18em; color: rgba(245,241,232,0.6); margin: 0; position: relative;
}}

.nav-sticky {{
  position: sticky; top: 0; z-index: 90;
  background: var(--paper); border-bottom: 1px solid var(--border);
  padding: 12px 16px; display: flex; gap: 8px; flex-wrap: wrap;
  align-items: center; justify-content: center;
}}
.nav-sticky a.salto {{
  font-family: var(--ff-serif); font-weight: 700; font-size: 14px;
  text-decoration: none; color: var(--ink); padding: 6px 14px;
  border: 1.5px solid var(--ink); border-radius: var(--r);
}}
.nav-sticky a.salto:hover {{ background: var(--ink); color: var(--paper); }}
.nav-sep {{ width:1px; height:22px; background: var(--border); margin: 0 4px; }}
.filtro-cat {{
  font-family: var(--ff-mono); font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: 0.06em;
  background: transparent; color: var(--muted);
  border: 1px solid var(--border); border-radius: 999px;
  padding: 5px 12px; cursor: pointer; transition: all 0.15s;
}}
.filtro-cat:hover {{ color: var(--ink); border-color: var(--ink); }}
.filtro-cat.activa {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

.seccion {{ max-width: 900px; margin: 0 auto; padding: 48px 24px 8px; }}
.seccion-titulo {{
  font-family: var(--ff-serif); font-weight: 900; font-size: clamp(28px,5vw,44px);
  margin: 0 0 4px; letter-spacing: -0.02em;
}}
.seccion-sub {{
  font-family: var(--ff-mono); font-size: 12px; text-transform: uppercase;
  letter-spacing: 0.12em; color: var(--muted); margin: 0 0 8px;
}}
.dia-grupo {{ padding: 0 24px; max-width: 900px; margin: 0 auto; }}
.dia-titulo {{
  font-family: var(--ff-mono); font-size: 13px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent);
  margin: 24px 0 0; padding-top: 16px; border-top: 2px solid var(--ink);
}}
.movete-event-item.oculto {{ display: none; }}
.movete-event-title a {{ color: inherit; text-decoration: none; }}
.movete-event-title a:hover {{ color: var(--accent); }}

footer.movete-footer {{
  background: var(--ink); color: rgba(245,241,232,0.6);
  text-align: center; padding: 40px 24px; margin-top: 60px;
  font-family: var(--ff-mono); font-size: 12px;
}}
footer.movete-footer a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>

<header class="site-header" style="background:var(--ink);position:sticky;top:0;z-index:100">
  <div class="inside-header" style="display:flex;align-items:center;justify-content:space-between;padding:14px 24px;max-width:1200px;margin:0 auto">
    <a href="/espectaculos/" style="color:var(--paper);font-family:var(--ff-serif);font-weight:900;font-size:28px;text-decoration:none;letter-spacing:-0.02em">MoVeTe<span style="color:var(--accent)">.</span></a>
    <nav style="font-family:var(--ff-mono);font-size:13px">
      <a href="/cine/" style="color:rgba(245,241,232,0.7);text-decoration:none;margin-left:18px">Cine</a>
      <a href="/espectaculos/" style="color:var(--paper);text-decoration:none;margin-left:18px">En vivo</a>
    </nav>
  </div>
</header>

<section class="movete-edicion-hero">
  <h1>Qué hacer en <span class="italic">La Plata</span></h1>
  <p class="rango">Edición {rango} · {total} eventos esta semana</p>
</section>

<nav class="nav-sticky">
  <a class="salto" href="#esta-semana">Esta semana</a>
  <a class="salto" href="#lo-que-se-viene">Lo que se viene</a>
  <span class="nav-sep"></span>
  <button class="filtro-cat activa" data-cat="todas">Todas</button>
{botones_cat}
</nav>

<section class="seccion" id="esta-semana">
  <h2 class="seccion-titulo">Esta semana</h2>
  <p class="seccion-sub">Agenda del {rango}</p>
</section>
<div id="contenedor-semana">
{bloque_semana}
</div>

<section class="seccion" id="lo-que-se-viene">
  <h2 class="seccion-titulo">Lo que se viene</h2>
  <p class="seccion-sub">Grandes eventos en los estadios y teatros mayores</p>
</section>
{bloque_futuro}

<footer class="movete-footer">
  <p>MoVeTe · Agenda cultural del Gran La Plata · Edición {slug}</p>
  <p>Datos actualizados {generado} · <a href="/espectaculos/">Ver todas las ediciones</a></p>
</footer>

<script>
// Filtro de categorías: mantiene el agrupado por día, oculta lo que no matchea.
(function() {{
  const botones = document.querySelectorAll('.filtro-cat');
  const items = document.querySelectorAll('#contenedor-semana .movete-event-item');
  const grupos = document.querySelectorAll('#contenedor-semana .dia-grupo');

  function aplicar(cat) {{
    items.forEach(it => {{
      const match = cat === 'todas' || it.dataset.cat === cat;
      it.classList.toggle('oculto', !match);
    }});
    // Ocultar días que quedaron vacíos
    grupos.forEach(g => {{
      const visibles = g.querySelectorAll('.movete-event-item:not(.oculto)').length;
      g.style.display = visibles ? '' : 'none';
    }});
  }}

  botones.forEach(b => b.addEventListener('click', () => {{
    botones.forEach(x => x.classList.remove('activa'));
    b.classList.add('activa');
    aplicar(b.dataset.cat);
  }}));
}})();
</script>

</body>
</html>'''
