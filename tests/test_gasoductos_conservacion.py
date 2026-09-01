"""
Gasoductos: un ducto no crea ni destruye gas.
=============================================

El invariante de `pipeline/gasoductos/intervenciones.py`:

    sum(Volumen_inyectado del área) == igual antes y después

de CUALQUIER intervención. Si esto se rompe, el impacto que se ve en las
plantas ya no es "por el ducto" sino por gas que apareció o se perdió, y la
comparación contra la corrida oficial pierde sentido.

También se verifica la coherencia de las columnas extensivas
(`Vol_<compuesto> = fracción * Volumen_inyectado`), que se desincronizan en
silencio si alguien mueve volumen sin recalcularlas.
"""

import pandas as pd
import pytest

pytest.importorskip("pipeline.gasoductos.intervenciones",
                    reason="el paquete de gasoductos no está instalado")

from pipeline.gasoductos.intervenciones import Intervencion, aplicar_intervenciones

from conftest import TOL_BALANCE


@pytest.fixture
def tablas(compuestos, croma_uniforme):
    yac = pd.DataFrame([
        {"Area": "Chivo", "HUB": "H1", "Gasoducto": "VMN",
         "Volumen_inyectado": 600.0, **croma_uniforme},
        {"Area": "Chivo", "HUB": "H1", "Gasoducto": "MEGA",
         "Volumen_inyectado": 400.0, **croma_uniforme},
        {"Area": "Solita", "HUB": "H2", "Gasoducto": "VMN",
         "Volumen_inyectado": 300.0, **croma_uniforme},
    ])
    for c in compuestos:
        yac[f"Vol_{c}"] = yac[c] * yac["Volumen_inyectado"]
    fdi = pd.DataFrame([
        {"Area": "VMN", "HUB": "-", "Gasoducto": "TTY",
         "Volumen_inyectado": 900.0, **croma_uniforme},
    ])
    for c in compuestos:
        fdi[f"Vol_{c}"] = fdi[c] * fdi["Volumen_inyectado"]
    return yac, fdi


def _vol_por_area(df):
    return df.groupby("Area")["Volumen_inyectado"].sum()


def _vol_columnas_coherentes(df, compuestos):
    for c in compuestos:
        col = f"Vol_{c}"
        if col not in df.columns:
            continue
        esperado = df[c] * df["Volumen_inyectado"]
        assert (df[col] - esperado).abs().max() < TOL_BALANCE, (
            f"'{col}' quedó desincronizada de Volumen_inyectado")


def test_alta_conserva_el_volumen_del_area(tablas, compuestos):
    yac, fdi = tablas
    antes = _vol_por_area(yac)

    interv = [Intervencion("alta", "GNuevo", area_origen="Chivo",
                           planta_destino="TTY", volumen=250.0)]
    yac2, fdi2, *_ = aplicar_intervenciones(yac, fdi, interv, compuestos, None)

    despues = _vol_por_area(yac2)
    assert abs(float(antes["Chivo"]) - float(despues["Chivo"])) < TOL_BALANCE
    assert abs(float(antes["Solita"]) - float(despues["Solita"])) < TOL_BALANCE

    # El resto se redistribuyó EN LA MISMA proporción (600:400 => 450:300).
    chivo = yac2[yac2["Area"] == "Chivo"].set_index("Gasoducto")["Volumen_inyectado"]
    assert abs(float(chivo["GNuevo"]) - 250.0) < TOL_BALANCE
    assert abs(float(chivo["VMN"]) - 450.0) < TOL_BALANCE
    assert abs(float(chivo["MEGA"]) - 300.0) < TOL_BALANCE

    _vol_columnas_coherentes(yac2, compuestos)
    _vol_columnas_coherentes(fdi2, compuestos)

    # Las tablas originales no se tocan: es un sandbox, no un cambio.
    assert abs(float(_vol_por_area(yac)["Chivo"]) - 1000.0) < TOL_BALANCE
    assert "GNuevo" not in set(yac["Gasoducto"])


def test_baja_redistribuye_proporcional_y_conserva(tablas, compuestos):
    yac, fdi = tablas
    antes = _vol_por_area(yac)

    interv = [Intervencion("baja", "MEGA")]
    yac2, *_ = aplicar_intervenciones(yac, fdi, interv, compuestos, None)

    despues = _vol_por_area(yac2)
    for area in antes.index:
        assert abs(float(antes[area]) - float(despues[area])) < TOL_BALANCE, (
            f"la baja cambió el gas total de {area}")

    # Chivo inyectaba 600 a VMN y 400 a MEGA: los 400 caen enteros en VMN.
    chivo = yac2[yac2["Area"] == "Chivo"]
    en_mega = chivo[chivo["Gasoducto"] == "MEGA"]["Volumen_inyectado"].sum()
    en_vmn = chivo[chivo["Gasoducto"] == "VMN"]["Volumen_inyectado"].sum()
    assert abs(float(en_mega)) < TOL_BALANCE
    assert abs(float(en_vmn) - 1000.0) < TOL_BALANCE

    _vol_columnas_coherentes(yac2, compuestos)


@pytest.mark.xfail(
    reason="DUDA-1 en docs/dudas.md: no está decidido si un área que pierde su "
           "única salida deja de inyectar. Hoy la fila se borra y el total "
           "inyectado baja, contra lo que promete el docstring del módulo.",
    strict=False)
def test_baja_sin_salida_deja_las_filas_como_estan(compuestos, croma_uniforme):
    """Un área que inyecta ÚNICAMENTE al ducto dado de baja no tiene a dónde
    ir: no se inventa un destino, las filas quedan y se reporta. Repartirlas
    por default sería decidir por el usuario algo que el modelo no sabe.

    Este test codifica la lectura del DOCSTRING del módulo. Si operaciones
    confirma que el pozo se cierra, hay que darlo vuelta: verificar que la fila
    desaparece y que el informe lo reporta. No borrarlo — el caso hay que
    cubrirlo en cualquiera de las dos lecturas."""
    yac = pd.DataFrame([
        {"Area": "Aislada", "HUB": "H9", "Gasoducto": "UNICO",
         "Volumen_inyectado": 100.0, **croma_uniforme},
    ])
    fdi = yac.iloc[0:0].copy()

    resultado = aplicar_intervenciones(
        yac, fdi, [Intervencion("baja", "UNICO")], compuestos, None)
    yac2 = resultado[0]

    fila = yac2[yac2["Area"] == "Aislada"]
    assert abs(float(fila["Volumen_inyectado"].sum()) - 100.0) < TOL_BALANCE, (
        "el gas del área sin salida no puede desaparecer ni moverse solo")
    assert set(fila["Gasoducto"]) == {"UNICO"}
