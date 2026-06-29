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


# Direcciones confirmadas para enriquecer las tarjetas de la cartelera. Los
# alias absorben las variantes de mayusculas y nombres que traen las fuentes.
VENUES_DIRECCIONES = {
    'area_chica': (
        'Área Chica', 'Boulevard 83 N° 403, La Plata', ['area chica'],
    ),
    'los_hornos_1103': (
        'Los Hornos', 'Av. 66 y 173, Los Hornos, La Plata',
        ['av 66 y 173 los hornos', '66 y 173 los hornos'],
    ),
    'casa_hereje': (
        'Casa Hereje', 'Calle 40 N° 973, La Plata', ['casa hereje'],
    ),
    'centro_viejo_almacen': (
        'Centro Cultural Viejo Almacén El Obrero',
        'Av. 13 N° 1900 esquina 71, La Plata',
        ['centro cultural viejo almacen el obrero', 'viejo almacen el obrero'],
    ),
    'colibri': (
        'Colibrí Arte y Cultura', 'Diagonal 77 N° 444, La Plata',
        ['colibri arte y cultura'],
    ),
    'escenario_40': (
        'Escenario 40', 'Calle 40 N° 1180, La Plata', ['escenario 40'],
    ),
    'espacio_44': (
        'Espacio 44', 'Av. 44 N° 496 entre 4 y 5, La Plata',
        ['espacio 44', 'teatro espacio 44'],
    ),
    'espacio_medusa': (
        'Espacio Medusa', 'Calle 55 N° 780 entre 10 y 11, La Plata',
        ['espacio medusa', 'medusa la plata'],
    ),
    'la_merceria': (
        'La Mercería Teatro', 'Calle 1 N° 210, La Plata',
        ['la merceria teatro', 'merceria teatro'],
    ),
    'sala_420': (
        'Sala 420', 'Calle 42 N° 571 entre 6 y 7, La Plata', ['sala 420'],
    ),
    'teatro_abierto': (
        'Teatro Abierto', 'Calle 38 N° 1263 entre 20 y 21, La Plata',
        ['teatro abierto'],
    ),
    'teatro_argentino': (
        'Teatro Argentino de La Plata', 'Av. 51 entre 9 y 10, La Plata',
        ['teatro argentino', 'teatro argentino la plata'],
    ),
    'teatro_discepolo': (
        'Teatro Armando Discépolo', 'Calle 12 entre 62 y 63, La Plata',
        ['teatro armando discepolo', 'armando discepolo'],
    ),
    'teatro_coliseo': (
        'Teatro Coliseo Podestá', 'Calle 10 entre 46 y 47, La Plata',
        ['teatro coliseo podesta', 'teatro y museo coliseo podesta', 'coliseo podesta'],
    ),
    'teatro_el_escape': (
        'Teatro El Escape', 'Calle 44 N° 1443 entre 23 y 24, La Plata',
        ['teatro el escape', 'el escape'],
    ),
    'teatro_la_lechuza': (
        'Teatro La Lechuza', 'Calle 58 entre 10 y 11, La Plata',
        ['teatro la lechuza', 'la lechuza teatro'],
    ),
    'teatro_metro': (
        'Teatro Metro', 'Calle 4 N° 978 entre 51 y 53, La Plata',
        ['teatro metro'],
    ),
    'teatro_opera': (
        'Teatro Ópera La Plata', 'Calle 58 entre 10 y 11, La Plata',
        ['teatro opera', 'teatro opera la plata'],
    ),
    'telon_negro': (
        'Telón Negro Teatro', 'Calle 13 entre 32 y 33, La Plata',
        ['telon negro teatro', 'telon negro'],
    ),
    'sociedad_platense_stand_up': (
        'Sociedad Platense de Stand Up',
        'Calle 43 N° 1349 esquina 22, La Plata',
        [
            'sociedad platense de stand up',
            'sociedad platense stand up',
            'tres empanadas comedia',
        ],
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


def venue_info(lugar: str) -> dict:
    """Devuelve nombre canonico y direccion confirmada para un lugar."""
    original = str(lugar or '').strip() or 'La Plata'
    norm = _normalizar(original)
    for nombre, direccion, alias in VENUES_DIRECCIONES.values():
        for candidato in alias:
            alias_norm = _normalizar(candidato)
            if re.search(rf'(^|\s){re.escape(alias_norm)}(\s|$)', norm):
                return {'nombre': nombre, 'direccion': direccion}
    return {'nombre': original, 'direccion': ''}
