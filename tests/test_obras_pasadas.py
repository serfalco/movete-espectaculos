from datetime import date

import generar_edicion as g

EV = {"titulo": "Conociendo Rusia", "fecha": "2026-10-03 21:00:00",
      "lugar": "Teatro Argentino", "categoria": "musica", "imagen": "https://x/a.jpg"}
JUEVES = date(2026, 10, 29)


def test_la_pagina_activa_guarda_la_ultima_funcion():
    html_activa = g.render_pagina_obra("conociendo-rusia", [EV], date(2026, 10, 1))
    ult = g.leer_ultima(html_activa)
    assert ult["fecha"] == "2026-10-03" and ult["categoria"] == "musica"


def test_pasada_reciente_queda_indexada_con_la_ultima_fecha():
    ult = g.datos_ultima_funcion("Conociendo Rusia", [EV])
    out = g.render_pagina_obra("conociendo-rusia", [], JUEVES, "Conociendo Rusia", ultima=ult,
                               parecidos=[{"slug": "x", "titulo": "X", "cuando": "vie 30/10", "sala": "Y"}])
    assert "noindex" not in out
    assert "la última función fue el sábado 3 de octubre de 2026" in out
    assert 'href="/en-vivo/obra/x/"' in out
    assert g.leer_ultima(out)["fecha"] == "2026-10-03"  # sobrevive a la próxima corrida


def test_pasado_el_anio_vuelve_a_noindex_pero_conserva_el_dato():
    ult = g.datos_ultima_funcion("Conociendo Rusia", [EV])
    out = g.render_pagina_obra("conociendo-rusia", [], date(2027, 11, 4), "Conociendo Rusia", ultima=ult)
    assert 'content="noindex"' in out and g.leer_ultima(out)


def test_sin_datos_sigue_como_antes():
    assert 'content="noindex"' in g.render_pagina_obra("x", [], JUEVES, "X")


def test_lee_paginas_viejas_por_json_ld():
    viejo = g.render_pagina_obra("conociendo-rusia", [EV], date(2026, 10, 1))
    viejo = viejo.replace(g.meta_ultima(g.datos_ultima_funcion("Conociendo Rusia", [EV])), "")
    assert g.leer_ultima(viejo)["sala"]
