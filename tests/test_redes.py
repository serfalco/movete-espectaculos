"""Pruebas de las piezas y la publicación en redes. Offline: Meta está simulada."""
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import generar_redes as gr
import publicar_redes as pr


def ev(titulo, fecha, lugar, cat="teatro", imagen=""):
    return {"titulo": titulo, "fecha": fecha, "lugar": lugar, "categoria": cat,
            "fuente": "genda", "imagen": imagen, "url": ""}


SIN_AFICHE = lambda e: False  # noqa: E731
JUEVES = date(2026, 11, 5)


class SeleccionTests(unittest.TestCase):
    def test_el_carrusel_reparte_viernes_sabado_y_domingo(self):
        evs = [ev(f"Vie {i}", "2026-11-06 21:00:00", f"Sala V{i}") for i in range(6)]
        evs += [ev(f"Sab {i}", "2026-11-07 21:00:00", f"Sala S{i}") for i in range(6)]
        evs += [ev("Dom 1", "2026-11-08 19:00:00", "Sala D1", "musica")]
        elegidos = gr.elegir_finde(evs, JUEVES, SIN_AFICHE)
        dias = {e["fecha"][:10] for e in elegidos}
        self.assertEqual(dias, {"2026-11-06", "2026-11-07", "2026-11-08"})
        self.assertLessEqual(len(elegidos), gr.TOPE_CARRUSEL)

    def test_carrusel_sin_jueves_ni_salas_repetidas(self):
        evs = [ev("Jue", "2026-11-05 21:00:00", "Sala A"),
               ev("Vie A", "2026-11-06 21:00:00", "Sala B"),
               ev("Vie B", "2026-11-06 22:00:00", "Sala B", "musica")]
        elegidos = gr.elegir_finde(evs, JUEVES, SIN_AFICHE)
        self.assertEqual([e["titulo"] for e in elegidos], ["Vie A"])

    def test_historia_solo_del_dia_y_con_tope(self):
        evs = [ev(f"T{i}", "2026-11-08 20:00:00", f"Sala {i}") for i in range(7)]
        evs.append(ev("Otro dia", "2026-11-09 20:00:00", "Sala Z"))
        del_dia = gr.elegir_dia(evs, date(2026, 11, 8), SIN_AFICHE)
        self.assertEqual(len(del_dia), gr.TOPE_HISTORIA)
        self.assertTrue(all(e["fecha"].startswith("2026-11-08") for e in del_dia))


class TextosTests(unittest.TestCase):
    def test_instagram_sin_links_y_facebook_con_utm_a_la_obra(self):
        evs = [ev("Habitación Macbeth", "2026-11-06 21:00:00", "Teatro Metro")]
        ig = gr.texto_carrusel(evs, JUEVES, "instagram", {})
        fb = gr.texto_carrusel(evs, JUEVES, "facebook", {})
        self.assertIn("La Plata", ig)
        self.assertIn("Habitación Macbeth — Teatro Metro", ig)
        self.assertNotIn("https://", ig)
        self.assertIn("/en-vivo/obra/habitacion-macbeth/?utm_source=facebook", fb)
        self.assertLessEqual(ig.count("#"), 5)

    def test_arroba_la_sala_con_la_cuenta_de_venues(self):
        evs = [ev("Las Hijas", "2026-11-08 19:30:00", "Teatro Metro")]
        ig = gr.texto_carrusel(evs, JUEVES, "instagram", {})
        self.assertIn("Teatro Metro @teatrometrolaplata", ig)

    def test_sala_sin_cuenta_no_se_arroba(self):
        evs = [ev("Algo", "2026-11-08 19:30:00", "Un lugar inventado")]
        ig = gr.texto_carrusel(evs, JUEVES, "instagram", {})
        self.assertNotIn(" @", ig.split("\n")[2])


