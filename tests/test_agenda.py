"""Páginas fijas /en-vivo/hoy/ y /en-vivo/fin-de-semana/."""
import unittest
from datetime import date

import generar_edicion as g


def ev(titulo, fecha, lugar="Teatro Metro", categoria="teatro"):
    return {"titulo": titulo, "fecha": fecha, "lugar": lugar, "categoria": categoria}


class FindeTests(unittest.TestCase):
    def test_entre_semana_es_el_que_viene(self):
        self.assertEqual(g.dias_finde(date(2026, 10, 21)),
                         [date(2026, 10, 23), date(2026, 10, 24), date(2026, 10, 25)])

    def test_en_finde_es_el_actual(self):
        self.assertEqual(g.dias_finde(date(2026, 10, 24))[0], date(2026, 10, 23))
        self.assertEqual(g.dias_finde(date(2026, 10, 25))[0], date(2026, 10, 23))


class PaginaAgendaTests(unittest.TestCase):
    EVS = [ev("Obra del jueves", "2026-10-22 21:00:00"),
           ev("Obra del sábado", "2026-10-24 21:00:00"),
           ev("Obra de noviembre", "2026-11-20 21:00:00")]

    def test_hoy_tiene_siete_dias(self):
        html = g.render_pagina_agenda("hoy", self.EVS, date(2026, 10, 22))
        self.assertIn('data-dia="2026-10-22"', html)
        self.assertIn('data-dia="2026-10-24"', html)
        self.assertNotIn("Obra de noviembre", html)
        self.assertIn('href="https://movete.info/en-vivo/hoy/"', html)
        self.assertNotIn("noindex", html)

    def test_finde_solo_viernes_a_domingo(self):
        html = g.render_pagina_agenda("fin-de-semana", self.EVS, date(2026, 10, 22))
        self.assertIn("Obra del sábado", html)
        self.assertNotIn("Obra del jueves", html)

    def test_sin_eventos_no_se_indexa(self):
        html = g.render_pagina_agenda("fin-de-semana", [], date(2026, 10, 22))
        self.assertIn("noindex", html)


if __name__ == "__main__":
    unittest.main()
