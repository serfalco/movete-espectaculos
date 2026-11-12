"""Generador estático de En Vivo para MoVeTe.

Lee eventos.json, genera una edición semanal jueves→miércoles y escribe:

- /index.html portada vigente de En Vivo
- /YYYY-MM-DD/index.html edición archivada

Ejemplo local:

python generar_edicion.py --eventos eventos.json --output ../Movete-info/en-vivo
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from edicion import (
    MESES,
    MESES_ABR,
    en_esta_semana,
    etiqueta_dia,
    etiqueta_rango,
    jueves_de_edicion,
    slug_edicion,
)
from imagenes import localizar_imagenes
from venues import (venue_info, venue_masivo, venue_canonico, venue_slug, venue_instagram, venue_web, venue_imagen,
                    VENUES_MASIVOS, VENUES_DIRECCIONES)


CAT_LABEL = {
    "teatro": "Teatro",
    "musica": "Música",
    "stand-up": "Stand Up",
    "danza": "Danza",
    "cine": "Cine",
    "infantil": "Infantil",
    "taller": "Taller",
    "a-plasticas": "Artes plásticas",
    "charlas": "Charlas y letras",
    "ferias": "Ferias y fiestas",
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
    "ferias",
    "charlas",
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
    "ferias": "Ferias y fiestas en La Plata: ferias de diseño y vinilos, degustaciones, aniversarios de bares y festejos de la semana.",
    "charlas": "Charlas y letras en La Plata: conversatorios, presentaciones de libros, poesía y encuentros literarios de la semana.",
    "otros": "Más cosas para hacer en La Plata: actividades culturales, encuentros y propuestas de la semana.",
}


def postal_address(direccion: str | None) -> dict:
    """PostalAddress para el JSON-LD, siempre presente.

    Google Search Console marca "Falta el campo address (en location)" cuando
    el Place sale solo con name. Antes omitiamos el bloque entero si no
    sabiamos la calle, y eso pasaba con todo lugar que no esta en
    VENUES_DIRECCIONES (12 de 40 eventos en la edicion del 10/09/2026).

    Ahora la direccion sale siempre: si no tenemos la calle, igual decimos
    que es en La Plata, Buenos Aires, Argentina. Es cierto, es lo que Google
    pide, y el streetAddress se suma solo cuando lo conocemos.
    """
    addr = {
        "@type": "PostalAddress",
        "addressLocality": "La Plata",
        "addressRegion": "Buenos Aires",
        "addressCountry": "AR",
    }
    calle = str(direccion or "").strip()
    if calle:
        # La tabla guarda ", La Plata" al final; en el JSON-LD ya lo dice
        # addressLocality, repetirlo ensucia el dato.
        calle = re.sub(r",?\s*La Plata\s*$", "", calle).strip(" ,")
        calle = re.sub(r",?\s*Buenos Aires\s*$", "", calle).strip(" ,")
    if calle:
        addr["streetAddress"] = calle
    return addr


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
        "url": "https://tresempanadas.com.ar/reservas/",
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


def _obra_slug_base(ev: dict) -> str:
    """Slug que sale del título tal cual, sin unificar variantes."""
    if ev.get("categoria") == "cine" or not ev.get("fecha"):
        return ""
    titulo = evento_titulo(ev)
    if titulo == "Sin título":
        return ""
    slug = venue_slug(titulo)[:70].strip("-")
    if len(slug.replace("-", "")) < 4:
        return ""
    return slug


# Variantes de un mismo show: {slug_largo: slug_principal}. Se calcula una vez
# por corrida (calcular_alias_obras) antes de renderizar nada, así las tarjetas
# de las ediciones enlazan siempre a la misma página.
_ALIAS_OBRA: dict[str, str] = {}

# Un slug principal necesita este largo (sin guiones) para absorber variantes:
# evita juntar "la-k" con "la-konga" aunque compartan el comienzo.
_MIN_LARGO_SLUG_PRINCIPAL = 6


def obra_slug(ev: dict) -> str:
    """Slug de la página propia de una obra/show: /en-vivo/obra/<slug>/.

    Se arma solo con el título, así la misma obra en dos salas (o en varias
    fechas) comparte una página. Si el título es una variante de otro show de
    la misma sala ("Elena Roger" y "Elena Roger en concierto"), las dos usan
    la página del más corto. Devuelve '' si el evento no merece página
    (cine, sin fecha o título demasiado pobre para posicionar).
    """
    base = _obra_slug_base(ev)
    return _ALIAS_OBRA.get(base, base)


def _clave_sala_obra(ev: dict) -> str:
    """Identidad de la sala de un evento: la del catálogo si la hay, y si no
    el texto del lugar normalizado."""
    lugar = evento_lugar(ev)
    vc = venue_canonico(lugar)
    return vc["slug"] if vc else venue_slug(lugar)


def calcular_alias_obras(eventos: list[dict]) -> dict[str, str]:
    """{slug_variante: slug_principal} para obras que son el mismo show.

    Dos páginas de obra son el mismo show si el slug de una empieza con el de
    la otra ("emanero" / "emanero-todo-por-un-beso") Y comparten sala. Cada
    fuente agrega un subtítulo distinto al mismo espectáculo, y dos páginas
    para lo mismo se hacen competencia entre sí en Google. Gana el slug más
    corto: es el que la gente escribe al buscar.
    """
    claves: dict[str, set] = {}
    for ev in eventos:
        base = _obra_slug_base(ev)
        if base:
            claves.setdefault(base, set()).add(_clave_sala_obra(ev))
    alias: dict[str, str] = {}
    slugs = sorted(claves, key=lambda x: (len(x), x))
    for i, largo in enumerate(slugs):
        for corto in slugs[:i]:
            if (len(corto.replace("-", "")) >= _MIN_LARGO_SLUG_PRINCIPAL
                    and largo.startswith(corto + "-")
                    and claves[corto] & claves[largo]):
                # Si el corto ya es variante de otro, se sigue hasta el principal.
                alias[largo] = alias.get(corto, corto)
                break
    return alias


# Slugs que nombran un tipo de evento y no un show: "la-fiesta" no es la
# principal de "la-fiesta-judia-klezmer...".
_PALABRAS_GENERICAS_OBRA = {
    "la", "el", "los", "las", "un", "una", "de", "del", "y", "en",
    "fiesta", "festival", "concierto", "show", "tributo", "gala", "noche",
    "homenaje", "recital", "taller", "obra", "teatro", "milonga", "pena",
    "feria", "muestra", "stand", "up", "standup", "humor", "musica", "danza",
}


def principal_existente(slug: str, existentes: set[str]) -> str:
    """Para una obra que ya no tiene funciones: si hay otra página cuyo slug
    es el comienzo de éste ("emanero" para "emanero-todo-por-un-beso"), esa es
    la principal. El alias de calcular_alias_obras dura solo mientras las dos
    variantes están en cartelera; cuando el show termina, las dos quedaban
    como páginas sueltas compitiendo entre sí. Devuelve '' si no hay."""
    candidatos = [
        s for s in existentes
        if s != slug and len(s.replace("-", "")) >= _MIN_LARGO_SLUG_PRINCIPAL
        and slug.startswith(s + "-")
        and not set(s.split("-")) <= _PALABRAS_GENERICAS_OBRA
    ]
    return min(candidatos, key=len) if candidatos else ""


def _texto_busqueda(*partes: str) -> str:
    """Texto en minúsculas y sin acentos para el buscador de la cartelera."""
    import unicodedata
    t = " ".join(p for p in partes if p).casefold()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def render_evento(ev: dict, link_obra: bool = True) -> str:
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
    # El título lleva a la página propia de la obra (enlazado interno: es lo
    # que hace que Google la encuentre y la posicione). La web externa de
    # entradas queda como link aparte.
    oslug = obra_slug(ev) if link_obra else ""
    if oslug:
        titulo_html = f'<a href="/en-vivo/obra/{oslug}/">{titulo}</a>'
    elif url:
        titulo_html = f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>'
    else:
        titulo_html = titulo
    ticket_html = ""
    if url and (oslug or not link_obra):
        ticket_html = (f'\n      <p class="event-ticket"><a class="card-link" href="{url}" '
                       f'target="_blank" rel="noopener">Entradas y más info →</a></p>')
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

    # Imagen del evento (si la fuente la trajo). Si falla al cargar, el propio
    # onerror saca el bloque y la tarjeta queda de texto, sin imagen rota.
    imagen = str(ev.get("imagen") or "").strip()
    media_html = ""
    if imagen:
        media_html = f"""
      <div class="event-card-media">
        <img src="{esc(imagen)}" alt="Afiche de {titulo}" loading="lazy" decoding="async"
             onerror="this.style.visibility='hidden'">
      </div>"""

    return f"""
    <article class="event-card{' has-media' if imagen else ''}" data-category="{esc(cat)}"
             data-dia="{f.date().isoformat()}" data-franja="{'tarde' if f.hour < 19 else 'noche'}"
             data-texto="{esc(_texto_busqueda(evento_titulo(ev), datos_lugar['nombre'], cat_label(cat)))}"
             data-titulo="{titulo}" data-inicio="{f.strftime('%Y-%m-%dT%H:%M')}" data-lugar="{lugar}"
             data-direccion="{esc(direccion)}" data-link="{esc(('https://movete.info/en-vivo/obra/' + oslug + '/') if oslug else evento_url(ev))}">
      {media_html}
      <div class="event-card-topline">
        <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
        <p class="pill">{esc(cat_label(cat))}</p>
      </div>
      <h3>{titulo_html}</h3>
      <p class="event-meta">{meta}</p>{ticket_html}
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

    cats = sorted({ev.get("categoria", "otros") for ev in eventos_semana}, key=cat_label)
    return render_buscador(cats) + "\n".join(bloques) + _SCRIPT_BUSCADOR