class GenerarTests(unittest.TestCase):
    def test_arma_imagenes_y_manifest(self):
        evs = [ev(f"Show {i}", f"2026-11-0{6 + i % 3} 21:00:00", f"Sala {i}",
                  ["teatro", "musica", "stand-up"][i % 3]) for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "ev.json"
            ruta.write_text(json.dumps({"generado": "x", "eventos": evs}), "utf-8")
            info = gr.generar(str(ruta), Path(tmp) / "redes", Path(tmp) / "afiches", hoy=JUEVES)
            carpeta = Path(tmp) / "redes" / "2026-11-05"
            m = json.loads((carpeta / "manifest.json").read_text("utf-8"))
            self.assertEqual(info["carrusel"], 8)  # tapa + 6 + cierre
            self.assertEqual(m["carrusel"]["publicar"], "2026-11-05")
            self.assertTrue(all(u.startswith("https://movete.info/redes/2026-11-05/")
                                for u in m["carrusel"]["imagenes"]))
            self.assertTrue((carpeta / "carrusel-00.jpg").exists())
            self.assertIn("2026-11-06", m["historias"])

    def test_poda_ediciones_viejas(self):
        with tempfile.TemporaryDirectory() as tmp:
            for d in ("2026-10-15", "2026-10-22", "2026-10-29", "2026-11-05"):
                (Path(tmp) / d).mkdir()
            gr._podar(Path(tmp))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()),
                             ["2026-10-22", "2026-10-29", "2026-11-05"])


class PublicarTests(unittest.TestCase):
    MANIFEST = {
        "edicion": "2026-11-05",
        "carrusel": {"publicar": "2026-11-05", "imagenes": ["https://movete.info/redes/a.jpg"],
                     "instagram": "ig", "facebook": "fb"},
        "historias": {"2026-11-05": {"imagen": "https://movete.info/redes/h.jpg", "facebook": "fb"},
                      "2026-11-06": {"imagen": "https://movete.info/redes/h2.jpg", "facebook": "fb"}},
    }

    def test_el_jueves_toca_carrusel_e_historia_y_el_viernes_solo_historia(self):
        jue = [n for n, _ in pr.tareas_de_hoy(self.MANIFEST, date(2026, 11, 5))]
        vie = [n for n, _ in pr.tareas_de_hoy(self.MANIFEST, date(2026, 11, 6))]
        self.assertEqual(jue, ["ig_carrusel", "fb_carrusel", "ig_historia", "fb_dia"])
        self.assertEqual(vie, ["ig_historia", "fb_dia"])

    def _carpeta(self, tmp):
        carpeta = Path(tmp) / "2026-11-05"
        carpeta.mkdir()
        (carpeta / "manifest.json").write_text(json.dumps(self.MANIFEST), "utf-8")
        return carpeta

    def test_sin_secrets_no_publica_y_termina_bien(self):
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = self._carpeta(tmp)
            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch("sys.argv", ["x", "--redes", tmp, "--hoy", "2026-11-05"]):
                self.assertEqual(pr.main(), 0)
            self.assertFalse((carpeta / "publicado.json").exists())

    def test_publica_una_sola_vez_por_dia(self):
        llamadas = []

        def falso(self, metodo, ruta, datos=None, token=None):
            llamadas.append((metodo, ruta))
            if metodo == "GET" and (datos or {}).get("fields") == "access_token":
                return {"access_token": "token-de-pagina"}
            if metodo == "GET":
                return {"status_code": "FINISHED"}
            if ruta.startswith("page/"):
                assert token == "token-de-pagina", "Facebook necesita el token de la página"
            return {"id": f"id{len(llamadas)}"}

        env = {"META_TOKEN": "t", "META_PAGE_ID": "page", "META_IG_ID": "ig"}
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = self._carpeta(tmp)
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(pr.Meta, "_llamar", falso), \
                 mock.patch.object(pr, "esperar_publicadas", lambda urls: None), \
                 mock.patch("sys.argv", ["x", "--redes", tmp, "--hoy", "2026-11-05"]):
                self.assertEqual(pr.main(), 0)
                primeras = len(llamadas)
                self.assertEqual(pr.main(), 0)  # segunda corrida del mismo día
            self.assertEqual(len(llamadas), primeras)
            hechas = json.loads((carpeta / "publicado.json").read_text("utf-8"))["2026-11-05"]
            self.assertEqual(set(hechas), {"ig_carrusel", "fb_carrusel", "ig_historia", "fb_dia"})
            self.assertIn(("POST", "ig/media_publish"), llamadas)
            self.assertIn(("POST", "page/feed"), llamadas)


if __name__ == "__main__":
    unittest.main()
