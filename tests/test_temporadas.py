from datetime import date

import generar_edicion as ge


def test_carnaval_2027_cae_en_febrero():
    assert ge.rango_temporada("carnaval", date(2026, 11, 18)) == (date(2027, 2, 6), date(2027, 2, 9))


def test_temporada_en_curso_y_proxima():
    assert ge.rango_temporada("verano", date(2027, 1, 10)) == (date(2026, 12, 20), date(2027, 2, 28))
    assert ge.rango_temporada("aniversario-de-la-plata", date(2026, 11, 30))[0] == date(2027, 11, 14)


def test_pagina_temporada_con_y_sin_funciones():
    evs = [{"titulo": f"Obra {i}", "fecha": f"2026-12-2{i} 21:00:00", "lugar": "Teatro Abierto",
            "categoria": "teatro"} for i in range(1, 5)]
    html = ge.render_pagina_temporada("verano", evs, date(2026, 12, 18))
    assert "Qué hacer en el verano en La Plata" in html and "noindex" not in html
    assert "Obra 1" in html
    vacia = ge.render_pagina_temporada("verano", [], date(2026, 12, 18))
    assert "noindex" in vacia and "Todavía no hay funciones" in vacia
