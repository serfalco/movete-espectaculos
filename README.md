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
