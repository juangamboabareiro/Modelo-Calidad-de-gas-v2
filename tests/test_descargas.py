"""
El ZIP de descarga: `ui/descargas.py`.
======================================

Es la única salida del sandbox que el usuario se lleva puesta a Excel, y es
código PURO: recibe registro y flujos, devuelve bytes. No necesita runtime de
Streamlit, así que sale barato testearlo bien.

Lo que se protege acá:

  - El caso "configuré todo y quiero guardarlo antes de restablecer" —
    `armar_zip` tiene que funcionar SIN cascada resuelta. Está al lado del
    botón Restablecer justamente para que nadie pierda el trabajo; si
    reventara sin resultados, no cumpliría su razón de ser.
  - Las unidades: los CSV van en MMm3/d, no en unidades internas. Un número
    1000× más grande en un Excel que alguien manda por mail es el peor tipo
    de error, porque nadie lo cuestiona.
  - El round-trip del escenario: lo que sale en `escenario.json` tiene que
    poder volver a cargarse.
"""

import io
import json
import zipfile

import pytest

from ui.descargas import armar_zip, nombre_zip

from conftest import TOL_BALANCE


FACTOR_MM = 1000.0


def _abrir(datos: bytes) -> zipfile.ZipFile:
    assert isinstance(datos, (bytes, bytearray)), "armar_zip devuelve bytes"
    return zipfile.ZipFile(io.BytesIO(datos))


def test_sin_resolver_trae_solo_la_configuracion(registro_tres):
    """El caso que justifica el botón: guardar antes de restablecer.

    Si esto reventara, el usuario que configuró veinte minutos de escenario y
    todavía no resolvió perdería todo al tocar Restablecer.
    """
    datos = armar_zip(registro=registro_tres, intervenciones=[],
                      factor_mm=FACTOR_MM)
    with _abrir(datos) as z:
        nombres = z.namelist()
        assert "escenario.json" in nombres
        assert not [n for n in nombres if n.endswith(".csv")], (
            "sin cascada resuelta no puede haber resultados")


def test_con_resultados_trae_los_csv(registro_tres, cascada_resuelta):
    plantas, flujos = cascada_resuelta
    datos = armar_zip(registro=registro_tres, intervenciones=[],
                      plantas=plantas, flujos=flujos, factor_mm=FACTOR_MM)
    with _abrir(datos) as z:
        nombres = z.namelist()
        assert "escenario.json" in nombres
        assert "flujos_plantas.csv" in nombres
        assert any(n.upper().startswith("LEEME") or "LEEME" in n.upper()
                   for n in nombres), "el LEEME es lo que hace usable el ZIP"


def test_los_volumenes_del_csv_estan_en_mm(registro_tres, cascada_resuelta):
    """Regla 5 de CLAUDE.md: tres escalas conviven. El CSV va en MMm3/d.

    Se compara contra los flujos internos divididos por el factor, así el test
    no depende de los valores concretos del escenario sintético.
    """
    import pandas as pd

    plantas, flujos = cascada_resuelta
    datos = armar_zip(registro=registro_tres, intervenciones=[],
                      plantas=plantas, flujos=flujos, factor_mm=FACTOR_MM)

    with _abrir(datos) as z:
        csv = pd.read_csv(io.BytesIO(z.read("flujos_plantas.csv")))

    csv = csv.set_index(csv.columns[0])

    for nombre in flujos.index:
        esperado = float(flujos.loc[nombre, "vol_asignado"]) / FACTOR_MM
        obtenido = float(csv.loc[nombre, "vol_asignado"])
        assert abs(esperado - obtenido) < TOL_BALANCE, (
            f"{nombre}: el CSV no está en MMm3/d")

    # El LGN NO se convierte: ya viene en tn/d.
    for nombre in flujos.index:
        assert abs(float(flujos.loc[nombre, "lgn_asignado"])
                   - float(csv.loc[nombre, "lgn_asignado"])) < TOL_BALANCE, (
            f"{nombre}: el LGN no debería reescalarse, ya está en tn/d")


def test_el_escenario_del_zip_se_puede_volver_a_cargar(registro_tres):
    """Round-trip: el JSON que sale del ZIP tiene que poder re-aplicarse.

    Es la promesa del LEEME ("para volver a este mismo escenario, subilo").
    """
    from ui.escenarios import partir

    datos = armar_zip(registro=registro_tres, intervenciones=[],
                      factor_mm=FACTOR_MM)
    with _abrir(datos) as z:
        crudo = json.loads(z.read("escenario.json"))

    plantas_json, ductos_json = partir(crudo)
    assert {p["nombre"] for p in plantas_json} == set(registro_tres)
    assert ductos_json == []


def test_el_nombre_del_archivo_es_usable():
    nombre = nombre_zip()
    assert nombre.endswith(".zip")
    assert not set(nombre) & set('\\/:*?"<>|'), (
        "el nombre tiene que ser válido en Windows")
