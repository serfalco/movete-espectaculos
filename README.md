# MoVeTe Espectáculos / En Vivo

Genera la edición semanal de **En Vivo** para `movete.info`.

Entrada:

```txt
eventos.json
```

`eventos.json` lo genera `movete-scraper` en cada corrida y no se versiona.
`eventos.ejemplo.json` es una muestra vieja (junio de 2026) para probar local;
no es la cartelera real.

Salida:

```txt
Movete-info/en-vivo/index.html
Movete-info/en-vivo/AAAA-MM-DD/index.html
```

Correr local:

```bash
python generar_edicion.py --eventos eventos.ejemplo.json --output ../Movete-info/en-vivo
```

## Redes (Instagram + Facebook)

`generar_redes.py` dibuja, desde `eventos.json`, el carrusel del finde y una
historia por día en `Movete-info/redes/<jueves>/` (corre en el workflow del
jueves). `publicar_redes.py` los publica por la API oficial de Meta; lo dispara
`Movete-info/.github/workflows/redes.yml`, apagado hasta cargar las cuentas
(ver `Movete-info/redes/LEEME.md`).

```bash
python generar_redes.py --eventos eventos.ejemplo.json --salida _preview_redes --hoy 2026-06-18
python publicar_redes.py --redes _preview_redes --hoy 2026-06-18 --dry-run
```
