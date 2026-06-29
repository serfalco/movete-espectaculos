import unittest

from generar_edicion import render_evento
from venues import venue_info


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


if __name__ == "__main__":
    unittest.main()
