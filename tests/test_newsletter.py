"""Pruebas de la seleccion del newsletter. Offline."""
import unittest
from datetime import date

from generar_newsletter import _elegir, armar_email


def ev(titulo, fecha, lugar, cat="teatro", fuente="genda"):
    return {"titulo": titulo, "fecha": fecha, "lugar": lugar,
            "categoria": cat, "fuente": fuente, "imagen": ""}


class ElegirTests(unittest.TestCase):
    def test_una_funcion_por_sala_y_sin_titulos_repetidos(self):
        evs = [ev("A", "2026-10-02 21:00:00", "Sala X"),
               ev("B", "2026-10-03 21:00:00", "Sala X"),
               ev("C", "2026-10-03 21:00:00", "Sala Y"),
               ev("c", "2026-10-04 21:00:00", "Sala Z")]
        titulos = [e["titulo"].lower() for e in _elegir(evs, 4)]
        self.assertEqual(len(titulos), 2)
        self.assertEqual(len(set(titulos)), 2)

    def test_descarta_titulos_vacios(self):
        evs = [ev("SIN DATOS", "2026-10-02 21:00:00", "Sala X")]
        self.assertEqual(_elegir(evs, 3), [])

    def test_respeta_el_tope(self):
        evs = [ev(f"T{i}", "2026-10-03 21:00:00", f"Sala {i}") for i in range(10)]
        self.assertEqual(len(_elegir(evs, 3)), 3)


class EmailTests(unittest.TestCase):
    def test_arma_rubros_y_no_usa_encabezados_grandes(self):
        evs = [ev("Obra", "2026-10-03 21:00:00", "Sala X"),
               ev("Show", "2026-10-03 22:00:00", "Sala Y", cat="musica")]
        _, cuerpo = armar_email(evs, date(2026, 10, 1))
        self.assertIn("🎭 Teatro", cuerpo)
        self.assertIn("🎵 Música", cuerpo)
        self.assertNotIn("###", cuerpo)

    def test_html_un_evento_por_fila_con_link_a_la_obra(self):
        evs = [ev("Obra Uno", "2026-10-03 21:00:00", "Sala X"),
               ev("Obra Dos", "2026-10-04 20:30:00", "Sala Y")]
        _, cuerpo = armar_email(evs, date(2026, 10, 1))
        self.assertTrue(cuerpo.startswith("<!-- buttondown-editor-mode: plaintext -->"))
        self.assertGreaterEqual(cuerpo.count("<tr><td width="), 2)  # filas separadas
        self.assertIn("https://movete.info/en-vivo/obra/obra-uno/", cuerpo)
        self.assertIn("20:30 h", cuerpo)

    def test_escapa_html_del_titulo(self):
        evs = [ev("<b>Rock & Roll</b>", "2026-10-03 21:00:00", "Sala X", cat="musica")]
        _, cuerpo = armar_email(evs, date(2026, 10, 1))
        self.assertNotIn("<b>Rock", cuerpo)
        self.assertIn("&lt;b&gt;Rock &amp; Roll", cuerpo)


class ImagenTests(unittest.TestCase):
    def test_usa_copia_de_movete_si_existe(self):
        import os, tempfile
        from generar_newsletter import _imagen
        from imagenes import nombre_local
        url = "https://ejemplo.com/afiche.jpg"
        with tempfile.TemporaryDirectory() as d:
            os.environ["MOVETE_AFICHES_DIR"] = d
            try:
                self.assertEqual(_imagen({"imagen": url}), "")  # sin copia, sin imagen
                open(os.path.join(d, nombre_local(url)), "wb").close()
                self.assertEqual(_imagen({"imagen": url}),
                                 "https://movete.info/assets/afiches/" + nombre_local(url))
            finally:
                del os.environ["MOVETE_AFICHES_DIR"]


if __name__ == "__main__":
    unittest.main()
