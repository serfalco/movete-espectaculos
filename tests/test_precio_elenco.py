"""Precio, disponibilidad y elenco: tarjeta visible y schema.org/Event."""
import json
import re
import unittest
from datetime import date

import generar_edicion as ge


def ev(**k):
    base = {"titulo": "Actúen", "fecha": "2026-11-21 21:00:00", "lugar": "Teatro Abierto",
            "categoria": "teatro", "url": "https://ejemplo.com/entradas", "fuente": "teatrocerca"}
    base.update(k)
    return base


def eventos_ld(html):
    salida = []
    for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        d = json.loads(m)
        salida += [i["item"] for i in d.get("itemListElement", [])
                   if isinstance(i.get("item"), dict) and i["item"].get("@type") == "Event"]
    return salida


class TextoPrecioTests(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(ge.texto_precio(ev(precio=30000, moneda="ARS")), "$30.000")
        self.assertEqual(ge.texto_precio(ev(precio=0)), "Gratis")
        self.assertEqual(ge.texto_precio(ev(precio=5000, disponibilidad="agotado")), "Agotado")
        self.assertEqual(ge.texto_precio(ev()), "")
        self.assertEqual(ge.texto_precio(ev(precio="30000")), "")


class SchemaTests(unittest.TestCase):
    def test_offers_con_precio_y_disponibilidad(self):
        x = ge.campos_extra_schema(ev(precio=30000, moneda="ARS", disponibilidad="disponible"),
                                   "Teatro Abierto")
        self.assertEqual(x["offers"], {"@type": "Offer", "url": "https://ejemplo.com/entradas",
                                       "price": 30000, "priceCurrency": "ARS",
                                       "availability": "https://schema.org/InStock"})
        self.assertNotIn("isAccessibleForFree", x)

    def test_gratis(self):
        x = ge.campos_extra_schema(ev(precio=0), "Teatro Abierto")
        self.assertEqual(x["offers"]["price"], 0)
        self.assertTrue(x["isAccessibleForFree"])

    def test_sin_datos_no_inventa(self):
        x = ge.campos_extra_schema(ev(), "Teatro Abierto")
        self.assertEqual(x["offers"], {"@type": "Offer", "url": "https://ejemplo.com/entradas"})
        self.assertNotIn("performer", x)

    def test_elenco_solo_en_la_pagina_de_la_obra(self):
        e = ev(elenco=["Letizia Bloisi", "Gerónimo De Urquiza"], precio=30000)
        self.assertNotIn("performer", ge.campos_extra_schema(e, "Teatro Abierto"))
        html = ge.render_pagina_obra("actuen", [e], date(2026, 11, 19))
        (item,) = eventos_ld(html)
        self.assertEqual([p["name"] for p in item["performer"]],
                         ["Letizia Bloisi", "Gerónimo De Urquiza"])
        self.assertIn("Con Letizia Bloisi, Gerónimo De Urquiza", html)
        self.assertIn("$30.000", html)

    def test_tarjeta_de_cartelera_sin_elenco_con_precio(self):
        html = ge.render_evento(ev(elenco=["Letizia Bloisi"], precio=30000))
        self.assertNotIn("Letizia", html)
        self.assertIn("$30.000", html)


if __name__ == "__main__":
    unittest.main()


class SinopsisTests(unittest.TestCase):
    def test_sinopsis_en_la_obra_y_en_su_schema(self):
        s = "Durante años, un escritor mantuvo su prestigio gracias a un pacto sobrenatural."
        html = ge.render_pagina_obra("actuen", [ev(sinopsis=s)], date(2026, 11, 19))
        self.assertIn(f'class="obra-sinopsis"', html)
        (item,) = eventos_ld(html)
        self.assertEqual(item["description"], s)

    def test_cartelera_no_marca_la_sinopsis(self):
        x = ge.campos_extra_schema(ev(sinopsis="Una obra sobre la memoria."), "Teatro Abierto")
        self.assertNotIn("memoria", x["description"])

    def test_sin_sinopsis_no_hay_parrafo(self):
        html = ge.render_pagina_obra("actuen", [ev()], date(2026, 11, 19))
        self.assertNotIn('class="obra-sinopsis"', html)
