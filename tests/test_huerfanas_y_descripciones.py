from datetime import date
from pathlib import Path

import generar_edicion as ge


def test_recortar_desc_corta_en_palabra():
    texto = "palabra " * 40
    r = ge.recortar_desc(texto)
    assert len(r) <= ge.DESC_MAX
    assert r.endswith("…")
    assert ge.recortar_desc("corta") == "corta"


def test_descripcion_obra_titulo_largo_entra():
    ev = {"titulo": "Taller de Cultivo de Hongos Comestibles: Técnicas de cultivo a partir de residuos domiciliarios",
          "fecha": "2026-11-12 21:00:00", "lugar": "Teatro Abierto", "url": "https://x"}
    _, desc = ge.titulo_y_descripcion_obra(ev["titulo"], [ev])
    assert len(desc) <= ge.DESC_MAX


def test_descripcion_sala_muchos_shows_entra():
    evs = [{"titulo": f"Un show con un nombre bastante largo número {i}",
            "fecha": f"2026-11-1{i} 21:00:00"} for i in range(5)]
    _, desc = ge.titulo_y_descripcion_venue("Meridiano V", "Av. 71 y 17, La Plata", evs)
    assert len(desc) <= ge.DESC_MAX
    assert desc.startswith("Cartelera de Meridiano V:")


def test_sala_enlaza_otros_shows():
    venue = {"nombre": "Sala X", "slug": "sala-x", "direccion": ""}
    html = ge.render_pagina_venue(venue, [], date(2026, 11, 5),
                                  [{"slug": "show-viejo", "titulo": "Show viejo", "fecha": "2026-10-01"}])
    assert 'href="/en-vivo/obra/show-viejo/"' in html
    assert "Otros shows en esta sala" in html


def test_archivo_enlaza_salas_shows_y_ediciones(tmp_path: Path):
    en_vivo = tmp_path / "en-vivo"
    for rel, h1, extra in (("sala/sala-x", "Sala X", ""),
                           ("obra/show-a", "Show A", ""),
                           ("obra/show-b", "Show B", '<meta name="robots" content="noindex">')):
        d = en_vivo / rel
        d.mkdir(parents=True)
        (d / "index.html").write_text(f"<head>{extra}</head><h1>{h1}</h1>", encoding="utf-8")
    (en_vivo / "2026-11-05").mkdir()
    (en_vivo / "2026-11-05" / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "cine" / "2026-10-29").mkdir(parents=True)
    (tmp_path / "cine" / "2026-10-29" / "index.html").write_text("x", encoding="utf-8")

    ge.escribir_archivo(en_vivo, date(2026, 11, 5))
    html = (en_vivo / "archivo" / "index.html").read_text(encoding="utf-8")
    for href in ("/en-vivo/sala/sala-x/", "/en-vivo/obra/show-a/",
                 "/en-vivo/2026-11-05/", "/cine/2026-10-29/"):
        assert f'href="{href}"' in html
    assert "/en-vivo/obra/show-b/" not in html  # noindex: no se enlaza


def test_schema_evento_completo():
    import json, re
    ev = {"titulo": "Show X", "fecha": "2026-11-12 21:30:00", "lugar": "Teatro Abierto",
          "categoria": "teatro", "url": "https://entradas.example/x", "imagen": "https://img/x.jpg"}
    data = json.loads(re.search(r">(.*)</script>", ge.render_schema_eventos([ev]), re.S).group(1))
    e = data["itemListElement"][0]["item"]
    assert e["startDate"] == "2026-11-12T21:30:00-03:00"
    assert e["offers"]["url"] == "https://entradas.example/x"
    assert e["url"].startswith("https://movete.info/en-vivo/obra/")
    assert e["organizer"]["name"] and e["description"] and e["image"]
    sin_hora = dict(ev, fecha="2026-11-12 00:00:00")
    data = json.loads(re.search(r">(.*)</script>", ge.render_schema_eventos([sin_hora]), re.S).group(1))
    assert data["itemListElement"][0]["item"]["startDate"] == "2026-11-12"
