import unittest
from datetime import date

from generar_edicion import render_evento, render_html
from venues import venue_info, venue_slug, venue_canonico


class VenueInfoTests(unittest.TestCase):
    def test_aliases_comparten_direccion(self):
        esperado = "Av. 44 N° 496 entre 4 y 5, La Plata"
        self.assertEqual(venue_info("ESPACIO 44")["direccion"], esperado)
        self.assertEqual(venue_info("Teatro Espacio 44")["direccion"], esperado)

    def test_coliseo_con_nombre_extendido(self):
        info = venue_info("Teatro y Museo Coliseo Podestá")
        self.assertEqual(info["nombre"], "Teatro Coliseo Podestá")
        self.assertIn("Calle 10", info["direccion"])

    def test_evento_con_direccion_muestra_como_llegar(self):
        html = render_evento({
            "titulo": "Primera noche",
            "fecha": "2026-06-28 19:00:00",
            "lugar": "LA MERCERIA TEATRO",
            "categoria": "teatro",
        })
        self.assertIn("Cómo llegar", html)
        self.assertIn("google.com/maps/search", html)
        self.assertIn("Calle+1+N%C2%B0+210", html)

    def test_evento_sin_direccion_no_inventa_mapa(self):
        html = render_evento({
            "titulo": "Evento de prueba",
            "fecha": "2026-06-28 19:00:00",
            "lugar": "Lugar todavía sin verificar",
            "categoria": "teatro",
        })
        self.assertNotIn("Cómo llegar", html)

    def test_categoria_queda_junto_a_la_fecha(self):
        html = render_evento({
            "titulo": "Una obra",
            "fecha": "2026-06-28 19:00:00",
            "lugar": "Espacio 44",
            "categoria": "teatro",
        })
        bloque_superior = html.split("</div>", 1)[0]
        self.assertIn("event-date", bloque_superior)
        self.assertIn("Teatro", bloque_superior)

    def test_sociedad_platense_de_stand_up_tiene_direccion(self):
        info = venue_info("Sociedad Platense de Stand Up")
        self.assertEqual(info["nombre"], "Sociedad Platense de Stand Up")
        self.assertEqual(
            info["direccion"],
            "Calle 43 N° 1349 esquina 22, La Plata",
        )

    def test_tres_empanadas_abre_la_cartelera_de_stand_up(self):
        # El segundo evento es el mismo show fijo que una fuente publica el
        # mismo viernes (26/6): no debe generar una segunda tarjeta.
        html, info = render_html(
            [
                {
                    "titulo": "Otra fecha de humor",
                    "fecha": "2026-06-25 20:00:00",
                    "lugar": "Espacio 44",
                    "categoria": "stand-up",
                },
                {
                    "titulo": "Sociedad Platense de Stand Up",
                    "fecha": "2026-06-26 21:30:00",
                    "lugar": "Tres Empanadas Comedia",
                    "categoria": "stand-up",
                },
            ],
            generado="2026-06-25T10:00:00",
            hoy=date(2026, 6, 28),
            categoria="stand-up",
        )
        cartelera = html.split('<section id="esta-semana"', 1)[1].split(
            '<section id="lo-que-se-viene"', 1
        )[0]

        self.assertEqual(info["esta_semana"], 2)
        # El show fijo aparece una sola vez pese al duplicado de la fuente,
        # y abre la cartelera (destacado, viernes) antes del evento del jueves.
        self.assertEqual(cartelera.count("Sociedad Platense de Stand Up"), 1)
        self.assertLess(
            cartelera.index("Viernes 26 de junio"),
            cartelera.index("Jueves 25 de junio"),
        )
        self.assertIn("21:30 hs", cartelera)
        # El nombre de la sala ahora linkea a su pagina propia.
        self.assertIn("/en-vivo/sala/tres-empanadas-comedia/", cartelera)
        self.assertIn("Calle+43+N%C2%B0+1349+esquina+22%2C+La+Plata", cartelera)


class VenueCanonicoTests(unittest.TestCase):
    def test_slug_seo_friendly(self):
        self.assertEqual(venue_slug("Teatro Coliseo Podestá"), "teatro-coliseo-podesta")
        self.assertEqual(venue_slug("Tres Empanadas Comedia"), "tres-empanadas-comedia")

    def test_sala_con_direccion_tiene_pagina(self):
        info = venue_canonico("Tres Empanadas Comedia")
        self.assertIsNotNone(info)
        self.assertEqual(info["slug"], "tres-empanadas-comedia")
        self.assertFalse(info["masivo"])
        self.assertIn("Calle 43", info["direccion"])

    def test_masivo_tiene_pagina_pero_sin_direccion(self):
        info = venue_canonico("Estadio Único Diego Maradona")
        self.assertIsNotNone(info)
        self.assertTrue(info["masivo"])
        self.assertEqual(info["direccion"], "")
        self.assertEqual(info["slug"], "estadio-unico-diego-maradona")

    def test_lugar_generico_no_tiene_pagina(self):
        self.assertIsNone(venue_canonico("La Plata"))
        self.assertIsNone(venue_canonico("Lugar todavía sin verificar"))


if __name__ == "__main__":
    unittest.main()
