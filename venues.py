"""Venues masivos — lista blanca de lugares de miles de personas.

Un evento en uno de estos venues va al bloque "Lo que se viene" y tiene
página permanente propia. El resto va solo a la edición semanal.

El match se hace por alias normalizados, porque los scrapers traen nombres
sucios y variados ("Estadio UNO", "UNO de Estudiantes", etc.).

OJO: Estadio UNO (Estudiantes) y Estadio Único (provincial) son DISTINTOS.
"""
import re
import unicodedata

# Cada venue masivo: clave canónica → (nombre lindo, lista de alias)
VENUES_MASIVOS = {
    'teatro_argentino': (
        'Teatro Argentino de La Plata',
        ['teatro argentino', 'argentino la plata', 'teatro arg'],
    ),
    'hipodromo': (
        'Hipódromo de La Plata',
        ['hipodromo', 'hipodromo la plata', 'hipodromo de la plata'],
    ),
    'atenas': (
        'Estadio Atenas',
        ['atenas', 'estadio atenas', 'club atenas'],
    ),
    'estadio_uno': (
        'Estadio UNO',  # Estudiantes de La Plata (EDLP)
        ['estadio uno', 'uno de estudiantes', 'jorge luis hirschi',
         'estadio jorge luis hirschi', 'uno edlp', 'estadio de estudiantes'],
    ),
    'estadio_unico': (
        'Estadio Único Diego Maradona',  # provincial, distinto de UNO
        ['estadio unico', 'unico', 'diego armando maradona',
         'estadio diego maradona', 'ciudad de la plata', 'estadio ciudad de la plata',
         'estadio unico diego maradona'],
    ),
}


def _normalizar(texto: str) -> str:
    """Pasa a minúsculas, saca tildes y colapsa espacios."""
    texto = texto.lower().strip()
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r'[^a-z0-9 ]', ' ', texto)
    return re.sub(r'\s+', ' ', texto).strip()


def venue_masivo(lugar: str):
    """Si el lugar es un venue masivo, devuelve (clave, nombre_lindo).
    Si no, devuelve None.

    OJO con el orden: 'estadio unico' contiene 'unico', y 'estadio uno'
    NO debe matchear con 'unico'. Por eso comparamos alias completos
    como palabras, no como substring suelto.
    """
    norm = _normalizar(lugar)
    if not norm:
        return None

    for clave, (nombre, alias) in VENUES_MASIVOS.items():
        for a in alias:
            a_norm = _normalizar(a)
            # match por palabra/frase completa, con límites
            if re.search(rf'(^|\s){re.escape(a_norm)}(\s|$)', norm):
                return (clave, nombre)
    return None
