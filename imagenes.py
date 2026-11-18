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
# Google Discover solo muestra la tarjeta grande con imágenes de 1200 px de
# ancho o más. Si el original llega a ese ancho, se guarda además una copia
# grande (solo para og:image y el JSON-LD; en la página se sigue usando la
# liviana). Si el original es más chico no se agranda: no se inventa calidad.
ANCHO_GRANDE = 1200
ALTO_GRANDE = 2400
TIMEOUT = 20
BYTES_MAX = 20 * 1024 * 1024
USER_AGENT = "MoVeTe/1.0 (+https://movete.info)"


def nombre_local(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".webp"


def nombre_grande(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + "-g.webp"


def _bajar(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        datos = r.read(BYTES_MAX + 1)
    if len(datos) > BYTES_MAX:
        raise ValueError("imagen demasiado grande")
    return datos


def convertir(datos: bytes, ancho: int = ANCHO_MAX, alto: int = ALTO_MAX,
              minimo: int = 0) -> bytes | None:
    """WebP achicado a ancho x alto. Con minimo, devuelve None si el original
    es más angosto que eso (no se agranda)."""
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(datos)) as im:
        im = ImageOps.exif_transpose(im)
        if minimo and im.width < minimo:
            return None
        im.thumbnail((ancho, alto))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "P") else "RGB")
        salida = io.BytesIO()
        im.save(salida, "WEBP", quality=CALIDAD, method=6)
        return salida.getvalue()


def _guardar(destino: Path, datos: bytes) -> None:
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(datos)
    tmp.replace(destino)


def _asegurar(url: str, carpeta: Path) -> tuple[bool, bool]:
    """(hay copia liviana, hay copia grande)."""
    destino = carpeta / nombre_local(url)
    grande = carpeta / nombre_grande(url)
    # Marca de "el original es chico, no hay grande": así no se vuelve a bajar.
    sin_grande = carpeta / (nombre_grande(url) + ".no")
    ok_chica = destino.exists() and destino.stat().st_size > 0
    ok_grande = grande.exists() and grande.stat().st_size > 0
    if ok_chica and (ok_grande or sin_grande.exists()):
        return True, ok_grande
    try:
        datos = _bajar(url)
        if not ok_chica:
            _guardar(destino, convertir(datos))
            ok_chica = True
        if not ok_grande:
            g = convertir(datos, ANCHO_GRANDE, ALTO_GRANDE, minimo=ANCHO_GRANDE)
            if g:
                _guardar(grande, g)
                ok_grande = True
            else:
                sin_grande.write_bytes(b"")
    except Exception as exc:  # red, 404, formato raro: se queda la URL original
        print(f"[imagenes] no se pudo localizar {url}: {exc}")
    return ok_chica, ok_grande


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
        and not str(ev.get("imagen")).startswith("https://movete.info/")  # ya es propia
    })
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        ok = dict(zip(urls, pool.map(lambda u: _asegurar(u, carpeta), urls)))

    for ev in eventos:
        url = str(ev.get("imagen") or "").strip()
        chica, grande = ok.get(url, (False, False))
        if chica:
            ev["imagen_original"] = url
            ev["imagen"] = URL_BASE + nombre_local(url)
        if grande:
            ev["imagen_grande"] = URL_BASE + nombre_grande(url)

    localizadas = sum(1 for c, _ in ok.values() if c)
    return {"localizadas": localizadas, "fallidas": len(ok) - localizadas, "omitido": False}
