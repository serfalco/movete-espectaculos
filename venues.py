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
    'la_chicharra': (
        'Galpón de La Grieta y Biblioteca Popular La Chicharra',
        'Calle 71 N° 1138 esquina 18, La Plata',
        [
            'galpon de la grieta y biblioteca popular la chicharra',
            'galpon de la grieta',
            'biblioteca popular la chicharra',
            'la chicharra',
        ],
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
    'tres_empanadas': (
        'Tres Empanadas Comedia',
        'Calle 43 N° 1349 esquina 22, La Plata',
        [
            'tres empanadas comedia',
            'tres empanadas',
        ],
    ),
    # --- Salas chicas / under: direcciones investigadas y confirmadas ---
    'la_ferreteria': (
        'Teatro Bar Cultural La Ferretería', 'Calle 57 N° 827 e/ 11 y 12, La Plata',
        ['teatro bar cultural la ferreteria', 'la ferreteria bar cultural', 'la ferreteria'],
    ),
    'ciudad_de_gatos': (
        'Ciudad de Gatos', 'Calle 71 N° 1099, La Plata',
        ['ciudad de gatos'],
    ),
    'rene_favaloro': (
        'Teatro René Favaloro', 'Calle 67 e/ 116 y 117, La Plata',
        ['teatro rene favaloro', 'multiespacio cultural rene favaloro', 'rene favaloro'],
    ),
    'dardo_rocha': (
        'Centro Cultural Pasaje Dardo Rocha', 'Calle 50 e/ 6 y 7, La Plata',
        ['centro cultural pasaje dardo rocha', 'pasaje dardo rocha'],
    ),
    'islas_malvinas': (
        'Centro Cultural Islas Malvinas', 'Calle 50 N° 1200 (esq. 19), La Plata',
        ['centro cultural y de la memoria islas malvinas', 'centro cultural islas malvinas', 'islas malvinas'],
    ),
    'meridiano_v': (
        'Meridiano V', 'Av. 71 y 17, La Plata',
        ['meridiano v', 'estacion provincial'],
    ),
    'casa_unclan': (
        'Casa Unclan', 'Calle 5 N° 1512 e/ 63 y 64, La Plata',
        ['club cultural casa unclan', 'casa unclan'],
    ),
    'casa_pulsar': (
        'Casa Pulsar', 'Calle 58 N° 512, La Plata',
        ['casa pulsar'],
    ),
    'pena_bellas_artes': (
        'Peña de las Bellas Artes', 'Calle 49 N° 879, La Plata',
        ['la pena de las bellas artes', 'pena de las bellas artes', 'pena bellas artes'],
    ),
    'museo_almafuerte': (
        'Museo Almafuerte', 'Av. 66 N° 530, La Plata',
        ['museo almafuerte'],
    ),
    'republica_ninos': (
        'República de los Niños', 'Camino General Belgrano y 501, Manuel B. Gonnet, La Plata',
        ['republica de los ninos'],
    ),
    'museo_ciencias': (
        'Museo de Ciencias Naturales de La Plata', 'Paseo del Bosque s/n (Av. 60 y 122), La Plata',
        ['museo de ciencias naturales de la plata', 'museo de ciencias naturales', 'museo de la plata'],
    ),
    'centro_arte_unlp': (
        'Centro de Arte UNLP', 'Calle 48 N° 575 e/ 6 y 7 (Edificio Karakachoff), La Plata',
        ['centro de arte unlp', 'centro de arte de la unlp'],
    ),
    'observatorio_planetario': (
        'Observatorio / Planetario de La Plata', 'Paseo del Bosque s/n, La Plata',
        ['observatorio de la plata', 'museo de astronomia y geofisica', 'planetario'],
    ),
    'jardin_botanico': (
        'Jardín Botánico del Parque Saavedra', 'Parque Saavedra, Calle 66 y 13, La Plata',
        ['jardin botanico del parque saavedra', 'jardin botanico del parque saavedra de la plata'],
    ),
    'espacio_satelite': (
        'Espacio Satélite', 'Calle 6 N° 1030 e/ 53 y 54, La Plata',
        ['espacio satelite'],
    ),
    'refugio_62': (
        'Refugio 62', 'Calle 10 esquina 62, La Plata',
        ['refugio 62'],
    ),
    'desafinado_club': (
        'Desafinado Club', 'Diagonal 93 N° 52, City Bell, La Plata',
        ['desafinado club', 'desafinado'],
    ),
    'asoc_jubilados_abogados': (
        'Asociación de Jubilados y Pensionados (Caja de Abogados)',
        'Av. 13 N° 831/833, piso 6, La Plata',
        ['asociacion de jubilados y pensionados de la caja de prevision social para abogados'],
    ),
    'la_maga': (
        'La Maga Club de Arte', 'Calle 1 N° 177 e/ 35 y 36, La Plata',
        ['la maga club de arte', 'la maga'],
    ),
    'altillo_del_sur': (
        'Teatro El Altillo del Sur', 'Calle 1 N° 1693 casi esq. 67, La Plata',
        ['teatro el altillo del sur', 'el altillo del sur'],
    ),
    # --- Aportadas por Tres (conocimiento local) ---
    'guajira_bar': (
        'Guajira Bar', 'Calle 49 N° 484 e/ 4 y 5, La Plata',
        ['guajira bar', 'guajira'],
    ),
    'teatro_la_nonna': (
        'Teatro La Nonna', 'Calle 47 N° 395 (esq. 3), La Plata',
        ['teatro la nonna', 'la nonna'],
    ),
    'esquina_america': (
        'Esquina América', 'Calle 71 y 18, La Plata',
        ['esquina america'],
    ),
    'pura_vida': (
        'Pura Vida', 'Diagonal 78 N° 733 e/ 8 y 61, La Plata',
        ['pura vida'],
    ),
    'lazuli': (
        'Lázuli Espacio Cultural', 'Calle 62 N° 468 e/ 4 y 5, La Plata',
        ['lazuli espacio cultural', 'lazuli'],
    ),
    'la_culturosa': (
        'La Culturosa', 'Calle 8 N° 1092 e/ 54 y 55, La Plata',
        ['la culturosa'],
    ),
    'teatro_unlp_mediza': (
        'Teatro UNLP y Biblioteca Popular Teatral "Alberto Mediza"',
        'Calle 10 N° 1076 e/ 54 y 55, La Plata',
        ['teatro unlp y biblioteca popular teatral', 'teatro unlp', 'alberto mediza'],
    ),
    # --- Exportadas desde MoVeTe-venues ---
    'estudio_71': (
        'Estudio 71', 'Calle 71 N° 576, La Plata',
        ['estudio 71', 'estudio7 1'],
    ),
    'entre_pueblos': (
        'Entre Pueblos', 'Calle 13C N° 372, City Bell, La Plata',
        ['entre pueblos', 'entrepueblos', 'entrepueblos citybell'],
    ),
    'ruda': (
        'RUDA Red Ultrapotente de Amistad', 'Calle 70 N° 1136, La Plata',
        ['ruda', 'red ultrapotente de amistad', 'ruda red ultrapotente de amistad'],
    ),
    'espacio_sudaka': (
        'Espacio Sudaka', 'Av. 7 N° 1789, La Plata',
        ['espacio sudaka', 'sudaka'],
    ),
    'comunidad_raices': (
        'Comunidad Raíces - FM Raíces Rock', 'Calle 139 entre 40 y 41, La Plata',
        ['comunidad raices', 'comunidad raices lp', 'fm raices rock', 'raices rock'],
    ),
    'la_hormiguera': (
        'Espacio Cultural La Hormiguera', 'Calle 8 entre 61 y 62, La Plata',
        ['espacio cultural la hormiguera', 'la hormiguera', 'la hormiguera espacio'],
    ),
    'espacio_live': (
        'Espacio Live', 'Calle 56 N° 685, La Plata',
        ['espacio live', 'espacio live la plata'],
    ),
    'tcb_berisso': (
        'TCB - Teatro Comunitario de Berisso', 'Nueva York y Marsella N° 4711, Berisso',
        ['tcb', 'teatro comunitario de berisso', 'tcb berisso'],
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