_ESTILO_BUSCADOR = """
<style>
  .buscador { display: grid; gap: 10px; margin: 8px 0 22px; padding-bottom: 14px; border-bottom: 1px solid var(--line-strong); }
  .buscador input[type=search] { width: 100%; font: inherit; font-size: 1rem; padding: 11px 14px;
    border: 1px solid var(--line-strong); border-radius: 12px; background: var(--paper); color: var(--ink); }
  .buscador-fila { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .buscador-fila button, .buscador-fila select { font: inherit; font-size: .88rem; padding: 6px 12px;
    border-radius: 999px; border: 1px solid var(--line-strong); background: transparent; color: var(--ink); cursor: pointer; }
  .buscador-fila button[aria-pressed=true] { background: var(--ink); color: var(--paper); border-color: var(--ink); }
  .buscador-cuenta { margin: 0; font-size: .85rem; color: var(--muted); }
  [data-sin-resultados] button { font: inherit; margin-left: 4px; padding: 4px 12px; border-radius: 999px;
    border: 1px solid var(--line-strong); background: transparent; color: var(--ink); cursor: pointer; }
  .buscador-cuenta button { font: inherit; background: none; border: 0; padding: 0; color: inherit; text-decoration: underline; cursor: pointer; }
</style>"""


def render_buscador(cats: list[str]) -> str:
    """Buscador y filtros combinables (día, horario, categoría) arriba de la
    cartelera. Todo en el navegador: filtra las tarjetas que ya están en la
    página. El estado va en la URL (?q=&dia=&franja=&cat=) para poder
    compartir una búsqueda."""
    opciones = "".join(f'<option value="{esc(c)}">{esc(cat_label(c))}</option>' for c in cats)
    select = (f'<select data-f="cat" aria-label="Categoría"><option value="">Todas las categorías</option>'
              f'{opciones}</select>') if len(cats) > 1 else ""
    return _ESTILO_BUSCADOR + f"""
    <div class="buscador" role="search">
      <input type="search" data-f="q" placeholder="Buscá artista, obra o sala" aria-label="Buscar en la cartelera" autocomplete="off">
      <div class="buscador-fila" data-grupo="dia" aria-label="Día">
        <button type="button" data-v="" aria-pressed="true">Toda la semana</button>
        <button type="button" data-v="hoy" aria-pressed="false">Hoy</button>
        <button type="button" data-v="manana" aria-pressed="false">Mañana</button>
        <button type="button" data-v="finde" aria-pressed="false">Finde</button>
      </div>
      <div class="buscador-fila" data-grupo="franja" aria-label="Horario">
        <button type="button" data-v="" aria-pressed="true">Todo el día</button>
        <button type="button" data-v="tarde" aria-pressed="false">Tarde</button>
        <button type="button" data-v="noche" aria-pressed="false">Noche</button>
        {select}
      </div>
      <p class="buscador-cuenta" aria-live="polite"></p>
    </div>
    <p class="empty" data-sin-resultados style="display:none">No hay nada con esos filtros.
      <button type="button" data-limpiar>Ver toda la semana</button></p>"""


