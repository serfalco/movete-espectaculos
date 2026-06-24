# MoVeTe Espectáculos / En Vivo

Genera la edición semanal de **En Vivo** para `movete.info`.

Entrada:

```txt
eventos.json
```

Salida:

```txt
Movete-info/en-vivo/index.html
Movete-info/en-vivo/AAAA-MM-DD/index.html
```

Correr local:

```bash
python generar_edicion.py eventos.json ../Movete-info/en-vivo
```
