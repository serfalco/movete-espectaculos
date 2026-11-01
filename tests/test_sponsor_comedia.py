from generar_edicion import bloque_sponsor_comedia


def ev(cat, lugar="Teatro Metro", titulo="Show"):
    return {"categoria": cat, "lugar": lugar, "titulo": titulo, "fecha": "2026-11-06 21:00:00"}


def test_sale_en_stand_up_de_otra_sala():
    b = bloque_sponsor_comedia([ev("stand-up")])
    assert "Espacio promocional" in b and "tres-empanadas-comedia" in b


def test_no_sale_en_teatro():
    assert bloque_sponsor_comedia([ev("teatro")]) == ""


def test_no_sale_en_shows_del_propio_club():
    assert bloque_sponsor_comedia([ev("stand-up", lugar="Tres Empanadas Comedia")]) == ""
