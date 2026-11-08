"""MoVeTe — Publica en Instagram y Facebook las piezas que armó generar_redes.py.

Lee Movete-info/redes/<jueves>/manifest.json y publica lo que toca HOY (hora
de Argentina):
  - el jueves: el carrusel del finde en Instagram y Facebook;
  - todos los días: la historia "Hoy en La Plata" en Instagram y el mismo
    plan del día, con links, como foto en la página de Facebook.

Usa solo la API oficial de Meta (gratis). Lo que ya se publicó queda anotado en
redes/<jueves>/publicado.json: si el workflow corre dos veces el mismo día, no
se repite nada.

Variables de entorno (secrets del repo Movete-info):
  META_TOKEN    token de la página de Facebook (con permiso de publicar en IG)
  META_PAGE_ID  id de la página de Facebook
  META_IG_ID    id de la cuenta profesional de Instagram vinculada
  GRAPH_VERSION opcional, por defecto v23.0

Sin esas variables no hace nada y termina bien: las redes están "apagadas".

Uso:
    python publicar_redes.py --redes ../Movete-info/redes
    python publicar_redes.py --redes ../Movete-info/redes --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")
JUEVES = 3


def jueves_de_edicion(d: date) -> date:
    return d - timedelta(days=(d.weekday() - JUEVES) % 7)


class ErrorMeta(Exception):
    pass


class Meta:
    def __init__(self, token: str, page_id: str, ig_id: str, version: str):
        self.token, self.page_id, self.ig_id = token, page_id, ig_id
        self.base = f"https://graph.facebook.com/{version}"

    def _llamar(self, metodo: str, ruta: str, datos: dict | None = None) -> dict:
        datos = dict(datos or {}, access_token=self.token)
        cuerpo = urllib.parse.urlencode(datos).encode()
        url = f"{self.base}/{ruta}"
        if metodo == "GET":
            url, cuerpo = f"{url}?{cuerpo.decode()}", None
        req = urllib.request.Request(url, data=cuerpo, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:500]
            raise ErrorMeta(f"{metodo} {ruta}: HTTP {e.code} {detalle}") from None

    # Instagram: se crea un "contenedor", se espera a que Meta procese la
    # imagen y recién ahí se publica.
    def _ig_contenedor(self, **datos) -> str:
        return self._llamar("POST", f"{self.ig_id}/media", datos)["id"]

    def _ig_esperar(self, cid: str, intentos: int = 30) -> None:
        for _ in range(intentos):
            estado = self._llamar("GET", cid, {"fields": "status_code"}).get("status_code")
            if estado == "FINISHED":
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErrorMeta(f"Instagram no pudo procesar {cid}: {estado}")
            time.sleep(5)
        raise ErrorMeta(f"Instagram tardó demasiado en procesar {cid}")

    def _ig_publicar(self, cid: str) -> str:
        self._ig_esperar(cid)
        return self._llamar("POST", f"{self.ig_id}/media_publish", {"creation_id": cid})["id"]

    def ig_carrusel(self, imagenes: list[str], texto: str) -> str:
        hijos = [self._ig_contenedor(image_url=u, is_carousel_item="true") for u in imagenes[:10]]
        for h in hijos:
            self._ig_esperar(h)
        cid = self._ig_contenedor(media_type="CAROUSEL", children=",".join(hijos), caption=texto)
        return self._ig_publicar(cid)

    def ig_historia(self, imagen: str) -> str:
        return self._ig_publicar(self._ig_contenedor(media_type="STORIES", image_url=imagen))

    # Facebook: varias fotos sin publicar y un post que las junta.
    def fb_album(self, imagenes: list[str], texto: str) -> str:
        fotos = [self._llamar("POST", f"{self.page_id}/photos",
                              {"url": u, "published": "false"})["id"] for u in imagenes]
        datos = {"message": texto}
        for i, fid in enumerate(fotos):
            datos[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
        return self._llamar("POST", f"{self.page_id}/feed", datos)["id"]

    def fb_foto(self, imagen: str, texto: str) -> str:
        r = self._llamar("POST", f"{self.page_id}/photos", {"url": imagen, "caption": texto})
        return r.get("post_id") or r["id"]


def esperar_publicadas(urls: list[str], minutos: int = 15) -> None:
    """Meta baja las imágenes desde movete.info: tienen que estar en línea.

    Recién commiteadas, Cloudflare tarda un par de minutos en desplegarlas.
    """
    limite = time.time() + minutos * 60
    pendientes = list(urls)
    while pendientes:
        url = pendientes[0]
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": "MoVeTe/1.0 (+https://movete.info)"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200 and "image" in r.headers.get("Content-Type", ""):
                    pendientes.pop(0)
                    continue
        except (urllib.error.URLError, TimeoutError):
            pass
        if time.time() > limite:
            raise ErrorMeta(f"La imagen no está en línea todavía: {url}")
        time.sleep(20)


def tareas_de_hoy(manifest: dict, hoy: date) -> list[tuple[str, dict]]:
    tareas = []
    carrusel = manifest.get("carrusel")
    if carrusel and carrusel.get("publicar") == hoy.isoformat():
        tareas += [("ig_carrusel", carrusel), ("fb_carrusel", carrusel)]
    historia = manifest.get("historias", {}).get(hoy.isoformat())
    if historia:
        tareas += [("ig_historia", historia), ("fb_dia", historia)]
    return tareas


def _alertar(msg: str) -> None:
    print(f"[redes] {msg}", file=sys.stderr)
    ruta = os.environ.get("MOVETE_ALERTA", "").strip()
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"Redes: {msg}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publica las piezas de MoVeTe en IG y Facebook")
    ap.add_argument("--redes", default="../Movete-info/redes")
    ap.add_argument("--hoy", default=None, help="AAAA-MM-DD (por defecto, hoy en Argentina)")
    ap.add_argument("--dry-run", action="store_true", help="Muestra qué publicaría, sin publicar")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    hoy = date.fromisoformat(args.hoy) if args.hoy else datetime.now(ZONA).date()
    carpeta = Path(args.redes) / jueves_de_edicion(hoy).isoformat()
    ruta_manifest = carpeta / "manifest.json"
    if not ruta_manifest.exists():
        print(f"[redes] No hay piezas para la edición de esta semana ({ruta_manifest}). Nada que publicar.")
        return 0
    manifest = json.loads(ruta_manifest.read_text("utf-8"))
    ruta_estado = carpeta / "publicado.json"
    estado = json.loads(ruta_estado.read_text("utf-8")) if ruta_estado.exists() else {}
    hechas = estado.setdefault(hoy.isoformat(), {})

    tareas = [(n, d) for n, d in tareas_de_hoy(manifest, hoy) if n not in hechas]
    if not tareas:
        print("[redes] Nada pendiente para hoy.")
        return 0
    if args.dry_run:
        for nombre, datos in tareas:
            print(f"--- {nombre} ---")
            print(json.dumps(datos, ensure_ascii=False, indent=1)[:1500])
        return 0

    token = os.environ.get("META_TOKEN", "").strip()
    page_id = os.environ.get("META_PAGE_ID", "").strip()
    ig_id = os.environ.get("META_IG_ID", "").strip()
    if not (token and page_id and ig_id):
        print("[redes] Faltan META_TOKEN / META_PAGE_ID / META_IG_ID: redes apagadas, no se publica.")
        return 0
    meta = Meta(token, page_id, ig_id, os.environ.get("GRAPH_VERSION", "v23.0").strip() or "v23.0")

    errores = 0
    for nombre, datos in tareas:
        try:
            imagenes = datos.get("imagenes") or [datos["imagen"]]
            esperar_publicadas(imagenes)
            if nombre == "ig_carrusel":
                pid = meta.ig_carrusel(imagenes, datos["instagram"])
            elif nombre == "fb_carrusel":
                pid = meta.fb_album(imagenes, datos["facebook"])
            elif nombre == "ig_historia":
                pid = meta.ig_historia(datos["imagen"])
            else:
                pid = meta.fb_foto(datos["imagen"], datos["facebook"])
            hechas[nombre] = pid
            print(f"[redes] {nombre}: publicado ({pid})")
        except ErrorMeta as e:
            errores += 1
            _alertar(f"{nombre} falló: {e}")
        # Se guarda después de cada una: si algo se cae a mitad, lo publicado no se repite.
        ruta_estado.write_text(json.dumps(estado, ensure_ascii=False, indent=1), "utf-8")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
