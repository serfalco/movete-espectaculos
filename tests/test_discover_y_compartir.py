import io
import json
import re
from datetime import date

import generar_edicion as ge
import imagenes


def _ev(t, fecha, cat, img="https://x/a.jpg", **kw):
    return {"titulo": t, "fecha": fecha, "lugar": "Teatro Abierto", "categoria": cat, "imagen": img, **kw}


def test_ficha_tiene_boton_whatsapp():
    html = ge.render_pagina_obra("show-x", [_ev("Show X", "2026-11-21 21:00:00", "teatro")], date(2026, 11, 19))
    assert 'data-share="whatsapp"' in html and "https://wa.me/?text=" in html
    assert "s%C3%A1bado+21%2F11" in html  # el día va en el mensaje


def test_imagen_grande_en_schema_y_og():
    ev = _ev("Show X", "2026-11-21 21:00:00", "teatro", imagen_grande="https://movete.info/assets/afiches/abc-g.webp")
    html = ge.render_pagina_obra("show-x", [ev], date(2026, 11, 19))
    assert 'og:image" content="https://movete.info/assets/afiches/abc-g.webp"' in html
    data = json.loads(re.search(r">(.*)</script>", ge.render_schema_eventos([ev]), re.S).group(1))
    assert data["itemListElement"][0]["item"]["image"].endswith("-g.webp")


def test_planes_alternan_rubros_y_no_repiten_show():
    evs = [_ev(f"Obra {i}", f"2026-11-2{i % 3} 21:00:00", "teatro") for i in range(8)]
    evs += [_ev("Banda", "2026-11-21 22:00:00", "musica"), _ev("Banda", "2026-11-22 22:00:00", "musica"),
            _ev("Sin foto", "2026-11-21 20:00:00", "danza", img="")]
    planes = ge.elegir_planes(evs)
    titulos = [p["titulo"] for p in planes]
    assert len(planes) == 9 and titulos.count("Banda") == 1 and "Sin foto" not in titulos


def test_no_agranda_imagenes_chicas():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (800, 1000)).save(buf, "JPEG")
    assert imagenes.convertir(buf.getvalue(), 1200, 2400, minimo=1200) is None
    buf = io.BytesIO()
    Image.new("RGB", (1600, 2000)).save(buf, "JPEG")
    with Image.open(io.BytesIO(imagenes.convertir(buf.getvalue(), 1200, 2400, minimo=1200))) as im:
        assert im.width == 1200
