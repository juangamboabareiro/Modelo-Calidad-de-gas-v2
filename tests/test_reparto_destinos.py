"""
Reparto del sobrante entre N destinos: dominio.md §2.3.
=======================================================

Las dos reglas que se confunden fácil y por eso tienen tests separados:

  - **Bypass ESTRUCTURAL** (proporciones que suman < 1): esa fracción es una
    decisión del operador y NO se redistribuye.
  - **Bypass POR TOPE** (una rama saturada): el excedente SÍ se reoferta a las
    ramas con lugar, como haría un splitter real.

Se prueba por la puerta pública (`PlantaConfig.desde_dict` + `resolver_cascada`)
con una cascada mínima inventada: una cabecera A con mucho sobrante y dos
plantas B y C sobre el mismo pool. Así el test sobrevive a refactors internos
del reparto mientras la física sea la misma.
"""

import pytest

from pipeline.plantas.registro import PlantaConfig
from pipeline.plantas.cascada import resolver_cascada, desvio_balance

from conftest import TOL, TOL_BALANCE, planta_dict, conexion


POOL = "POOLX"
VOL_POOL = 1000.0
RETENCION = 0.5           # uniforme, para que lgn_unitario sea > 0
CAP_A = 100.0             # en tn/d: con retención 0.5, A trata 200 y sobran 800
GRANDE = 1.0e9            # capacidad que no limita


@pytest.fixture
def comunes_pool_unico(compuestos, croma_uniforme):
    import pandas as pd
    yac = pd.DataFrame([
        {"Area": "AreaX", "HUB": "H1", "Gasoducto": POOL,
         "Volumen_inyectado": VOL_POOL, **croma_uniforme},
    ])
    fdi = yac.iloc[0:0].copy()
    return dict(matriz_inyecciones=None, calcular_retenidos=None,
                propiedades=None, COMPUESTOS=compuestos,
                tabla_total_yacimientos=yac,
                tabla_total_flujos_directos=fdi)


def _armar(compuestos, conexiones_a):
    """Registro A -> {B, C}: A cabecera chica, B y C terminales holgadas."""
    dicts = [
        planta_dict("A", pool=POOL, cap_evac=CAP_A, compuestos=compuestos,
                    retencion=RETENCION, conexiones=conexiones_a,
                    deriva=True, cabecera=True),
        planta_dict("B", pool=POOL, cap_evac=GRANDE, compuestos=compuestos,
                    retencion=RETENCION, deriva=False, cabecera=False),
        planta_dict("C", pool=POOL, cap_evac=GRANDE, compuestos=compuestos,
                    retencion=RETENCION, deriva=False, cabecera=False),
    ]
    return {d["nombre"]: PlantaConfig.desde_dict(d) for d in dicts}


def _correr(compuestos, comunes, conexiones_a):
    reg = _armar(compuestos, conexiones_a)
    plantas, flujos = resolver_cascada(reg, comunes)
    assert desvio_balance(flujos) < TOL_BALANCE
    sobrante_a = float(flujos.loc["A", "sobrante"])
    derivados = plantas["A"]["flujos"].get("derivados", {})
    bypass_a = float(flujos.loc["A", "bypass"])
    return sobrante_a, derivados, bypass_a, flujos


def test_mitad_y_mitad_sin_tope(compuestos, comunes_pool_unico):
    sobrante, deriv, bypass, _ = _correr(
        compuestos, comunes_pool_unico,
        [conexion("B", 0.5), conexion("C", 0.5)])
    assert sobrante > 0, "el escenario necesita sobrante para tener sentido"
    assert abs(deriv.get("B", 0) - sobrante / 2) < TOL_BALANCE
    assert abs(deriv.get("C", 0) - sobrante / 2) < TOL_BALANCE
    assert abs(bypass) < TOL_BALANCE


def test_bypass_estructural_no_se_redistribuye(compuestos, comunes_pool_unico):
    """Proporciones 30% a B y nada más: el 70% restante es bypass POR
    DEFINICIÓN, aunque B y C tengan lugar de sobra."""
    sobrante, deriv, bypass, _ = _correr(
        compuestos, comunes_pool_unico, [conexion("B", 0.3)])
    assert abs(deriv.get("B", 0) - 0.3 * sobrante) < TOL_BALANCE
    assert abs(bypass - 0.7 * sobrante) < TOL_BALANCE
    assert deriv.get("C", 0) < TOL


def test_tope_saturado_se_reoferta_a_la_otra_rama(compuestos, comunes_pool_unico):
    """B con tope chico: su excedente va a C, no a bypass. Sin redistribución,
    agregar una rama con tope chico EMPEORARÍA el resultado global — eso es
    exactamente lo que este test impide reintroducir."""
    tope_b = 50.0
    sobrante, deriv, bypass, _ = _correr(
        compuestos, comunes_pool_unico,
        [conexion("B", 0.5, tope=tope_b), conexion("C", 0.5)])
    assert sobrante > 2 * tope_b, "el escenario necesita saturar el tope de B"
    assert abs(deriv.get("B", 0) - tope_b) < TOL_BALANCE
    assert abs(deriv.get("C", 0) - (sobrante - tope_b)) < TOL_BALANCE
    assert abs(bypass) < TOL_BALANCE


def test_proporciones_que_suman_mas_de_uno_se_renormalizan(
        compuestos, comunes_pool_unico):
    """0.8 + 0.6 = 1.4: no se puede derivar más sobrante del que hay. Se
    renormaliza hacia abajo y el derivado total es exactamente el sobrante."""
    sobrante, deriv, bypass, _ = _correr(
        compuestos, comunes_pool_unico,
        [conexion("B", 0.8), conexion("C", 0.6)])
    total = deriv.get("B", 0) + deriv.get("C", 0)
    assert abs(total - sobrante) < TOL_BALANCE
    assert total <= sobrante + TOL, "derivar más de lo que sobra crearía gas"
    # y las proporciones relativas se conservan: 8:6
    assert abs(deriv.get("B", 0) / total - 0.8 / 1.4) < 1e-6


def test_rama_al_cero_por_ciento_no_recibe(compuestos, comunes_pool_unico):
    """Una rama en 0% se puso en 0 a propósito: no recibe ni con gas sobrando."""
    _, deriv, _, _ = _correr(
        compuestos, comunes_pool_unico,
        [conexion("B", 0.0), conexion("C", 1.0)])
    assert deriv.get("B", 0) < TOL


def test_sin_deriva_todo_el_sobrante_es_bypass(compuestos, comunes_pool_unico):
    reg = _armar(compuestos, [conexion("B", 1.0)])
    reg["A"].deriva = False
    plantas, flujos = resolver_cascada(reg, comunes_pool_unico)
    assert desvio_balance(flujos) < TOL_BALANCE
    assert abs(float(flujos.loc["A", "vol_derivado"])) < TOL
    assert abs(float(flujos.loc["A", "bypass"])
               - float(flujos.loc["A", "sobrante"])) < TOL_BALANCE