_SCRIPT_BUSCADOR = """
<script>
(function () {
  var raiz = document.getElementById("esta-semana") || document;
  var barra = raiz.querySelector(".buscador");
  if (!barra) return;
  var tarjetas = Array.prototype.slice.call(raiz.querySelectorAll(".event-card[data-dia]"));
  var secciones = raiz.querySelectorAll(".day-block");
  var input = barra.querySelector('[data-f="q"]');
  var select = barra.querySelector('[data-f="cat"]');
  var cuenta = barra.querySelector(".buscador-cuenta");
  var vacio = raiz.querySelector("[data-sin-resultados]");
  var estado = { q: "", dia: "", franja: "", cat: "" };

  function sinAcentos(t) { return t.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
  function iso(d) { return d.toLocaleDateString("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }); }
  var hoy = iso(new Date());
  var manana = iso(new Date(Date.now() + 864e5));
  function esFinde(dia) { var w = new Date(dia + "T12:00:00").getDay(); return w === 5 || w === 6 || w === 0; }

  function aplicar() {
    var palabras = sinAcentos(estado.q).split(/\s+/).filter(Boolean);
    var n = 0;
    tarjetas.forEach(function (t) {
      var d = t.getAttribute("data-dia");
      var ok = (!estado.cat || t.getAttribute("data-category") === estado.cat)
        && (!estado.franja || t.getAttribute("data-franja") === estado.franja)
        && (!estado.dia || (estado.dia === "hoy" ? d === hoy : estado.dia === "manana" ? d === manana : esFinde(d) && d >= hoy))
        && palabras.every(function (p) { return (t.getAttribute("data-texto") || "").indexOf(p) !== -1; });
      t.style.display = ok ? "" : "none";
      if (ok) n++;
    });
    Array.prototype.forEach.call(secciones, function (s) {
      var alguna = Array.prototype.some.call(s.querySelectorAll(".event-card[data-dia]"), function (t) { return t.style.display !== "none"; });
      s.style.display = alguna ? "" : "none";
    });
    var filtrando = estado.q || estado.dia || estado.franja || estado.cat;
    cuenta.innerHTML = filtrando ? n + (n === 1 ? " evento" : " eventos") + ' · <button type="button" data-limpiar>limpiar filtros</button>' : tarjetas.length + " eventos esta semana";
    vacio.style.display = n ? "none" : "";
    barra.querySelectorAll("[data-grupo]").forEach(function (g) {
      g.querySelectorAll("button").forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-v") === estado[g.getAttribute("data-grupo")] ? "true" : "false");
      });
    });
    try {
      var u = new URL(location.href);
      ["q", "dia", "franja", "cat"].forEach(function (k) { if (estado[k]) u.searchParams.set(k, estado[k]); else u.searchParams.delete(k); });
      history.replaceState(null, "", u);
    } catch (e) {}
  }

  function limpiar() { estado = { q: "", dia: "", franja: "", cat: "" }; input.value = ""; if (select) select.value = ""; aplicar(); }

  try {
    var p = new URL(location.href).searchParams;
    ["q", "dia", "franja", "cat"].forEach(function (k) { estado[k] = p.get(k) || ""; });
    input.value = estado.q; if (select) select.value = estado.cat;
  } catch (e) {}

  var espera;
  input.addEventListener("input", function () { clearTimeout(espera); espera = setTimeout(function () { estado.q = input.value; aplicar(); }, 120); });
  if (select) select.addEventListener("change", function () { estado.cat = select.value; aplicar(); });
  barra.querySelectorAll("[data-grupo]").forEach(function (g) {
    g.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-v]"); if (!b) return;
      estado[g.getAttribute("data-grupo")] = b.getAttribute("data-v"); aplicar();
    });
  });
  raiz.addEventListener("click", function (e) { if (e.target.closest("[data-limpiar]")) limpiar(); });
  aplicar();
})();
</script>"""


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
        oslug = obra_slug(ev)
        if oslug:
            titulo_html = f'<a href="/en-vivo/obra/{oslug}/">{titulo}</a>'
        elif url:
            titulo_html = f'<a href="{url}" target="_blank" rel="noopener">{titulo}</a>'
        else:
            titulo_html = titulo
        cards.append(
            f"""
            <article class="event-card future" data-category="{esc(cat)}">
              <div class="event-card-topline">
                <p class="event-date">{f.day} {MESES_ABR[f.month]}</p>
                <p class="pill">{esc(cat_label(cat))}</p>
              </div>
              <h3>{titulo_html}</h3>
              <p class="event-meta"><a href="/en-vivo/sala/{venue_slug(nombre_venue)}/">{esc(nombre_venue)}</a></p>
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
    links += [
        '<a class="filter-button" href="/en-vivo/hoy/">Hoy</a>',
        '<a class="filter-button" href="/en-vivo/fin-de-semana/">Este finde</a>',
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


def fecha_schema(f: datetime) -> str:
    """startDate con la zona horaria de La Plata. Sin offset Google tiene que
    adivinarla (y avisa); sin hora conocida va solo la fecha."""
    if f.hour == 0 and f.minute == 0:
        return f.date().isoformat()
    return f.strftime("%Y-%m-%dT%H:%M:00-03:00")


def campos_extra_schema(ev: dict, sala: str) -> dict:
    """Campos que Google recomienda para la ficha de evento en el buscador:
    url (la página del show en MoVeTe), offers (link a las entradas),
    organizer (la sala), description e image. Sin precio: las fuentes no
    lo traen y no se inventa."""
    extra: dict = {}
    titulo = evento_titulo(ev)
    oslug = obra_slug(ev)
    if oslug:
        extra["url"] = f"https://movete.info/en-vivo/obra/{_ALIAS_OBRA.get(oslug, oslug)}/"
    entradas = evento_url(ev)
    if entradas:
        extra["offers"] = {"@type": "Offer", "url": entradas}
        extra.setdefault("url", entradas)
    imagen = str(ev.get("imagen") or "").strip()
    if imagen:
        extra["image"] = imagen
    if sala:
        org = {"@type": "Organization", "name": sala}
        vc = venue_canonico(evento_lugar(ev))
        if vc:
            org["url"] = f"https://movete.info/en-vivo/sala/{vc['slug']}/"
        else:
            # Search Console avisa si falta organizer.url: respaldo con el
            # link de entradas o la cartelera general.
            org["url"] = entradas or "https://movete.info/en-vivo/"
        extra["organizer"] = org
    cat = cat_label(ev.get("categoria", "otros"))
    extra["description"] = f"{_sin_gritos(titulo)}: {cat.lower()} en {sala or 'La Plata'}, La Plata."
    return extra


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
        # PostalAddress en vez de un string suelto: es lo que Google espera
        # para poder mostrar el evento con su ubicación.
        lugar_ld = {"@type": "Place", "name": datos["nombre"]}
        lugar_ld["address"] = postal_address(
            ev.get("direccion") or datos["direccion"])
        ev_ld = {
            "@type": "Event",
            "name": evento_titulo(ev),
            "startDate": fecha_schema(f),
            "eventStatus": "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location": lugar_ld,
        }
        ev_ld.update(campos_extra_schema(ev, datos["nombre"]))
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
    page_url: str | None = None,
) -> tuple[str, dict]:
    """page_url fuerza el canonical y el og:url de la pagina.

    Sin este parametro, la edicion archivada salia con el canonical de la
    portada: le decia a Google "no me indexes, indexa /en-vivo/" justo en las
    URLs permanentes que son la apuesta SEO del proyecto.
    """
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
        "teatro": f"Cartelera de teatro en La Plata · Obras de esta semana · MoVeTe",
        "musica": f"Recitales en La Plata · Música en vivo esta semana · MoVeTe",
        "infantil": f"Obras infantiles en La Plata · Teatro para chicos · MoVeTe",
        "stand-up": f"Stand up en La Plata · Shows de comedia esta semana · MoVeTe",
        "otros": f"Más cosas para hacer en La Plata · Cartelera cultural · MoVeTe",
    }
    seo_descriptions = {
        "teatro": f"Cartelera de teatro en La Plata para la semana {rango}: obras, salas independientes, unipersonales y funciones.",
        "musica": f"Recitales y música en vivo en La Plata para la semana {rango}: bandas, conciertos y shows.",
        "infantil": f"Obras infantiles en La Plata para la semana {rango}: teatro, títeres y shows para ir con chicos.",
        "stand-up": f"Stand up en La Plata para la semana {rango}: shows de comedia, ciclos y funciones.",
        "otros": f"Más cosas para hacer en La Plata durante la semana {rango}: actividades culturales, encuentros y propuestas.",
    }
    seo_h1 = {
        "teatro": "Cartelera de teatro en La Plata",
        "musica": "Recitales y música en vivo en La Plata",
        "infantil": "Obras infantiles en La Plata",
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
    page_url = page_url or (
        f"https://movete.info/en-vivo/{categoria}/" if categoria
        else "https://movete.info/en-vivo/"
    )
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
  <link rel="canonical" href="https://movete.info/en-vivo/{esc(categoria)}/">
  <title>{esc(label)} en La Plata · MoVeTe</title>
  <meta name="description" content="Esta semana no hay {esc(label.lower())} en la cartelera en vivo de La Plata. Mirá el resto en MoVeTe.">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
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


LASTMOD_JSON = "data/sitemap-lastmod.json"


def _huella(idx: Path) -> str:
    """Huella del contenido propio de una página: el texto de <main>, sin el
    bloque "Parecido" (cambia cada semana en los shows pasados aunque el show
    no haya cambiado)."""
    try:
        texto = idx.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"<main\b.*?</main>", texto, re.S)
    cuerpo = m.group(0) if m else texto
    cuerpo = re.sub(r'<h2[^>]*>Parecido, en las próximas semanas</h2>\s*<ul class="obra-parecidos".*?</ul>',
                    "", cuerpo, flags=re.S)
    cuerpo = re.sub(r"<[^>]+>", " ", cuerpo)
    return hashlib.sha1(" ".join(cuerpo.split()).encode("utf-8")).hexdigest()[:16]


def fechas_de_cambio(root: Path, urls: list[tuple[str, str]], hoy: date) -> dict[str, str]:
    """lastmod real de cada URL del sitemap: el día en que cambió su contenido.

    Se guarda la huella de cada página en data/sitemap-lastmod.json; la fecha
    solo se mueve cuando la huella cambia. Así Google ve qué se tocó en cada
    pasada (martes, jueves, domingo) en vez de un sitemap sin fechas.
    La primera vez una edición fechada arranca con su propia fecha y el resto
    con la del día.
    """
    ruta = root / LASTMOD_JSON
    try:
        previo = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previo = {}
    nuevo: dict[str, dict] = {}
    for loc, inicial in urls:
        idx = root / loc.strip("/") / "index.html"
        huella = _huella(idx)
        if not huella:
            continue
        ant = previo.get(loc) or {}
        if ant.get("huella") == huella and ant.get("fecha"):
            fecha = ant["fecha"]
        elif not ant and inicial:
            fecha = inicial
        else:
            fecha = hoy.isoformat()
        nuevo[loc] = {"fecha": fecha, "huella": huella}
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(nuevo, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                        encoding="utf-8")
    except OSError as e:
        print(f"[sitemap] no se pudo guardar {LASTMOD_JSON}: {e}")
    return {loc: d["fecha"] for loc, d in nuevo.items()}


DIAS_EDICION_INDEXADA = 28


def retirar_ediciones_viejas(root: Path, jueves: date, dias: int = DIAS_EDICION_INDEXADA) -> int:
    """Ediciones fechadas de más de 4 semanas (/en-vivo/AAAA-MM-DD/ y
    /cine/AAAA-MM-DD/): noindex, follow y canonical propio.

    Nunca tuvieron impresiones en Search Console y entre ellas comparten
    título; varias de julio y agosto de 2026 además apuntaban su canonical a
    la portada de la sección. Con noindex dejan de contar como duplicado y
    Google sigue pasando por sus enlaces. Los archivos no se borran.
    """
    tocadas = 0
    for seccion in ("cine", "en-vivo"):
        d = root / seccion
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            idx = sub / "index.html"
            if not (sub.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", sub.name) and idx.exists()):
                continue
            if (jueves - date.fromisoformat(sub.name)).days <= dias:
                continue
            texto = idx.read_text(encoding="utf-8")
            if "noindex" in texto[:900]:
                continue
            propio = f'<link rel="canonical" href="https://movete.info/{seccion}/{sub.name}/">'
            nuevo, n = re.subn(r'<link rel="canonical" href="[^"]*">', propio, texto, count=1)
            m = re.search(r'<meta charset="?utf-8"?\s*/?>', nuevo, re.I)
            if not m:
                continue
            extra = '\n  <meta name="robots" content="noindex, follow">'
            if not n:
                extra += "\n  " + propio
            nuevo = nuevo[:m.end()] + extra + nuevo[m.end():]
            idx.write_text(nuevo, encoding="utf-8")
            tocadas += 1
    return tocadas


_MARCA_ALIAS_INI = "# --- Alias de obra (generado por movete-espectaculos, no editar a mano) ---"
_MARCA_ALIAS_FIN = "# --- fin alias de obra ---"


def escribir_redirects_alias(root: Path, alias: dict[str, str]) -> int:
    """301 reales para las variantes de un mismo show.

    La página del alias solo tenía meta refresh + noindex, que no traspasa a
    la principal lo que juntó la URL vieja. Workers aplica _redirects aunque
    exista un archivo en esa ruta, así que la página queda solo de respaldo.
    Las reglas viejas se conservan: una variante que deja de detectarse
    sigue redirigiendo mientras exista su página de alias.
    """
    ruta = root / "_redirects"
    if not ruta.exists():
        return 0
    texto = ruta.read_text(encoding="utf-8")
    pares: dict[str, str] = {}
    m = re.search(re.escape(_MARCA_ALIAS_INI) + r"\n(.*?)" + re.escape(_MARCA_ALIAS_FIN), texto, re.S)
    if m:
        for linea in m.group(1).splitlines():
            partes = linea.split()
            if len(partes) == 3 and partes[2] == "301":
                pares[partes[0]] = partes[1]
        texto = (texto[:m.start()] + texto[m.end():]).rstrip("\n") + "\n"
    for variante, principal in alias.items():
        if variante and principal and variante != principal:
            pares[f"/en-vivo/obra/{variante}/"] = f"/en-vivo/obra/{principal}/"
    # Sin cadenas ni vueltas: si el destino también es alias, se va al final.
    def final(u: str) -> str:
        vistos = {u}
        while pares.get(u) and pares[u] not in vistos:
            u = pares[u]
            vistos.add(u)
        return u
    def pagina(u: str) -> Path:
        return root / u.strip("/") / "index.html"

    def es_alias(u: str) -> bool:
        # Solo se redirige una URL cuya página hoy es de alias: si esa
        # variante volvió a ser un show con página propia, la regla se cae.
        try:
            return 'http-equiv="refresh"' in pagina(u).read_text(encoding="utf-8")[:900]
        except OSError:
            return False

    limpio = {o: final(d) for o, d in pares.items()}
    limpio = {o: d for o, d in limpio.items()
              if o != d and d not in limpio and es_alias(o) and pagina(d).exists() and not es_alias(d)}
    if not limpio:
        ruta.write_text(texto, encoding="utf-8")
        return 0
    bloque = "\n".join([_MARCA_ALIAS_INI] + [f"{o} {d} 301" for o, d in sorted(limpio.items())]
                       + [_MARCA_ALIAS_FIN])
    ruta.write_text(texto.rstrip("\n") + "\n\n" + bloque + "\n", encoding="utf-8")
    return len(limpio)


def generar_sitemap(en_vivo_dir: Path, hoy: date | None = None) -> None:
    """Regenera sitemap.xml: páginas fijas, categorías vigentes (indexables) y
    TODAS las ediciones archivadas de cine y en-vivo (URLs permanentes)."""
    root = Path(en_vivo_dir).parent
    base = "https://movete.info"

    def es_fecha(nombre: str) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", nombre))

    def indexable(idx: Path) -> bool:
        return idx.exists() and "noindex" not in idx.read_text(encoding="utf-8")[:900]

    urls: list[tuple[str, str]] = [("/", ""), ("/cine/", ""), ("/cine/pelis/", ""), ("/en-vivo/", "")]

    # Categorías de en-vivo con página indexable (se saltan las noindex/vacías)
    envivo = root / "en-vivo"
    if envivo.is_dir():
        for sub in sorted(envivo.iterdir()):
            if not sub.is_dir() or es_fecha(sub.name) or sub.name in ("actividades", "obra", "sala"):
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
            # Las ediciones retiradas (noindex, ver retirar_ediciones_viejas)
            # quedan afuera: no se le pide a Google que indexe lo que no va.
            if sub.is_dir() and es_fecha(sub.name) and indexable(sub / "index.html"):
                urls.append((f"/{seccion}/{sub.name}/", sub.name))

    # Páginas fijas por sala de cine (las escribe movete-cine)
    cine_sala_dir = root / "cine" / "sala"
    if cine_sala_dir.is_dir():
        for sub in sorted(cine_sala_dir.iterdir()):
            if sub.is_dir() and (sub / "index.html").exists():
                urls.append((f"/cine/sala/{sub.name}/", ""))

    # Páginas por sala (evergreen, indexables)
    sala_dir = root / "en-vivo" / "sala"
    if sala_dir.is_dir():
        for sub in sorted(sala_dir.iterdir()):
            if sub.is_dir() and (sub / "index.html").exists():
                urls.append((f"/en-vivo/sala/{sub.name}/", ""))

    # Páginas por obra con funciones vigentes (las noindex quedan afuera)
    obra_dir = root / "en-vivo" / "obra"
    if obra_dir.is_dir():
        for sub in sorted(obra_dir.iterdir()):
            idx = sub / "index.html"
            if sub.is_dir() and idx.exists() and "noindex" not in idx.read_text(encoding="utf-8")[:900]:
                urls.append((f"/en-vivo/obra/{sub.name}/", ""))

    vistos: set[str] = set()
    lineas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    fechas = fechas_de_cambio(root, urls, hoy or hoy_argentina())
    for loc, _ in urls:
        if loc in vistos:
            continue
        vistos.add(loc)
        lastmod = fechas.get(loc, "")
        if lastmod:
            lineas.append(f"  <url><loc>{base}{loc}</loc><lastmod>{lastmod}</lastmod></url>")
        else:
            lineas.append(f"  <url><loc>{base}{loc}</loc></url>")
    lineas.append("</urlset>")
    try:
        (root / "sitemap.xml").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[sitemap] no se pudo escribir: {e}")


def escribir_archivo(en_vivo_dir: Path, jueves: date) -> None:
    """/en-vivo/archivo/: enlaza todas las salas, los shows indexables y las
    ediciones semanales de en vivo y cine. Es el punto de entrada que les
    faltaba a esas páginas: sin ningún enlace interno Google las trata como
    huérfanas (Ahrefs, nov/2026: 118 páginas del sitemap sin enlaces)."""
    out = Path(en_vivo_dir)
    root = out.parent

    def h1_e_indexable(idx: Path) -> tuple[str, bool]:
        texto = idx.read_text(encoding="utf-8")
        m = re.search(r"<h1>(.*?)</h1>", texto, re.S)
        return (html.unescape(m.group(1).strip()) if m else idx.parent.name,
                "noindex" not in texto[:900])

    def lista(items: list[tuple[str, str]]) -> str:
        if not items:
            return '<p class="empty">Todavía no hay.</p>'
        lis = "".join(f'<li><a href="{esc(u)}">{esc(t)}</a></li>' for u, t in items)
        return f'<ul class="archivo-lista" style="line-height:1.7;columns:16rem">{lis}</ul>'

    def paginas(sub: str) -> list[tuple[str, str]]:
        d = out / sub
        res = []
        if d.is_dir():
            for c in d.iterdir():
                idx = c / "index.html"
                if c.is_dir() and idx.exists():
                    t, ok = h1_e_indexable(idx)
                    if ok:
                        res.append((f"/en-vivo/{sub}/{c.name}/", t))
        return sorted(res, key=lambda x: x[1].casefold())

    def ediciones(seccion: str) -> list[tuple[str, str]]:
        d = root / seccion
        if not d.is_dir():
            return []
        res = []
        for c in sorted(d.iterdir(), reverse=True):
            if c.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c.name) and (c / "index.html").exists():
                f = date.fromisoformat(c.name)
                res.append((f"/{seccion}/{c.name}/", f"Semana del {f.day}/{f.month}/{f.year}"))
        return res

    salas, shows = paginas("sala"), paginas("obra")
    cuerpo = (lista(salas)
              + f'<h2 style="margin-top:28px">Shows ({len(shows)})</h2>' + lista(shows)
              + '<h2 style="margin-top:28px">Ediciones de En vivo</h2>' + lista(ediciones("en-vivo"))
              + '<h2 style="margin-top:28px">Ediciones de Cine</h2>' + lista(ediciones("cine")))
    pagina = PLANTILLA_VENUE.format(
        page_title="Archivo: salas, shows y ediciones · MoVeTe",
        page_description=("Todas las salas, los shows y las ediciones semanales de "
                          "MoVeTe, la cartelera de teatro, música, stand up y cine de La Plata."),
        page_url="https://movete.info/en-vivo/archivo/",
        og_image="https://movete.info/assets/images/cartelera-en-vivo.jpg",
        bloque_schema="",
        eyebrow="Archivo de MoVeTe",
        h1="Salas, shows y ediciones",
        bloque_mapa="",
        titulo_agenda=f"Salas ({len(salas)})",
        bloque_eventos=cuerpo,
        anio=jueves.year,
    ).replace(' aria-current="page"', "", 1)
    destino = out / "archivo" / "index.html"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(pagina, encoding="utf-8")


_DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _fecha_corta(ev: dict) -> str:
    """'vie 26/9' a partir de 'YYYY-MM-DD HH:MM:SS'; '' si no se puede."""
    try:
        d = date.fromisoformat((ev.get("fecha") or "")[:10])
    except ValueError:
        return ""
    return f"{_DIAS_CORTOS[d.weekday()]} {d.day}/{d.month}"


DESC_MAX = 155


def recortar_desc(texto: str, maximo: int = DESC_MAX) -> str:
    """Meta description de no más de ~155 caracteres: es lo que Google
    muestra en el móvil; lo que sobra se corta igual y se pierde la cola
    (Ahrefs, nov/2026: 496 de 965 páginas pasadas de largo)."""
    texto = " ".join(texto.split())
    if len(texto) <= maximo:
        return texto
    corte = texto[: maximo - 1]
    if " " in corte:
        corte = corte[: corte.rfind(" ")]
    return corte.rstrip(" ,;:·—-(") + "…"


def _sumar_si_entra(desc: str, cola: str, maximo: int = DESC_MAX) -> str:
    return desc + cola if len(desc + cola) <= maximo else desc


def titulo_y_descripcion_venue(nombre: str, direccion: str, eventos_sala: list[dict]) -> tuple[str, str]:
    """Title y meta description de la página de una sala.

    Google ya muestra estas páginas (impresiones altas) pero el CTR era ~1 %
    con un título genérico ("Qué hay en X"). Mostrar lo concreto — cuántas
    funciones, qué obra y qué día — es lo que hace clickear en el resultado.
    """
    titulos = []
    for ev in eventos_sala:
        t = _sin_gritos((ev.get("titulo") or "").strip())
        if t and t not in titulos:
            titulos.append(t)
    n = len(eventos_sala)
    # "Teatro X La Plata", salvo que el nombre ya diga La Plata.
    lugar = nombre if "la plata" in nombre.lower() else f"{nombre} La Plata"

    # "cartelera" es la palabra que la gente agrega al buscar una sala
    # ("teatro argentino la plata cartelera", "pasaje dardo rocha
    # cartelera"): va siempre en el título. Lo concreto (cuántas funciones,
    # qué día) queda como cola, que es lo que hace clickear.
    if n == 0:
        base, extra = f"{lugar}: cartelera y próximas funciones", ""
        desc = f"Cartelera de {nombre} en La Plata: próximas funciones, shows y cómo llegar."
    elif n == 1:
        cuando = _fecha_corta(eventos_sala[0])
        base = f"{lugar}: cartelera"
        extra = f" · {titulos[0]}" + (f" ({cuando})" if cuando else "")
        desc = (f"Cartelera de {nombre}: {titulos[0]}"
                + (f", {cuando}" if cuando else "") + ". Horario, entradas y cómo llegar.")
    else:
        desde, hasta = _fecha_corta(eventos_sala[0]), _fecha_corta(eventos_sala[-1])
        base = f"{lugar}: cartelera"
        extra = f" · {n} funciones" + (f" ({desde} al {hasta})" if desde and hasta and desde != hasta else "")
        desc = ""
        for k in (3, 2, 1):
            muestra = " · ".join(titulos[:k]) + (" y más" if len(titulos) > k else "")
            desc = f"Cartelera de {nombre}: {muestra}. Horarios, entradas y cómo llegar."
            if len(desc) <= DESC_MAX:
                break

    # Google corta el título en ~60 caracteres. Se prueba de más completo a
    # menos: con cola y marca, con cola, solo la cola sin fecha, sin cola; y
    # si nada entra, se recorta el texto base con elipsis.
    marca = " · MoVeTe"
    cola_corta = re.sub(r"\s*\([^)]*\)$", "", extra)
    title = next(
        (t for t in (base + extra + marca, base + extra, base + cola_corta, base + marca, base)
         if len(t) <= 62),
        base[:61].rstrip(" ,·:(") + "…",
    )
    if direccion:
        desc = _sumar_si_entra(desc, f" Dirección: {direccion}.")
    return title, recortar_desc(desc)


def schema_migas(pasos: list[tuple[str, str]]) -> str:
    """BreadcrumbList: Google muestra "MoVeTe › En vivo › Sala X" en el
    resultado en lugar de la URL cruda. pasos = [(nombre, url), ...]."""
    items = [{"@type": "ListItem", "position": i, "name": n, "item": u}
             for i, (n, u) in enumerate(pasos, 1)]
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


MIGAS_BASE = [("MoVeTe", "https://movete.info/"), ("En vivo", "https://movete.info/en-vivo/")]


def render_otros_shows_sala(anteriores: list[dict] | None) -> str:
    """Shows de la sala que hoy no tienen funciones (pasados o que la fuente
    dejó de traer). Sin este enlace sus páginas quedan huérfanas: están en el
    sitemap pero ninguna página las enlaza y Google las valora poco."""
    if not anteriores:
        return ""
    items = "".join(
        f'<li><a href="/en-vivo/obra/{esc(a["slug"])}/">{esc(a["titulo"])}</a>'
        + (f' · {esc(_fecha_larga(a["fecha"]))}' if a.get("fecha") else "") + "</li>"
        for a in anteriores)
    return ('<h2 style="margin-top:28px">Otros shows en esta sala</h2>'
            f'<ul class="sala-anteriores" style="line-height:1.7">{items}</ul>')


def render_pagina_venue(venue: dict, eventos_sala: list[dict], jueves: date,
                        anteriores: list[dict] | None = None) -> str:
    """Pagina evergreen de una sala: /en-vivo/sala/<slug>/."""
    nombre = venue["nombre"]
    slug = venue["slug"]
    direccion = (venue.get("direccion") or "").strip()
    page_url = f"https://movete.info/en-vivo/sala/{slug}/"
    n = len(eventos_sala)

    page_title, page_description = titulo_y_descripcion_venue(nombre, direccion, eventos_sala)
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

    web = venue_web(slug)
    if web:
        bloque_mapa += (
            f'\n      <p class="venue-social"><a href="{esc(web)}" target="_blank"'
            f' rel="noopener">Web oficial y entradas de {esc(nombre)} →</a></p>'
        )
    ig = venue_instagram(slug)
    if ig:
        handle = ig.lstrip("@")
        bloque_mapa += (
            f'\n      <p class="venue-social"><a href="https://instagram.com/{esc(handle)}"'
            f' target="_blank" rel="noopener">Instagram @{esc(handle)}</a></p>'
        )

    if eventos_sala:
        bloque_eventos = "".join(render_evento(e) for e in eventos_sala)
        titulo_agenda = f"Próximas funciones ({n})"
    else:
        bloque_eventos = ('<p class="empty">Por ahora no hay funciones cargadas en '
                          'esta sala. Volvé a mirar la semana que viene.</p>')
        titulo_agenda = "Agenda"

    place = {"@context": "https://schema.org", "@type": "Place",
             "name": nombre, "url": page_url}
    place["address"] = postal_address(direccion)
    if web:
        place["sameAs"] = web
    schema = '<script type="application/ld+json">' + json.dumps(place, ensure_ascii=False) + "</script>"
    if eventos_sala:
        schema += render_schema_eventos(eventos_sala)
    schema += schema_migas(MIGAS_BASE + [(nombre, page_url)])

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
        bloque_eventos=bloque_eventos + render_otros_shows_sala(anteriores),
        anio=jueves.year,
    )


def _sin_gritos(titulo: str) -> str:
    """'GABRIEL ROLÓN "PALABRA PLENA"' -> 'Gabriel Rolón "Palabra Plena"'.
    Las fuentes a veces cargan todo en mayúsculas; en el resultado de Google
    se lee como spam."""
    letras = [c for c in titulo if c.isalpha()]
    if len(letras) > 6 and sum(c.isupper() for c in letras) / len(letras) > 0.8:
        return titulo.title()
    return titulo


def _sala_corta(nombre: str) -> str:
    """'Hipódromo de La Plata' -> 'Hipódromo'. En el título ya dice
    'en La Plata'; repetirlo gasta caracteres que Google corta."""
    corto = re.sub(r"\s*(?:-|,|de|en)?\s*La Plata$", "", nombre or "", flags=re.I).strip()
    return corto or (nombre or "")


def _hora(ev: dict) -> str:
    """'21:30' a partir de 'YYYY-MM-DD HH:MM:SS'; '' si no hay hora."""
    h = (ev.get("fecha") or "")[11:16]
    if not re.fullmatch(r"\d\d:\d\d", h) or h == "00:00":
        return ""
    return f"{int(h[:2])}" if h.endswith(":00") else h


def titulo_y_descripcion_obra(titulo: str, eventos_obra: list[dict]) -> tuple[str, str]:
    """Title y description de la página de una obra.

    Search Console (oct/2026): estas páginas juntan miles de impresiones con
    CTR de 0,2-0,4 % ("un poco de ruido la plata": 1.688 impr., 3 clics).
    Quien busca un show quiere saber cuándo y dónde antes de clickear: va en
    el título el día y la sala, y en la descripción la hora, la dirección y
    que hay link a las entradas. Google corta el título en ~60 caracteres."""
    titulo = _sin_gritos(titulo)
    salas, direcciones = [], []
    for ev in eventos_obra:
        info = venue_info(evento_lugar(ev))
        if info["nombre"] and info["nombre"] not in salas:
            salas.append(info["nombre"])
            direcciones.append(info.get("direccion") or "")
    n = len(eventos_obra)
    una_sala = len(salas) == 1
    donde = salas[0] if una_sala else ("varias salas" if salas else "")
    sala_t = _sala_corta(salas[0]) if una_sala else ""
    base = f"{titulo} en La Plata"
    marca = " · MoVeTe"

    if n == 1:
        cuando = _fecha_corta(eventos_obra[0])
        hora = _hora(eventos_obra[0])
        colas = [f" ({cuando}, {sala_t})" if cuando and sala_t else "",
                 f" ({cuando})" if cuando else ""]
        desc = f"{titulo} en La Plata: {cuando}" + (f" a las {hora} h" if hora else "")
        desc += f" en {donde}" if donde else ""
    else:
        desde, hasta = _fecha_corta(eventos_obra[0]), _fecha_corta(eventos_obra[-1])
        rango = f"{desde} al {hasta}" if desde and hasta and desde != hasta else desde
        colas = [f" ({rango}, {sala_t})" if rango and sala_t else "",
                 f": {n} funciones ({rango})" if rango else "",
                 f" ({n} funciones desde {desde})" if desde else "",
                 f": {n} funciones"]
        desc = f"{titulo} en La Plata: {n} funciones" + (f" del {rango}" if " al " in rango else "")
        desc += f" en {donde}" if donde else ""
    desc = desc.rstrip(":")
    if una_sala and direcciones[0]:
        desc = _sumar_si_entra(desc, f" ({direcciones[0]})", DESC_MAX - 30)
    desc += "."
    hay_link = any(str(e.get("url") or "").strip() for e in eventos_obra)
    for cola in ((" Link a las entradas, horarios y cómo llegar." if hay_link
                  else " Horarios, entradas y cómo llegar."), " Entradas y cómo llegar."):
        if len(desc + cola) <= DESC_MAX:
            desc += cola
            break
    desc = recortar_desc(desc)

    candidatos = []
    for c in [c for c in colas if c] + [""]:
        candidatos += [base + c + marca, base + c]
    title = next((t for t in candidatos if len(t) <= 62), base[:61].rstrip(" ,·:(") + "…")
    return title, desc


# ---------------------------------------------------------------- obras pasadas
# Cuando un show termina, su página no se borra ni se saca de Google: queda
# un año con "la última vez en La Plata" y lo que hay parecido esta semana.
# Los artistas que vuelven (Conociendo Rusia, La Vela Puerca) ya tienen la
# URL posicionada cuando anuncian fecha. Pasado el año, noindex.
# El dato de la última función viaja en un <meta name="movete-ultima"> dentro
# de la propia página, así sobrevive entre corridas sin archivo aparte.

DIAS_OBRA_PASADA_INDEXADA = 365
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def datos_ultima_funcion(titulo: str, eventos_obra: list[dict]) -> dict:
    """Lo mínimo para armar la página cuando el show ya pasó."""
    ev = max(eventos_obra, key=lambda e: e.get("fecha", ""))
    vc = venue_canonico(evento_lugar(ev)) or {}
    imagen = next((str(e.get("imagen") or "").strip() for e in eventos_obra
                   if str(e.get("imagen") or "").strip()), "")
    return {"titulo": titulo, "fecha": (ev.get("fecha") or "")[:10],
            "sala": vc.get("nombre") or venue_info(evento_lugar(ev))["nombre"],
            "sala_slug": vc.get("slug", ""), "categoria": ev.get("categoria", "otros"),
            "imagen": imagen}


def meta_ultima(datos: dict) -> str:
    return f'<meta name="movete-ultima" content="{esc(json.dumps(datos, ensure_ascii=False))}">'


def leer_ultima(html_viejo: str) -> dict:
    """Recupera la última función de una página ya generada: primero del
    <meta movete-ultima>; si no está (páginas de antes de este cambio, que
    todavía tenían funciones), del JSON-LD de Event."""
    m = re.search(r'<meta name="movete-ultima" content="([^"]*)">', html_viejo)
    if m:
        try:
            return json.loads(html.unescape(m.group(1)))
        except ValueError:
            pass
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html_viejo, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    evs = [it.get("item", {}) for it in data.get("itemListElement", [])]
    evs = [e for e in evs if e.get("@type") == "Event" and e.get("startDate")]
    if not evs:
        return {}
    ult = max(evs, key=lambda e: e["startDate"])
    sala = (ult.get("location") or {}).get("name", "")
    vc = venue_canonico(sala) or {}
    cat = ""
    mc = re.search(r'<p class="eyebrow">(.*?) en La Plata</p>', html_viejo)
    if mc:
        etiqueta = html.unescape(mc.group(1)).strip().casefold()
        cat = next((k for k, v in CAT_LABEL.items() if v.casefold() == etiqueta), "")
    return {"titulo": html.unescape(ult.get("name", "")), "fecha": ult["startDate"][:10],
            "sala": sala, "sala_slug": vc.get("slug", ""), "categoria": cat or "otros",
            "imagen": next((e.get("image", "") for e in evs if e.get("image")), "")}


def _fecha_larga(iso: str) -> str:
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    return f"{_DIAS_SEMANA[d.weekday()]} {d.day} de {_MESES[d.month - 1]} de {d.year}"


def render_parecidos(parecidos: list[dict]) -> str:
    if not parecidos:
        return ""
    items = "".join(
        f'<li><a href="/en-vivo/obra/{esc(p["slug"])}/">{esc(p["titulo"])}</a>'
        f' · {esc(p["cuando"])}{(" · " + esc(p["sala"])) if p.get("sala") else ""}</li>'
        for p in parecidos)
    return ('<h2 style="margin-top:28px">Parecido, en las próximas semanas</h2>'
            f'<ul class="obra-parecidos" style="line-height:1.7">{items}</ul>')


_CATS_COMEDIA = {"stand-up", "humor", "impro"}


def bloque_sponsor_comedia(eventos_obra: list[dict]) -> str:
    """Espacio promocional de Tres Empanadas en las páginas de shows de
    comedia. Va identificado como promoción (DECISIONES.md: publicidad y
    editorial separadas) y no sale en los shows del propio club."""
    if not eventos_obra:
        return ""
    if not any(e.get("categoria") in _CATS_COMEDIA for e in eventos_obra):
        return ""
    if any("tres empanadas" in (evento_lugar(e) + " " + evento_titulo(e)).casefold()
           for e in eventos_obra):
        return ""
    utm = "utm_source=movete&amp;utm_medium=obra&amp;utm_campaign=sponsor"
    return f"""
    <section class="ad-box sponsor-card" style="margin-top:28px">
      <div class="sponsor-kicker">
        <img class="sponsor-logo" src="/assets/images/tres-empanadas-comedia.png" alt="Tres Empanadas Comedia" width="36" height="36" decoding="async" loading="lazy">
        <p class="ad-label">Espacio promocional</p>
      </div>
      <h2>¿Más stand up en La Plata?</h2>
      <p>Tres Empanadas Comedia: shows a la gorra todos los jueves y viernes.</p>
      <a class="button small" href="https://tresempanadas.com.ar/reservas/?{utm}">Reservar lugar</a>
      <a class="sponsor-sublink" href="/en-vivo/sala/tres-empanadas-comedia/">Ver las próximas funciones →</a>
    </section>"""


def render_pagina_obra(slug: str, eventos_obra: list[dict], jueves: date,
                       titulo_viejo: str = "", titulo_principal: str = "",
                       alias_de: str = "", ultima: dict | None = None,
                       parecidos: list[dict] | None = None) -> str:
    """Página propia de una obra/show: /en-vivo/obra/<slug>/.

    Con funciones: todas las fechas y salas, JSON-LD Event por función.
    Sin funciones (la obra ya pasó): se deja la página para no generar un
    404, pero con noindex para que Google la saque del índice.
    """
    page_url = f"https://movete.info/en-vivo/obra/{slug}/"
    if alias_de:
        # Variante de otro show: se deja la URL (no se rompe ningún enlace),
        # pero no se indexa y manda a la página principal.
        destino = f"/en-vivo/obra/{alias_de}/"
        titulo = titulo_viejo or slug.replace("-", " ").capitalize()
        page_title = f"{titulo} · MoVeTe"
        page_description = f"{titulo}: las funciones están en la página principal de este show."
        eyebrow = "En La Plata"
        titulo_agenda = "Funciones"
        bloque_eventos = (f'<p class="empty">Las funciones de este show están en '
                          f'<a href="{esc(destino)}">su página principal →</a></p>')
        schema, bloque_intro = "", ""
        robots = (f'<meta name="robots" content="noindex, follow">\n  '
                  f'<meta http-equiv="refresh" content="0; url={esc(destino)}">')
        og_image = "https://movete.info/assets/images/cartelera-en-vivo.jpg"
        # La redireccion de verdad (301) sale de _redirects, ver
        # escribir_redirects_alias(). Esta pagina queda de respaldo.
        page_url = f"https://movete.info{destino}"
    elif eventos_obra:
        titulo = _sin_gritos(titulo_principal or evento_titulo(eventos_obra[0]))
        cat = eventos_obra[0].get("categoria", "otros")
        page_title, page_description = titulo_y_descripcion_obra(titulo, eventos_obra)
        eyebrow = f"{cat_label(cat)} en La Plata"
        n = len(eventos_obra)
        titulo_agenda = "Función" if n == 1 else f"Funciones ({n})"
        # El afiche va una sola vez arriba; en las tarjetas de función se saca.
        bloque_eventos = "".join(
            re.sub(r'\s*<div class="event-card-media">.*?</div>', "",
                   render_evento(e, link_obra=False), flags=re.S).replace(" has-media", "")
            for e in eventos_obra)
        bloque_eventos += bloque_sponsor_comedia(eventos_obra)
        schema = render_schema_eventos(eventos_obra)
        imagen = next((str(e.get("imagen") or "").strip() for e in eventos_obra
                       if str(e.get("imagen") or "").strip()), "")
        bloque_intro = ""
        if imagen:
            # Alto fijo: el lugar queda reservado antes de que llegue la imagen y no
            # empuja el resto de la página (CLS). Es lo primero que se ve: sin lazy.
            bloque_intro = (f'<img class="obra-afiche" src="{esc(imagen)}" alt="{esc(titulo)}" '
                            'style="display:block;height:min(420px,90vw);width:auto;max-width:100%;'
                            'object-fit:contain;border-radius:18px;margin-top:12px" '
                            'fetchpriority="high" decoding="async" '
                            'onerror="this.style.visibility=\'hidden\'">')
        og_image = imagen or "https://movete.info/assets/images/cartelera-en-vivo.jpg"
        robots = meta_ultima(datos_ultima_funcion(titulo, eventos_obra))
    elif ultima and ultima.get("fecha") and (
            jueves - date.fromisoformat(ultima["fecha"][:10])).days <= DIAS_OBRA_PASADA_INDEXADA:
        titulo = _sin_gritos(titulo_viejo or ultima.get("titulo") or slug.replace("-", " ").capitalize())
        sala = ultima.get("sala", "")
        cuando = _fecha_larga(ultima["fecha"])
        page_title = next((t for t in (f"{titulo} en La Plata: próximas fechas · MoVeTe",
                                       f"{titulo} en La Plata: próximas fechas",
                                       f"{titulo} en La Plata · MoVeTe") if len(t) <= 62),
                          f"{titulo} en La Plata"[:61] + "…")
        # Si la fecha guardada todavía no llegó (la fuente dejó de traer el
        # show), no se puede decir "fue": se dice que estaba anunciada.
        ya_paso = ultima["fecha"][:10] < jueves.isoformat()
        verbo = "la última función fue el" if ya_paso else "tenía función anunciada el"
        page_description = (f"{titulo} en La Plata: {verbo} {cuando}"
                            + (f" en {sala}" if sala else "") + ".")
        page_description = recortar_desc(_sumar_si_entra(
            page_description, " Las próximas fechas aparecen acá apenas se anuncien."))
        cat = ultima.get("categoria") or "otros"
        eyebrow = f"{cat_label(cat)} en La Plata"
        titulo_agenda = "Próximas fechas"
        link_sala = (f' en <a href="/en-vivo/sala/{esc(ultima["sala_slug"])}/">{esc(sala)}</a>'
                     if ultima.get("sala_slug") and sala else (f" en {esc(sala)}" if sala else ""))
        bloque_eventos = (
            '<p class="empty">Por ahora no hay funciones anunciadas en La Plata. '
            + (f'La última fue el {esc(cuando)}{link_sala}.</p>' if ya_paso else
               f'Tenía función anunciada el {esc(cuando)}{link_sala}: confirmá con la sala.</p>')
            + render_parecidos(parecidos or [])
            + '<p style="margin-top:18px"><a href="/en-vivo/">Mirá todo lo que hay esta semana →</a></p>')
        schema = ""
        imagen = ultima.get("imagen", "")
        bloque_intro = ""
        if imagen:
            bloque_intro = (f'<img class="obra-afiche" src="{esc(imagen)}" alt="{esc(titulo)}" '
                            'style="display:block;height:min(320px,80vw);width:auto;max-width:100%;'
                            'object-fit:contain;border-radius:18px;margin-top:12px;opacity:.85" '
                            'decoding="async" onerror="this.style.display=\'none\'">')
        og_image = imagen or "https://movete.info/assets/images/cartelera-en-vivo.jpg"
        robots = meta_ultima(ultima)
    else:
        titulo = titulo_viejo or slug.replace("-", " ").capitalize()
        page_title = f"{titulo} · MoVeTe"
        page_description = f"{titulo}: por ahora no hay funciones anunciadas en La Plata."
        eyebrow = "En La Plata"
        titulo_agenda = "Funciones"
        bloque_eventos = ('<p class="empty">Por ahora no hay funciones anunciadas. '
                          '<a href="/en-vivo/">Mirá qué hay esta semana →</a></p>')
        schema, bloque_intro, robots = "", "", '<meta name="robots" content="noindex">'
        if ultima:
            robots += "\n  " + meta_ultima(ultima)
        og_image = "https://movete.info/assets/images/cartelera-en-vivo.jpg"

    if not alias_de and "noindex" not in robots:
        sala_vc = None
        if eventos_obra:
            salas = {(venue_canonico(evento_lugar(e)) or {}).get("slug") for e in eventos_obra}
            if len(salas) == 1:
                sala_vc = venue_canonico(evento_lugar(eventos_obra[0]))
        elif ultima and ultima.get("sala_slug") and ultima.get("sala"):
            sala_vc = {"slug": ultima["sala_slug"], "nombre": ultima["sala"]}
        pasos = list(MIGAS_BASE)
        if sala_vc:
            pasos.append((sala_vc["nombre"], f"https://movete.info/en-vivo/sala/{sala_vc['slug']}/"))
        schema += schema_migas(pasos + [(titulo, page_url)])

    html = PLANTILLA_VENUE.format(
        page_title=esc(page_title),
        page_description=esc(page_description),
        page_url=esc(page_url),
        og_image=esc(og_image),
        bloque_schema=schema,
        eyebrow=esc(eyebrow),
        h1=esc(titulo),
        bloque_mapa=bloque_intro,
        titulo_agenda=esc(titulo_agenda),
        bloque_eventos=bloque_eventos,
        anio=jueves.year,
    )
    if robots:
        html = html.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n  ' + robots, 1)
    return html.replace("Confirmá horarios y disponibilidad con la sala.",
                        "Confirmá horarios y disponibilidad con la sala o la ticketera.")


# ---------------------------------------------------------------- hoy / finde
# Páginas con URL fija para las búsquedas "qué hacer hoy en La Plata" y "qué
# hacer este fin de semana". Las ediciones fechadas no juntan historia en
# Google (cada semana es una URL nueva); éstas sí. Se regeneran en cada
# corrida (martes, jueves y domingo) y un script en la página oculta los días
# que ya pasaron, así nunca muestran el pasado aunque la corrida sea vieja.

_SCRIPT_DIAS_PASADOS = """
<script>
(function () {
  var hoy = new Date().toLocaleDateString("en-CA", {timeZone: "America/Argentina/Buenos_Aires"});
  var visibles = 0;
  document.querySelectorAll("[data-dia]").forEach(function (s) {
    if (s.getAttribute("data-dia") < hoy) { s.style.display = "none"; } else { visibles++; }
    if (s.getAttribute("data-dia") === hoy) {
      var h = s.querySelector("h2"); if (h) { h.textContent = "Hoy · " + h.textContent; }
    }
  });
  if (!visibles) { var v = document.getElementById("agenda-vacia"); if (v) { v.hidden = false; v.style.display = ""; } }
})();
</script>"""

_DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def hoy_argentina() -> date:
    """Fecha de hoy en La Plata (el runner de GitHub corre en UTC)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    except Exception:
        return (datetime.utcnow() - timedelta(hours=3)).date()


def dias_finde(hoy: date) -> list[date]:
    """Viernes, sábado y domingo del finde que viene. Si hoy ya es finde,
    el finde en curso (desde hoy)."""
    wd = hoy.weekday()
    if wd >= 4:  # viernes, sábado o domingo
        viernes = hoy - timedelta(days=wd - 4)
    else:
        viernes = hoy + timedelta(days=4 - wd)
    return [viernes + timedelta(days=i) for i in range(3)]


def _bloques_por_dia(eventos: list[dict], dias: list[date]) -> tuple[str, list[dict]]:
    por_dia: dict[date, list[dict]] = defaultdict(list)
    for ev in eventos:
        try:
            d = parse_fecha(ev["fecha"]).date()
        except Exception:
            continue
        if d in dias:
            por_dia[d].append(ev)
    bloques, usados = [], []
    for d in dias:
        evs = sorted(por_dia.get(d, []), key=lambda e: e.get("fecha", ""))
        if not evs:
            continue
        usados += evs
        filas = "\n".join(render_evento(ev) for ev in evs)
        bloques.append(
            f'\n      <section class="day-block" data-dia="{d.isoformat()}">'
            f'\n        <h2>{esc(etiqueta_dia(d))}</h2>'
            f'\n        <div class="grid cards">{filas}</div>\n      </section>')
    return "\n".join(bloques), usados


def render_pagina_agenda(tipo: str, eventos: list[dict], hoy: date) -> str:
    """tipo 'hoy' (los próximos 7 días, empezando por hoy) o 'fin-de-semana'."""
    eventos = [e for e in normalizar_categorias(eventos)
               if e.get("categoria") != "cine" and e.get("fecha")]
    if tipo == "hoy":
        dias = [hoy + timedelta(days=i) for i in range(7)]
        page_title = "Qué hacer hoy en La Plata · Teatro, recitales y stand up · MoVeTe"
        h1 = "Qué hacer hoy en La Plata"
        eyebrow = "La Plata · Agenda del día"
        intro = ("Teatro, música en vivo, stand up y más para hoy en La Plata. "
                 "Más abajo, lo de los próximos días.")
        titulo_agenda = "Agenda día por día"
        otro = '<a href="/en-vivo/fin-de-semana/">Ver este fin de semana →</a>'
    else:
        dias = dias_finde(hoy)
        v, sab, dom = dias
        rango = (f"viernes {v.day}, sábado {sab.day} y domingo {dom.day} de {MESES[dom.month]}"
                 if v.month == dom.month else
                 f"viernes {v.day}/{v.month}, sábado {sab.day}/{sab.month} y domingo {dom.day}/{dom.month}")
        page_title = "Qué hacer este fin de semana en La Plata · Shows y salidas · MoVeTe"
        h1 = "Qué hacer este fin de semana en La Plata"
        eyebrow = f"La Plata · Finde del {v.day}/{v.month} al {dom.day}/{dom.month}"
        intro = f"Teatro, recitales, stand up y salidas para el {rango} en La Plata."
        titulo_agenda = "Viernes, sábado y domingo"
        otro = '<a href="/en-vivo/hoy/">Ver qué hay hoy →</a>'

    bloques, usados = _bloques_por_dia(eventos, dias)
    n = len(usados)
    if tipo == "hoy":
        page_description = (f"Qué hacer hoy en La Plata: {n} funciones de teatro, música en vivo, "
                            "stand up y más para hoy y los próximos días. Horarios, salas y entradas.")
    else:
        page_description = (f"Qué hacer este fin de semana en La Plata: {n} funciones el {rango}. "
                            "Teatro, recitales, stand up y salidas, con horarios y entradas.")
    vacia = ('<p class="empty" id="agenda-vacia"{}>Ya no quedan funciones cargadas para estos días. '
             '<a href="/en-vivo/">Mirá la cartelera de la semana →</a></p>')
    cuerpo = (bloques + "\n      " + vacia.format(' hidden style="display:none"') if bloques else vacia.format(""))
    cuerpo += _SCRIPT_DIAS_PASADOS
    accesos = (f'<p class="home-lead">{esc(intro)}</p>\n      <p class="venue-social">{otro} · '
               '<a href="/en-vivo/teatro/">Teatro</a> · <a href="/en-vivo/musica/">Recitales</a> · '
               '<a href="/en-vivo/stand-up/">Stand up</a> · <a href="/cine/">Cine</a></p>')
    page_url = f"https://movete.info/en-vivo/{tipo}/"
    html_doc = PLANTILLA_VENUE.format(
        page_title=esc(page_title),
        page_description=esc(recortar_desc(page_description)),
        page_url=esc(page_url),
        og_image="https://movete.info/assets/images/cartelera-en-vivo.jpg",
        bloque_schema=render_schema_eventos(usados),
        eyebrow=esc(eyebrow),
        h1=esc(h1),
        bloque_mapa=accesos,
        titulo_agenda=esc(titulo_agenda),
        bloque_eventos=cuerpo,
        anio=hoy.year,
    )
    if not usados:
        html_doc = html_doc.replace('<meta charset="utf-8">',
                                    '<meta charset="utf-8">\n  <meta name="robots" content="noindex, follow">', 1)
    return html_doc


def escribir_paginas_agenda(eventos: list[dict], out: Path, hoy: date | None = None) -> list[str]:
    hoy = hoy or hoy_argentina()
    salidas = []
    for tipo in ("hoy", "fin-de-semana"):
        destino = out / tipo / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(render_pagina_agenda(tipo, eventos, hoy), encoding="utf-8")
        salidas.append(str(destino))
    return salidas


def render_pagina_lo_que_se_viene(eventos: list[dict], jueves: date) -> str:
    """Página evergreen con TODOS los grandes shows anunciados (venues masivos,
    fechas futuras): /en-vivo/lo-que-se-viene/. Imán de SEO para 'recitales La Plata'."""
    cuerpo = render_lo_que_se_viene(eventos, jueves)
    futuros = [
        ev for ev in eventos
        if ev.get("fecha") and not en_esta_semana(ev["fecha"], jueves)
        and venue_masivo(evento_lugar(ev))
    ]
    futuros.sort(key=lambda e: e.get("fecha", ""))
    schema = render_schema_eventos(futuros[:30]) if futuros else ""
    page_url = "https://movete.info/en-vivo/lo-que-se-viene/"
    return PLANTILLA_VENUE.format(
        page_title=esc("Grandes shows y recitales en La Plata · Próximas fechas · MoVeTe"),
        page_description=esc(
            "Todos los grandes shows y recitales anunciados en La Plata: Hipódromo, "
            "Teatro Argentino, Estadio Único y más. Fechas, artistas y cómo llegar."
        ),
        page_url=esc(page_url),
        og_image="https://movete.info/assets/images/cartelera-en-vivo.jpg",
        bloque_schema=schema,
        eyebrow=esc("La Plata · Grandes shows anunciados"),
        h1=esc("Lo que se viene en La Plata"),
        bloque_mapa="",
        titulo_agenda=esc("Próximos grandes shows"),
        bloque_eventos=cuerpo,
        anio=jueves.year,
    )


def completar_imagen_de_sala(eventos: list[dict]) -> int:
    """A los eventos sin imagen les pone la imagen por defecto de su sala, si tiene."""
    n = 0
    for ev in eventos:
        if str(ev.get("imagen") or "").strip():
            continue
        sala = venue_canonico(str(ev.get("lugar") or ""))
        imagen = venue_imagen(sala["slug"]) if sala else ""
        if imagen:
            ev["imagen"] = imagen
            n += 1
    return n


def generar(eventos_json_path: str, output_dir: str, hoy: date | None = None,
            solo_fechada: bool = False, hoy_real: date | None = None,
            afiches_dir: str | Path | None = None, sin_fechada: bool = False) -> dict:
    """Genera En Vivo.

    solo_fechada: escribe UNICAMENTE la edicion fechada (/en-vivo/<jueves>/) y
    regenera el sitemap. No toca la portada de En Vivo, las categorias, las
    salas ni las obras. Es la pre-edicion del martes: la semana que viene sale
    como URL propia para que Google la descubra antes, sin pisar la edicion
    vigente que sigue en pie hasta el miercoles.

    sin_fechada: lo contrario. Actualiza todo (portada de En Vivo, rubros,
    salas, obras, hoy y finde, sitemap) MENOS la edicion fechada vigente. Es la
    pasada intermedia del martes y del domingo: entran los shows nuevos sin
    reescribir /en-vivo/<jueves>/, que queda como la publico el jueves (si no,
    perderia los dias que ya pasaron, porque el scraper descarta lo pasado).

    afiches_dir: si viene, las imagenes se bajan una vez, se achican a WebP y
    se sirven desde /assets/afiches/ (ver imagenes.py). Sin el, URLs originales.
    """
    eventos, generado = cargar_eventos(eventos_json_path)
    completar_imagen_de_sala(eventos)
    resumen_afiches = localizar_imagenes(eventos, afiches_dir) if afiches_dir else None
    _ALIAS_OBRA.clear()
    _ALIAS_OBRA.update(calcular_alias_obras(normalizar_categorias(eventos)))
    html_doc, info = render_html(eventos, generado, hoy=hoy)

    jueves = jueves_de_edicion(hoy or date.today())
    eventos_semana = [
        e for e in normalizar_categorias(eventos)
        if e.get("categoria") != "cine" and e.get("fecha")
    ]
    cuentas = contar_categorias_semana(eventos_semana, jueves)

    out = Path(output_dir)
    slug_dir = out / info["slug"]
    if not sin_fechada:
        slug_dir.mkdir(parents=True, exist_ok=True)

    archive_index = slug_dir / "index.html"
    current_index = out / "index.html"

    # En las ediciones archivadas va un enlace a la edición vigente, para que
    # quien caiga en una vieja pase a la de esta semana. En la vigente no va.
    banner = (
        '<div class="edicion-vigente-bar">'
        '<a href="/en-vivo/">Ver la edición de esta semana →</a>'
        '</div>'
    )
    # La edicion archivada se re-renderiza con su propio canonical: es una URL
    # permanente y tiene que poder indexarse por si misma.
    html_archivo_doc, _ = render_html(
        eventos, generado, hoy=hoy,
        page_url=f"https://movete.info/en-vivo/{info['slug']}/",
    )
    html_archivo = html_archivo_doc.replace('<main>', f'<main>\n  {banner}', 1)

    if not sin_fechada:
        archive_index.write_text(html_archivo, encoding="utf-8")
    # Hoy y finde se escriben en todas las corridas, también en la
    # pre-edición del martes: usan la fecha real, no la de la edición.
    escribir_paginas_agenda(eventos, out, hoy_real)
    if solo_fechada:
        generar_sitemap(out)
        return {**info, "salida_archivo": str(archive_index), "solo_fechada": True,
                "afiches": resumen_afiches}
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

    # Páginas por obra/show: agrupa todas las funciones futuras por título.
    eventos_por_obra: dict[str, list[dict]] = defaultdict(list)
    for ev in normalizar_categorias(eventos):
        oslug = obra_slug(ev)
        if oslug:
            eventos_por_obra[oslug].append(ev)
    obra_root = out / "obra"
    salidas_obra = []
    titulos_por_slug: dict[str, str] = {}
    for ev in normalizar_categorias(eventos):
        base = _obra_slug_base(ev)
        if base and base not in titulos_por_slug:
            titulos_por_slug[base] = evento_titulo(ev)
    for oslug, evs in eventos_por_obra.items():
        evs = sorted(evs, key=lambda e: e.get("fecha", ""))
        destino = obra_root / oslug / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            render_pagina_obra(oslug, evs, jueves,
                               titulo_principal=titulos_por_slug.get(oslug, "")),
            encoding="utf-8")
        salidas_obra.append(str(destino))
    # Variantes del mismo show: la URL sigue existiendo, sin indexar, y manda
    # a la página principal.
    alias_total: dict[str, str] = dict(_ALIAS_OBRA)
    for variante, principal in _ALIAS_OBRA.items():
        destino = obra_root / variante / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            render_pagina_obra(variante, [], jueves,
                               titulo_viejo=titulos_por_slug.get(variante, ""),
                               alias_de=principal),
            encoding="utf-8")
    # Próximas obras por categoría, para "parecido" en las páginas de shows pasados.
    proximas_por_cat: dict[str, list[dict]] = defaultdict(list)
    for oslug, evs in sorted(eventos_por_obra.items(), key=lambda kv: min(e.get("fecha", "") for e in kv[1])):
        primera = min(evs, key=lambda e: e.get("fecha", ""))
        proximas_por_cat[primera.get("categoria", "otros")].append({
            "slug": oslug, "titulo": _sin_gritos(titulos_por_slug.get(oslug) or evento_titulo(primera)),
            "cuando": _fecha_corta(primera), "sala": venue_info(evento_lugar(primera))["nombre"]})
    # Obras sin funciones: un año indexadas con "la última vez" (ver
    # DIAS_OBRA_PASADA_INDEXADA); después, o si no hay datos, noindex (no 404).
    anteriores_por_sala: dict[str, list[dict]] = defaultdict(list)
    if obra_root.is_dir():
        existentes = {d.name for d in obra_root.iterdir() if (d / "index.html").exists()}
        for d in sorted(obra_root.iterdir()):
            idx = d / "index.html"
            if (d.is_dir() and d.name not in eventos_por_obra
                    and d.name not in _ALIAS_OBRA and idx.exists()):
                texto = idx.read_text(encoding="utf-8")
                m = re.search(r"<h1>(.*?)</h1>", texto, re.S)
                viejo = html.unescape(m.group(1).strip()) if m else ""
                principal = principal_existente(d.name, existentes)
                if principal:
                    alias_total[d.name] = principal
                ultima = {} if principal else leer_ultima(texto)
                idx.write_text(render_pagina_obra(
                    d.name, [], jueves, viejo, alias_de=principal, ultima=ultima,
                    parecidos=proximas_por_cat.get(ultima.get("categoria", ""), [])[:6]),
                    encoding="utf-8")
                if (ultima.get("sala_slug") and ultima.get("fecha")
                        and (jueves - date.fromisoformat(ultima["fecha"][:10])).days
                        <= DIAS_OBRA_PASADA_INDEXADA):
                    anteriores_por_sala[ultima["sala_slug"]].append({
                        "slug": d.name, "fecha": ultima["fecha"][:10],
                        "titulo": _sin_gritos(viejo or ultima.get("titulo") or d.name)})
    for lista in anteriores_por_sala.values():
        lista.sort(key=lambda a: a["fecha"], reverse=True)

    # Páginas por sala (evergreen): se escriben después de las obras para
    # poder enlazar los shows que ya no tienen funciones.

    salidas_venue = []
    sala_root = out / "sala"
    for slug, data in eventos_por_sala.items():
        evs = sorted(data["eventos"], key=lambda e: e.get("fecha", ""))
        pagina = render_pagina_venue(data["venue"], evs, jueves,
                                     anteriores_por_sala.get(slug, [])[:40])
        destino = sala_root / slug / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(pagina, encoding="utf-8")
        salidas_venue.append(str(destino))

    # Salas que ya tenían página pero esta semana no traen eventos: se
    # regeneran vacías. Si no, la página vieja queda con funciones pasadas
    # (y Google la sigue mostrando con un título que ya no es verdad).
    catalogo = {}
    for nombre, *_ in list(VENUES_MASIVOS.values()) + list(VENUES_DIRECCIONES.values()):
        vc = venue_canonico(nombre)
        if vc:
            catalogo.setdefault(vc["slug"], vc)
    if sala_root.is_dir():
        for d in sorted(sala_root.iterdir()):
            if d.is_dir() and d.name not in eventos_por_sala and d.name in catalogo:
                (d / "index.html").write_text(
                    render_pagina_venue(catalogo[d.name], [], jueves,
                                        anteriores_por_sala.get(d.name, [])[:40]), encoding="utf-8")

    # Página evergreen "Lo que se viene" (grandes shows anticipados)
    lqsv_dir = out / "lo-que-se-viene"
    lqsv_dir.mkdir(parents=True, exist_ok=True)
    (lqsv_dir / "index.html").write_text(
        render_pagina_lo_que_se_viene(normalizar_categorias(eventos), jueves),
        encoding="utf-8",
    )

    n_alias = escribir_redirects_alias(out.parent, alias_total)
    n_retiradas = retirar_ediciones_viejas(out.parent, jueves)
    print(f"[indice] {n_alias} alias con 301, {n_retiradas} ediciones viejas pasadas a noindex")
    escribir_archivo(out, jueves)
    generar_sitemap(out)

    return {
        **info,
        "salida_actual": str(current_index),
        "salida_archivo": str(archive_index),
        "salidas_categoria": salidas_categoria,
        "salidas_venue": salidas_venue,
        "salidas_obra": len(salidas_obra),
        "afiches": resumen_afiches,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera En Vivo para MoVeTe")
    parser.add_argument("--eventos", default="eventos.json")
    parser.add_argument("--output", default="../Movete-info/en-vivo")
    parser.add_argument("--hoy", default=None,
                        help="Fecha YYYY-MM-DD que se toma como 'hoy' (pre-edicion: el proximo jueves)")
    parser.add_argument("--solo-fechada", action="store_true",
                        help="Escribe solo /en-vivo/<jueves>/ y el sitemap")
    parser.add_argument("--sin-fechada", action="store_true",
                        help="Actualiza todo menos /en-vivo/<jueves>/ (pasadas del martes y domingo)")
    parser.add_argument("--afiches", default=None,
                        help="Carpeta de copias livianas de imagenes (default: <output>/../assets/afiches)")
    parser.add_argument("--sin-afiches", action="store_true",
                        help="No bajar ni achicar imagenes: usar las URLs originales")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    hoy = date.fromisoformat(args.hoy) if args.hoy else None
    afiches = None if args.sin_afiches else (
        args.afiches or Path(args.output).parent / "assets" / "afiches")
    if args.solo_fechada and args.sin_fechada:
        raise SystemExit("--solo-fechada y --sin-fechada no van juntos")
    info = generar(args.eventos, args.output, hoy=hoy, solo_fechada=args.solo_fechada,
                   afiches_dir=afiches, sin_fechada=args.sin_fechada)
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
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
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
        <img class="sponsor-logo" src="/assets/images/tres-empanadas-comedia.png" alt="Tres Empanadas Comedia" width="36" height="36" decoding="async">
        <p class="ad-label">Espacio promocional</p>
      </div>
      <h2>Tres Empanadas Comedia</h2>
      <p>Stand up en La Plata. Shows a la gorra, todos los jueves y viernes.</p>
      <a class="button small" href="https://tresempanadas.com.ar/reservas/?utm_source=movete&amp;utm_medium=en-vivo&amp;utm_campaign=sponsor">Reservar lugar</a>
      <a class="sponsor-sublink" href="https://tresempanadas.com.ar/cursos/?utm_source=movete&amp;utm_medium=en-vivo&amp;utm_campaign=sponsor">Taller de stand up los jueves →</a>
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
      <p class="mas-shows"><a href="/en-vivo/lo-que-se-viene/">Ver todos los grandes shows anunciados en La Plata →</a></p>
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
      <a href="/en-vivo/archivo/">Archivo</a>
      <span aria-hidden="true">·</span>
      <button class="footer-share" type="button" data-share-page title="Avisá que existimos por WhatsApp" aria-label="Avisá que existimos por WhatsApp">Avisá que existimos <img class="share-icon" src="/assets/icons/whatsapp.svg" alt=""></button>
    </p>
  </footer>
  <script src="/assets/js/movete.js" defer></script>
  <script src="/assets/js/movete-acciones.js" defer></script>
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
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="stylesheet" href="/assets/css/movete.css">
  <style>
    .nl-form {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }}
    .nl-form input[type="email"] {{ flex: 1 1 200px; min-width: 0; font: inherit; font-size: 1rem; padding: 11px 14px; border: 1px solid var(--line-strong); border-radius: 12px; background: var(--paper); color: var(--ink); }}
    .nl-form button {{ cursor: pointer; }}
    .nl-nota {{ margin: 10px 0 0; font-size: .88rem; color: var(--muted); }}
  </style>
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

    <section class="section">
      <article class="card">
        <p class="tag">No te lo pierdas</p>
        <h2>¿Qué hay esta semana en La Plata?</h2>
        <p>Dejanos tu mail y todos los jueves te llega la cartelera: teatro, música, stand up y cine. Sin spam.</p>
        <form class="nl-form" action="https://buttondown.com/api/emails/embed-subscribe/MoVeTe" method="post" target="_blank">
          <label for="nl-email" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">Tu mail</label>
          <input id="nl-email" type="email" name="email" required placeholder="tu@mail.com" autocomplete="email">
          <input type="hidden" name="embed" value="1">
          <button class="button small" type="submit">Avisame</button>
        </form>
        <p class="nl-nota">Te llega un mail para confirmar. Un envío por semana.</p>
      </article>
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
      <span aria-hidden="true">·</span>
      <a href="/en-vivo/archivo/">Archivo</a>
    </p>
  </footer>
  <script src="/assets/js/movete.js" defer></script>
  <script src="/assets/js/movete-acciones.js" defer></script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
