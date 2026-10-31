from generar_edicion import titulo_y_descripcion_obra


def test_una_funcion_lleva_dia_y_sala_en_el_titulo():
    t, d = titulo_y_descripcion_obra(
        "Un Poco de Ruido",
        [{"fecha": "2026-11-28 21:00:00", "lugar": "Hipódromo de La Plata", "url": "https://x"}])
    assert t == "Un Poco de Ruido en La Plata (sáb 28/11, Hipódromo) · MoVeTe"
    assert "a las 21 h" in d and "Link a las entradas" in d


def test_titulo_nunca_pasa_62_caracteres():
    t, _ = titulo_y_descripcion_obra(
        "Una obra con un título larguísimo que no entra nunca en Google",
        [{"fecha": "2026-10-30 00:00:00", "lugar": "Guajira"}])
    assert len(t) <= 62


def test_varias_funciones_con_direccion_en_descripcion():
    t, d = titulo_y_descripcion_obra(
        "Obra", [{"fecha": "2026-10-30 20:30:00", "lugar": "Teatro René Favaloro"},
                 {"fecha": "2026-11-06 20:30:00", "lugar": "Teatro René Favaloro"}])
    assert "vie 30/10" in t
    assert "Calle 67" in d and " h " not in d
