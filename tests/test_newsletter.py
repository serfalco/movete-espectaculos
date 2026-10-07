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


if __name__ == "__main__":
    unittest.main()
