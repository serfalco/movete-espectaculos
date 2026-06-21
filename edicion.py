"""Lógica de ediciones semanales.

- La edición sale el JUEVES y cubre jueves → miércoles siguiente (7 días).
- Es foto fija: se genera una vez y no se toca.
- Cada edición vive en /espectaculos/AAAA-MM-DD/ (el jueves de salida).

Estas funciones calculan a qué edición pertenece una fecha dada y el rango
de la edición vigente.
"""
from datetime import date, datetime, timedelta

JUEVES = 3  # weekday(): lunes=0 ... jueves=3


def jueves_de_edicion(d: date = None) -> date:
    """Devuelve el jueves de la edición que cubre la fecha `d`.

    Si hoy es jueves, es la edición de hoy. Si es viernes..miércoles,
    es el jueves anterior.
    """
    d = d or date.today()
    dias_desde_jueves = (d.weekday() - JUEVES) % 7
    return d - timedelta(days=dias_desde_jueves)


def rango_edicion(jueves: date):
    """(inicio, fin) de la edición: jueves 00:00 → miércoles 23:59."""
    inicio = datetime.combine(jueves, datetime.min.time())
    fin = datetime.combine(jueves + timedelta(days=6),
                           datetime.max.time().replace(microsecond=0))
    return inicio, fin


def slug_edicion(jueves: date) -> str:
    """URL de la edición: '2026-06-25'."""
    return jueves.isoformat()


def en_esta_semana(fecha_str: str, jueves: date) -> bool:
    """¿El evento cae en la ventana jueves→miércoles de esta edición?"""
    try:
        f = datetime.strptime(fecha_str[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return False
    inicio, fin = rango_edicion(jueves)
    return inicio <= f <= fin


# Nombres de meses y días en español (sin depender del locale del sistema)
MESES = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
MESES_ABR = ['', 'ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN',
             'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']


def etiqueta_dia(d: date) -> str:
    """'Jueves 25 de junio'."""
    return f'{DIAS[d.weekday()]} {d.day} de {MESES[d.month]}'


def etiqueta_rango(jueves: date) -> str:
    """'del 25/6 al 1/7' para el hero."""
    fin = jueves + timedelta(days=6)
    return f'del {jueves.day}/{jueves.month} al {fin.day}/{fin.month}'
