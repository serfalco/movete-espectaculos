"""Pasadas intermedias (martes y domingo): actualizan todo menos la edicion
fechada vigente, que queda como la publico el jueves."""
import json
from datetime import date

import generar_edicion as g

JUEVES = date(2026, 11, 12)
DOMINGO = date(2026, 11, 15)


def _eventos(tmp_path, eventos):
    p = tmp_path / "eventos.json"
    p.write_text(json.dumps({"generado": "x", "eventos": eventos}), encoding="utf-8")
    return str(p)


def _ev(titulo, fecha):
    return {"titulo": titulo, "fecha": fecha, "lugar": "Teatro Argentino",
            "categoria": "teatro"}


def test_el_domingo_no_pisa_la_edicion_del_jueves(tmp_path):
    out = tmp_path / "en-vivo"
    jueves_json = _eventos(tmp_path, [_ev("Obra del viernes", "2026-11-13 21:00:00"),
                                      _ev("Obra del martes", "2026-11-17 21:00:00")])
    g.generar(jueves_json, str(out), hoy=JUEVES, hoy_real=JUEVES, afiches_dir=None)
    fechada = out / "2026-11-12" / "index.html"
    antes = fechada.read_text(encoding="utf-8")
    assert "Obra del viernes" in antes

    # El domingo el scraper ya descarto lo del viernes y trae algo nuevo.
    domingo_json = _eventos(tmp_path, [_ev("Obra del martes", "2026-11-17 21:00:00"),
                                       _ev("Obra nueva", "2026-11-18 20:00:00")])
    g.generar(domingo_json, str(out), hoy=DOMINGO, hoy_real=DOMINGO,
              afiches_dir=None, sin_fechada=True)

    assert fechada.read_text(encoding="utf-8") == antes
    vigente = (out / "index.html").read_text(encoding="utf-8")
    assert "Obra nueva" in vigente
    assert (out / "obra" / g.obra_slug(_ev("Obra nueva", "2026-11-18 20:00:00")) / "index.html").exists()
