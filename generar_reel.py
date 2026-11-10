"""MoVeTe — Reel semanal "Planes para el finde en La Plata".

Video vertical 1080x1920 de unos 18 segundos: tapa, hasta 5 funciones del
finde (afiche con zoom suave + día, hora, título y sala) y cierre con
movete.info. De fondo, el tema propio de MoVeTe (assets_redes/movete-tema.mp3,
hecho en Suno con plan Pro, uso comercial permitido).

Lo llama generar_redes.py; se puede correr suelto para mirar una muestra:
    python generar_reel.py --eventos eventos.json --salida reel.mp4
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import generar_redes as gr
from generar_edicion import cat_label

AQUI = Path(__file__).resolve().parent
TEMA = AQUI / "assets_redes" / "movete-tema.mp3"

W, H = 1080, 1920
FPS = 30
T_TAPA, T_EVENTO, T_CIERRE, T_FUNDIDO = 2.4, 2.8, 2.8, 0.35
TOPE_REEL = 5

# Instagram tapa con su interfaz ~250 px arriba, ~420 abajo y ~160 a la derecha.
MARGEN_X, ANCHO_UTIL = 72, 1080 - 72 - 170


def _placa_tapa(jueves: date, afiches: gr.Afiches, evs: list[dict]):
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
    fondo = None
    for e in evs:
        a = afiches.abrir(e)
        if a:
            fondo = ImageOps.fit(a, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
            fondo = ImageEnhance.Brightness(fondo).enhance(0.35)
            break
    img = fondo or Image.new("RGB", (W, H), gr.TINTA)
    d = ImageDraw.Draw(img)
    gr._logo(d, MARGEN_X, 300, 56, gr.PAPEL)
    f = gr._fuente("Bold", 140)
    y = 560
    for linea, color in (("Planes", gr.PAPEL), ("para el finde", gr.PAPEL), ("en La Plata", gr.VERDE)):
        fl, lineas = gr._titulo_que_entre(d, linea, "Bold", W - 2 * MARGEN_X, 1, 140, 90)
        d.text((MARGEN_X, y), lineas[0], font=fl, fill=color)
        y += gr._alto_linea(fl) - 8
    d.text((MARGEN_X, y + 30), gr._rango_finde(jueves).capitalize(),
           font=gr._fuente("Medium", 56), fill=gr.PAPEL)
    return img


def _placa_evento(ev: dict, afiches: gr.Afiches):
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
    a = afiches.abrir(ev)
    if a:
        img = ImageOps.fit(a, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(36))
        img = ImageEnhance.Brightness(img).enhance(0.45)
        alto = 1100
        esc = min((W - 2 * 60) / a.width, alto / a.height)
        fr = a.resize((int(a.width * esc), int(a.height * esc)), Image.LANCZOS)
        img.paste(fr, ((W - fr.width) // 2, 230 + (alto - fr.height) // 2))
    else:
        img = gr._sin_afiche(W, H, ev)
    d = ImageDraw.Draw(img)
    # Panel de texto, dentro de la zona que Instagram no tapa.
    y0 = 1360
    d.rounded_rectangle((40, y0 - 30, W - 150, y0 + 360), radius=36, fill=gr.PAPEL)
    fin = gr._chip(d, MARGEN_X, y0, cat_label(ev.get("categoria") or "otros").upper(), gr.ACENTO, gr.PAPEL, 30)
    d.text((fin + 22, y0 + 6), gr._cuando(ev).upper(), font=gr._fuente("Bold", 40), fill=gr.TINTA)
    f_tit, lineas = gr._titulo_que_entre(d, gr._titulo(ev), "Bold", ANCHO_UTIL - 40, 2, 66, 42)
    y = gr._escribir(d, (MARGEN_X, y0 + 80), lineas, f_tit, gr.TINTA)
    f_sala = gr._fuente("Regular", 40)
    sala, _ = gr._envolver(d, gr._sala(ev), f_sala, ANCHO_UTIL - 40, 1)
    gr._escribir(d, (MARGEN_X, y + 6), sala, f_sala, gr.GRIS)
    return img


def _placa_cierre():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), gr.ACENTO)
    d = ImageDraw.Draw(img)
    for i in range(-H, W, 110):
        d.line((i, H, i + H, 0), fill=(190, 66, 54), width=34)
    gr._logo(d, MARGEN_X, 300, 56, gr.PAPEL, punto=gr.TINTA)
    y = 620
    f1 = gr._fuente("Bold", 96)
    for linea in ("Toda la cartelera", "de La Plata en"):
        d.text((MARGEN_X, y), linea, font=f1, fill=gr.PAPEL)
        y += gr._alto_linea(f1) - 6
    d.text((MARGEN_X, y + 10), "movete.info", font=gr._fuente("Bold", 130), fill=gr.TINTA)
    f2 = gr._fuente("Medium", 48)
    d.text((MARGEN_X, y + 230), "Seguinos para los planes de cada finde", font=f2, fill=gr.PAPEL)
    return img


def elegir_reel(evs: list[dict], jueves: date, afiches: gr.Afiches) -> list[dict]:
    """Las del carrusel, pero solo con afiche: un Reel sin imágenes no se mira."""
    cands = [e for e in gr.elegir_finde(evs, jueves, afiches) if afiches(e)]
    # De a uno por día (vie, sáb, dom) hasta llenar: que el Reel muestre todo el finde.
    por_dia: dict[str, list[dict]] = {}
    for e in cands:
        por_dia.setdefault(str(e["fecha"])[:10], []).append(e)
    elegidos: list[dict] = []
    while len(elegidos) < TOPE_REEL and any(por_dia.values()):
        for dia in sorted(por_dia):
            if por_dia[dia] and len(elegidos) < TOPE_REEL:
                elegidos.append(por_dia[dia].pop(0))
    return sorted(elegidos, key=lambda e: e["fecha"])


def armar_reel(evs: list[dict], jueves: date, afiches: gr.Afiches, salida: Path,
               tema: Path = TEMA) -> bool:
    if not shutil.which("ffmpeg"):
        print("[reel] falta ffmpeg: no se arma el Reel")
        return False
    if len(evs) < 3:
        print("[reel] menos de 3 funciones con afiche: no se arma el Reel")
        return False
    placas = [(_placa_tapa(jueves, afiches, evs), T_TAPA)]
    placas += [(_placa_evento(e, afiches), T_EVENTO) for e in evs]
    placas.append((_placa_cierre(), T_CIERRE))

    with tempfile.TemporaryDirectory() as tmp:
        entradas, filtros = [], []
        for i, (img, dur) in enumerate(placas):
            p = Path(tmp) / f"p{i}.png"
            img.save(p)
            entradas += ["-loop", "1", "-t", f"{dur + T_FUNDIDO:.2f}", "-i", str(p)]
            n = int((dur + T_FUNDIDO) * FPS)
            # Zoom suave hacia el centro: le da movimiento sin marear.
            filtros.append(
                f"[{i}:v]scale={W * 2}:{H * 2},zoompan=z='min(1+0.0011*on,1.05)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},"
                f"format=yuv420p,setsar=1[v{i}]"
            )
        # Fundidos encadenados entre placas.
        actual, t = "v0", placas[0][1]
        for i in range(1, len(placas)):
            sale = f"x{i}"
            filtros.append(f"[{actual}][v{i}]xfade=transition=fade:duration={T_FUNDIDO}:offset={t:.2f}[{sale}]")
            actual, t = sale, t + placas[i][1]
        total = t + T_FUNDIDO
        audio_idx = len(placas)
        filtros.append(f"[{audio_idx}:a]atrim=0:{total:.2f},afade=t=in:d=0.2,"
                       f"afade=t=out:st={total - 1.2:.2f}:d=1.2,volume=0.9[a]")
        cmd = ["ffmpeg", "-y", "-v", "error", *entradas, "-i", str(tema),
               "-filter_complex", ";".join(filtros), "-map", f"[{actual}]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
               "-t", f"{total:.2f}", str(salida)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[reel] ffmpeg falló: {r.stderr[-800:]}")
            return False
    return True


def texto_reel(evs: list[dict], jueves: date, red: str) -> str:
    lineas = [f"Planes para el finde en La Plata 🎪 del {gr._rango_finde(jueves)}", ""]
    lineas += [gr._linea(e, {}) for e in evs]
    lineas.append("")
    if red == "facebook":
        lineas.append("Toda la cartelera: " + gr._utm(f"{gr.BASE}/en-vivo/fin-de-semana/", red,
                                                     f"reel-{jueves.isoformat()}"))
    else:
        lineas.append("Toda la cartelera en movete.info (link en la bio) 👈")
    lineas += ["Guardalo para el finde 💌", "", gr.HASHTAGS]
    return "\n".join(lineas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reel semanal de MoVeTe")
    ap.add_argument("--eventos", default="eventos.json")
    ap.add_argument("--afiches", default="../Movete-info/assets/afiches")
    ap.add_argument("--salida", default="reel.mp4")
    ap.add_argument("--hoy", default=None)
    args = ap.parse_args()
    eventos, _ = gr.cargar_eventos(args.eventos)
    evs = gr._con_fecha(eventos)
    jueves = gr.jueves_de_edicion(date.fromisoformat(args.hoy) if args.hoy else date.today())
    afiches = gr.Afiches(Path(args.afiches))
    elegidos = elegir_reel(evs, jueves, afiches)
    ok = armar_reel(elegidos, jueves, afiches, Path(args.salida))
    print(texto_reel(elegidos, jueves, "instagram") if ok else "sin reel")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
