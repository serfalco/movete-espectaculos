"""Higiene del índice: alias con 301, ediciones viejas fuera de Google,
lastmod real en el sitemap y alt en los afiches."""
import json
from datetime import date
from pathlib import Path

import generar_edicion as g


def _pagina(root: Path, ruta: str, cuerpo: str, head: str = "") -> Path:
    idx = root / ruta.strip("/") / "index.html"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(f'<!doctype html><html><head>\n  <meta charset="utf-8">{head}\n</head>'
                   f'<body><main>{cuerpo}</main></body></html>', encoding="utf-8")
    return idx


ALIAS = '\n  <meta name="robots" content="noindex, follow">\n  <meta http-equiv="refresh" content="0; url=/x/">'


def test_alias_se_escriben_como_301_y_se_conservan(tmp_path):
    (tmp_path / "_redirects").write_text("# a mano\n/evento/*    /en-vivo/   301\n", encoding="utf-8")
    _pagina(tmp_path, "en-vivo/obra/anemonas", "show")
    _pagina(tmp_path, "en-vivo/obra/anemonas-un-plan", "alias", ALIAS)
    _pagina(tmp_path, "en-vivo/obra/otra", "show")
    _pagina(tmp_path, "en-vivo/obra/otra-2026", "alias", ALIAS)
    assert g.escribir_redirects_alias(tmp_path, {"anemonas-un-plan": "anemonas"}) == 1
    # segunda corrida: llega otro alias; el anterior no se pierde ni se duplica
    assert g.escribir_redirects_alias(tmp_path, {"otra-2026": "otra"}) == 2
    texto = (tmp_path / "_redirects").read_text(encoding="utf-8")
    assert "/evento/*    /en-vivo/   301" in texto
    assert texto.count("/en-vivo/obra/anemonas-un-plan/ /en-vivo/obra/anemonas/ 301") == 1
    assert texto.count(g._MARCA_ALIAS_INI) == 1
    assert "https://" not in texto  # Workers solo acepta rutas relativas


def test_alias_que_vuelve_a_ser_show_pierde_la_regla(tmp_path):
    (tmp_path / "_redirects").write_text("", encoding="utf-8")
    _pagina(tmp_path, "en-vivo/obra/a", "show")
    variante = _pagina(tmp_path, "en-vivo/obra/a-gira", "alias", ALIAS)
    assert g.escribir_redirects_alias(tmp_path, {"a-gira": "a"}) == 1
    variante.write_text(variante.read_text(encoding="utf-8").replace(ALIAS, ""), encoding="utf-8")
    assert g.escribir_redirects_alias(tmp_path, {}) == 0
    assert "a-gira" not in (tmp_path / "_redirects").read_text(encoding="utf-8")


def test_sin_cadenas_de_redirecciones(tmp_path):
    (tmp_path / "_redirects").write_text("", encoding="utf-8")
    _pagina(tmp_path, "en-vivo/obra/c", "show")
    _pagina(tmp_path, "en-vivo/obra/b", "alias", ALIAS)
    _pagina(tmp_path, "en-vivo/obra/a", "alias", ALIAS)
    g.escribir_redirects_alias(tmp_path, {"a": "b", "b": "c"})
    texto = (tmp_path / "_redirects").read_text(encoding="utf-8")
    assert "/en-vivo/obra/a/ /en-vivo/obra/c/ 301" in texto
    assert "/en-vivo/obra/b/ /en-vivo/obra/c/ 301" in texto


def test_ediciones_viejas_pasan_a_noindex_con_canonical_propio(tmp_path):
    vieja = _pagina(tmp_path, "en-vivo/2026-07-02", "x",
                    '\n  <link rel="canonical" href="https://movete.info/en-vivo/">')
    sin_canon = _pagina(tmp_path, "cine/2026-06-18", "x")
    nueva = _pagina(tmp_path, "en-vivo/2026-11-05", "x",
                    '\n  <link rel="canonical" href="https://movete.info/en-vivo/2026-11-05/">')
    assert g.retirar_ediciones_viejas(tmp_path, date(2026, 11, 12)) == 2
    t = vieja.read_text(encoding="utf-8")
    assert 'content="noindex, follow"' in t[:900]
    assert 'href="https://movete.info/en-vivo/2026-07-02/"' in t and t.count("canonical") == 1
    t2 = sin_canon.read_text(encoding="utf-8")
    assert "noindex, follow" in t2 and 'href="https://movete.info/cine/2026-06-18/"' in t2
    assert "noindex" not in nueva.read_text(encoding="utf-8")
    assert g.retirar_ediciones_viejas(tmp_path, date(2026, 11, 12)) == 0  # no se repite


def test_sitemap_lastmod_solo_cambia_si_cambia_el_contenido(tmp_path):
    out = tmp_path / "en-vivo"
    _pagina(tmp_path, "en-vivo", "portada")
    obra = _pagina(tmp_path, "en-vivo/obra/show", "Show · sábado")
    _pagina(tmp_path, "en-vivo/2026-11-05", "edicion")
    _pagina(tmp_path, "en-vivo/2026-07-02", "vieja", '\n  <meta name="robots" content="noindex, follow">')
    g.generar_sitemap(out, hoy=date(2026, 11, 10))
    sm = (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://movete.info/en-vivo/obra/show/</loc><lastmod>2026-11-10</lastmod>" in sm
    assert "<loc>https://movete.info/en-vivo/2026-11-05/</loc><lastmod>2026-11-05</lastmod>" in sm
    assert "2026-07-02" not in sm  # edición retirada, fuera del sitemap
    # otra pasada sin cambios: la fecha no se mueve
    g.generar_sitemap(out, hoy=date(2026, 11, 12))
    assert "show/</loc><lastmod>2026-11-10" in (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    # cambia el show: la fecha se mueve
    obra.write_text(obra.read_text(encoding="utf-8").replace("sábado", "domingo"), encoding="utf-8")
    g.generar_sitemap(out, hoy=date(2026, 11, 15))
    assert "show/</loc><lastmod>2026-11-15" in (tmp_path / "sitemap.xml").read_text(encoding="utf-8")
    assert json.loads((tmp_path / g.LASTMOD_JSON).read_text(encoding="utf-8"))


def test_afiche_de_la_tarjeta_lleva_alt():
    ev = {"titulo": "Los Tipitos", "fecha": "2026-11-14T21:00:00", "lugar": "Teatro Ópera",
          "categoria": "musica", "imagen": "https://movete.info/assets/afiches/abc.webp"}
    assert 'alt="Afiche de Los Tipitos"' in g.render_evento(ev)
