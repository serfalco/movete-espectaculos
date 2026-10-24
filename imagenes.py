"""Copias livianas de las imágenes de los eventos, servidas desde movete.info.

Las fuentes (sobre todo Genda) publican fotos originales de hasta 3000 px y
2-3 MB, y además desde un servidor lento. Al armar la edición se baja cada
imagen una sola vez, se achica a 640 px de ancho en WebP (~30-60 KB) y se
guarda en /assets/afiches/ del sitio con un nombre derivado de la URL de
origen. Una imagen que ya está en disco no se vuelve a bajar.

Si algo falla (red, formato, Pillow ausente) el evento conserva la URL
original: nunca se pierde una imagen por culpa de este paso.
"""
from __future__ import annotations

import hashlib
import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

URL_BASE = "https://movete.info/assets/afiches/"
ANCHO_MAX = 640
ALTO_MAX = 900          # el afiche de obra se muestra a 420 px de alto (x2 en pantallas densas)
CALIDAD = 72
TIMEOUT = 20
BYTES_MAX = 20 * 1024 * 1024
USER_AGENT = "MoVeTe/1.0 (+https://movete.info)"


def nombre_local(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".webp"


def _bajar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        datos = r.read(BYTES_MAX + 1)
    if len(datos) > BYTES_MAX:
        raise ValueError("imagen demasiado grande")
    return datos


def convertir(datos: bytes) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(datos)) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((ANCHO_MAX, ALTO_MAX))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "P") else "RGB")
        salida = io.BytesIO()
        im.save(salida, "WEBP", quality=CALIDAD, method=6)
        return salida.getvalue()


def _asegurar(url: str, carpeta: Path) -> bool:
    destino = carpeta / nombre_local(url)
    if destino.exists() and destino.stat().st_size > 0:
        return True
    try:
        webp = convertir(_bajar(url))
    except Exception as exc:  # red, 404, formato raro: se queda la URL original
        print(f"[imagenes] no se pudo localizar {url}: {exc}")
        return False
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(webp)
    tmp.replace(destino)
    return True


def localizar_imagenes(eventos: list[dict], carpeta: str | Path, hilos: int = 8) -> dict:
    """Reemplaza ev["imagen"] por la copia liviana local. Devuelve un resumen."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[imagenes] Pillow no está instalado: se usan las URLs originales")
        return {"localizadas": 0, "fallidas": 0, "omitido": True}

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    urls = sorted({
        str(ev.get("imagen") or "").strip()
        for ev in eventos
        if str(ev.get("imagen") or "").strip().startswith(("http://", "https://"))
        and not str(ev.get("imagen")).startswith(URL_BASE)
    })
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        ok = dict(zip(urls, pool.map(lambda u: _asegurar(u, carpeta), urls)))

    for ev in eventos:
        url = str(ev.get("imagen") or "").strip()
        if ok.get(url):
            ev["imagen_original"] = url
            ev["imagen"] = URL_BASE + nombre_local(url)

    localizadas = sum(ok.values())
    return {"localizadas": localizadas, "fallidas": len(ok) - localizadas, "omitido": False}
