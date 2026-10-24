import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import imagenes  # noqa: E402


def _jpg(w, h):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 50, 50)).save(buf, "JPEG")
    return buf.getvalue()


def test_convertir_achica_y_pasa_a_webp():
    webp = imagenes.convertir(_jpg(3000, 4000))
    with Image.open(io.BytesIO(webp)) as im:
        assert im.format == "WEBP"
        assert im.width <= imagenes.ANCHO_MAX and im.height <= imagenes.ALTO_MAX


def test_localizar_reemplaza_y_conserva_original(tmp_path, monkeypatch):
    bajadas = []

    def falso_bajar(url):
        bajadas.append(url)
        if "rota" in url:
            raise OSError("404")
        return _jpg(1200, 800)

    monkeypatch.setattr(imagenes, "_bajar", falso_bajar)
    eventos = [
        {"imagen": "https://ej.com/a.jpg"},
        {"imagen": "https://ej.com/a.jpg"},   # misma imagen: se baja una vez
        {"imagen": "https://ej.com/rota.jpg"},
        {"imagen": ""},
    ]
    r = imagenes.localizar_imagenes(eventos, tmp_path)

    assert r == {"localizadas": 1, "fallidas": 1, "omitido": False}
    assert bajadas.count("https://ej.com/a.jpg") == 1
    assert eventos[0]["imagen"].startswith(imagenes.URL_BASE)
    assert eventos[0]["imagen_original"] == "https://ej.com/a.jpg"
    assert eventos[2]["imagen"] == "https://ej.com/rota.jpg"   # si falla, queda la original
    assert (tmp_path / imagenes.nombre_local("https://ej.com/a.jpg")).exists()

    # Segunda corrida: ya está en disco, no se vuelve a bajar.
    bajadas.clear()
    imagenes.localizar_imagenes([{"imagen": "https://ej.com/a.jpg"}], tmp_path)
    assert bajadas == []
