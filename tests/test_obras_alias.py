"""Pruebas de la unificacion de paginas de obra.

Cada fuente escribe el mismo show con un subtitulo distinto y eso generaba dos
paginas para lo mismo ("emanero" y "emanero-todo-por-un-beso"), que en Google
se hacen competencia. Los casos salieron de la cartelera del 10/10/2026.
"""
import unittest
from datetime import date

import generar_edicion as g


def ev(titulo, lugar, fecha='2026-10-17 21:00:00', categoria='teatro'):
    return {'titulo': titulo, 'fecha': fecha, 'lugar': lugar,
            'categoria': categoria}


class AliasTests(unittest.TestCase):
    def test_variante_del_mismo_show_en_la_misma_sala(self):
        evs = [ev('Elena Roger', 'Teatro y Museo Coliseo Podestá', '2026-11-08 21:00:00'),
               ev('Elena Roger en concierto', 'Teatro Coliseo Podestá', '2026-12-08 21:00:00')]
        self.assertEqual(g.calcular_alias_obras(evs),
                         {'elena-roger-en-concierto': 'elena-roger'})

    def test_otra_sala_no_se_junta(self):
        evs = [ev('Elena Roger', 'Teatro Coliseo Podestá'),
               ev('Elena Roger en concierto', 'Teatro Metro')]
        self.assertEqual(g.calcular_alias_obras(evs), {})

    def test_titulo_corto_no_absorbe_otros(self):
        evs = [ev('La K', 'Teatro Metro'), ev('La Konga', 'Teatro Metro')]
        self.assertEqual(g.calcular_alias_obras(evs), {})
        evs = [ev('Rock', 'Teatro Metro'), ev('Rock nacional', 'Teatro Metro')]
        self.assertEqual(g.calcular_alias_obras(evs), {})

    def test_el_prefijo_tiene_que_terminar_en_palabra_entera(self):
        evs = [ev('Emanero', 'Teatro Metro'), ev('Emaneros del sur', 'Teatro Metro')]
        self.assertEqual(g.calcular_alias_obras(evs), {})

    def test_cadena_de_variantes_va_al_mas_corto(self):
        evs = [ev('Las del lirio', 'Teatro Metro'),
               ev('Las del lirio tullido', 'Teatro Metro'),
               ev('Las del lirio tullido retrato familiar', 'Teatro Metro')]
        r = g.calcular_alias_obras(evs)
        self.assertEqual(r['las-del-lirio-tullido'], 'las-del-lirio')
        self.assertEqual(r['las-del-lirio-tullido-retrato-familiar'], 'las-del-lirio')

    def test_cine_no_entra(self):
        evs = [ev('Los juegos del hambre', 'Cine City', categoria='cine'),
               ev('Los juegos del hambre sinsajo', 'Cine City', categoria='cine')]
        self.assertEqual(g.calcular_alias_obras(evs), {})


class ObraSlugTests(unittest.TestCase):
    def tearDown(self):
        g._ALIAS_OBRA.clear()

    def test_las_tarjetas_enlazan_a_la_principal(self):
        g._ALIAS_OBRA['elena-roger-en-concierto'] = 'elena-roger'
        self.assertEqual(g.obra_slug(ev('Elena Roger en concierto', 'X')), 'elena-roger')
        self.assertEqual(g.obra_slug(ev('Otra cosa distinta', 'X')), 'otra-cosa-distinta')


class PaginaAliasTests(unittest.TestCase):
    def test_la_variante_no_se_indexa_y_manda_a_la_principal(self):
        html = g.render_pagina_obra('elena-roger-en-concierto', [], date(2026, 10, 8),
                                    titulo_viejo='Elena Roger en concierto',
                                    alias_de='elena-roger')
        self.assertIn('noindex', html[:900])
        self.assertIn('url=/en-vivo/obra/elena-roger/', html)
        self.assertIn('href="/en-vivo/obra/elena-roger/"', html)

    def test_la_principal_usa_su_titulo(self):
        evs = [ev('Elena Roger en concierto', 'Teatro Coliseo Podestá', '2026-11-08 21:00:00'),
               ev('Elena Roger', 'Teatro Coliseo Podestá', '2026-12-08 21:00:00')]
        html = g.render_pagina_obra('elena-roger', evs, date(2026, 10, 8),
                                    titulo_principal='Elena Roger')
        self.assertIn('<h1>Elena Roger</h1>', html)
        self.assertNotIn('noindex', html[:900])


if __name__ == '__main__':
    unittest.main()


class PrincipalExistenteTests(unittest.TestCase):
    """Cuando el show termina, la variante sigue apuntando a la principal."""

    def test_variante_va_a_la_principal(self):
        from generar_edicion import principal_existente
        existentes = {"emanero", "emanero-todo-por-un-beso", "la-fiesta",
                      "la-fiesta-judia-klezmer"}
        self.assertEqual(principal_existente("emanero-todo-por-un-beso", existentes), "emanero")
        self.assertEqual(principal_existente("emanero", existentes), "")

    def test_slug_generico_no_absorbe(self):
        from generar_edicion import principal_existente
        self.assertEqual(principal_existente("la-fiesta-judia-klezmer",
                                             {"la-fiesta", "la-fiesta-judia-klezmer"}), "")
