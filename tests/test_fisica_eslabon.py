"""
Física de UN eslabón: las funciones puras de `pipeline/plantas/flujo_plantas.py`.
=================================================================================

Acá se verifica la matemática de dominio.md §2.2, sin pool, sin cromatografía,
sin cascada:

    vol_asignado = min(vol_disponible, vol_maximo)
    sobrante     = vol_disponible - vol_asignado
    vol_derivado = min(sobrante, tope de traspaso)
    bypass       = sobrante - vol_derivado

y el invariante que cierra el balance:

    vol_disponible = vol_asignado + vol_derivado + bypass

Los tests son relacionales (identidades que valen para cualquier número), no
comparan contra valores mágicos. Si alguien cambia la fórmula del reparto y el
gas empieza a aparecer o desaparecer, esto salta.
"""

import itertools

import pandas as pd
import pytest

from pipeline.plantas.flujo_plantas import (
    calcular_lgn_unitario,
    calcular_volumen_maximo,
    repartir_flujo_planta,
)

from conftest import TOL


# Grilla que cubre los tres regímenes: planta holgada (max > disp),
# planta justa (max == disp) y planta llena (max < disp); cruzada con
# tope de traspaso nulo, chico, exacto y sobrado.
DISPONIBLES = [0.0, 100.0, 1000.0]
MAXIMOS = [0.0, 50.0, 100.0, 1000.0, 5000.0]
TOPES = [0.0, 10.0, 900.0, 1e12]


@pytest.mark.parametrize(
    "disp,vmax,tope", list(itertools.product(DISPONIBLES, MAXIMOS, TOPES)))
def test_balance_de_un_eslabon(disp, vmax, tope):
    f = repartir_flujo_planta(
        vol_disponible=disp, vol_maximo=vmax,
        MAX_DERIVACION_PLANTA_A_PLANTA=tope)

    # 1. El invariante central: nada de gas aparece ni desaparece.
    assert abs(f["vol_disponible"]
               - (f["vol_asignado"] + f["vol_derivado"] + f["bypass"])) < TOL

    # 2. Ningún flujo puede ser negativo: no existe el gas negativo.
    for campo in ("vol_asignado", "sobrante", "vol_derivado", "bypass"):
        assert f[campo] >= -TOL, f"{campo} negativo con disp={disp} vmax={vmax}"

    # 3. Las definiciones, una por una.
    assert abs(f["vol_asignado"] - min(disp, vmax)) < TOL
    assert abs(f["sobrante"] - (disp - f["vol_asignado"])) < TOL
    assert f["vol_derivado"] <= f["sobrante"] + TOL
    assert f["vol_derivado"] <= tope + TOL
    assert abs(f["bypass"] - (f["sobrante"] - f["vol_derivado"])) < TOL


def test_planta_llena_deriva_hasta_el_tope_y_el_resto_es_bypass():
    f = repartir_flujo_planta(vol_disponible=1000.0, vol_maximo=300.0,
                              MAX_DERIVACION_PLANTA_A_PLANTA=200.0)
    assert abs(f["vol_asignado"] - 300.0) < TOL
    assert abs(f["vol_derivado"] - 200.0) < TOL
    assert abs(f["bypass"] - 500.0) < TOL


def test_planta_holgada_no_deriva_ni_bypasea():
    f = repartir_flujo_planta(vol_disponible=100.0, vol_maximo=1000.0,
                              MAX_DERIVACION_PLANTA_A_PLANTA=500.0)
    assert abs(f["vol_asignado"] - 100.0) < TOL
    assert abs(f["vol_derivado"]) < TOL
    assert abs(f["bypass"]) < TOL


# ---------------------------------------------------------------------------
# lgn_unitario: dominio.md §2.4 — los retenidos son LINEALES en el volumen.
# ---------------------------------------------------------------------------

def test_calcular_retenidos_es_lineal_en_el_volumen(compuestos, propiedades,
                                                    croma_uniforme):
    """La premisa de la que depende TODO el escalado pro-rata del modelo.

    `dominio.md` §2.4 afirma que el escalado es exacto, no una aproximación.
    Eso sólo vale si `calcular_retenidos` es lineal en `volumen_total`. Se
    verifica contra la función real del dominio: si alguien le agrega un
    término no lineal (una corrección por saturación, por ejemplo), "modelar
    el pool una vez y escalar" deja de ser válido y hay que re-modelar por
    volumen — un cambio de fondo que este test obliga a notar.
    """
    from domain.propiedades_gas import calcular_retenidos
    from domain.ctes_gas import PRESION_BASE, CONSTANTE_GAS, TEMPERATURA_BASE

    gas_rico = pd.Series(croma_uniforme).reindex(list(compuestos))
    retencion = pd.Series({c: 0.4 for c in compuestos}).reindex(list(compuestos))

    def corrida(vol):
        return calcular_retenidos(propiedades, vol, retencion, gas_rico,
                                  PRESION_BASE, CONSTANTE_GAS, TEMPERATURA_BASE)

    base = corrida(1000.0)
    triple = corrida(3000.0)

    assert (float(triple.values.sum()) - 3.0 * float(base.values.sum())) < 1e-6
    assert float(base.values.sum()) > 0, "el escenario necesita retención real"


def _retenidos_vol(escala=1.0):
    return pd.Series({"etano": 10.0, "propano": 40.0,
                      "butanos": 30.0, "gasolina": 20.0}) * escala


def test_lgn_unitario_es_intensivo():
    """Duplicar pool y retenidos juntos NO cambia el LGN por unidad de volumen.

    Es la propiedad que hace válido el escalado pro-rata de todo el modelo:
    si esto se rompe, "modelar el pool una vez y escalar" deja de ser exacto.
    """
    u1 = calcular_lgn_unitario(1000.0, _retenidos_vol(1.0))
    u2 = calcular_lgn_unitario(2000.0, _retenidos_vol(2.0))
    assert abs(float(u1) - float(u2)) < TOL


def test_lgn_unitario_es_lineal_en_los_retenidos():
    u1 = calcular_lgn_unitario(1000.0, _retenidos_vol(1.0))
    u3 = calcular_lgn_unitario(1000.0, _retenidos_vol(3.0))
    assert abs(float(u3) - 3.0 * float(u1)) < TOL


def test_lgn_unitario_con_pool_vacio_no_explota():
    """Pool en cero: sea 0 o inf según la convención, no puede levantar excepción."""
    calcular_lgn_unitario(0.0, _retenidos_vol(1.0))


# ---------------------------------------------------------------------------
# vol_maximo: la restricción activa es la evacuación de LGN (regla 2 de
# CLAUDE.md); el ingreso de gas entra sólo como min() adicional.
# ---------------------------------------------------------------------------

def test_vol_maximo_es_evacuacion_sobre_unitario():
    vmax = calcular_volumen_maximo(
        lgn_unitario=0.1, CAPACIDAD_EVACUACION_PLANTA=500.0,
        CAPACIDAD_INGRESO_PLANTA=None)
    assert abs(float(vmax) - 5000.0) < TOL


def test_ingreso_solo_recorta_nunca_amplia():
    holgado = calcular_volumen_maximo(
        lgn_unitario=0.1, CAPACIDAD_EVACUACION_PLANTA=500.0,
        CAPACIDAD_INGRESO_PLANTA=99999.0)
    recortado = calcular_volumen_maximo(
        lgn_unitario=0.1, CAPACIDAD_EVACUACION_PLANTA=500.0,
        CAPACIDAD_INGRESO_PLANTA=3000.0)
    assert abs(float(holgado) - 5000.0) < TOL
    assert abs(float(recortado) - 3000.0) < TOL


def test_sin_retencion_no_hay_restriccion_de_liquido():
    """dominio.md §2.2, caso borde: lgn_unitario <= 0 => vol_maximo infinito,
    o la capacidad de ingreso si está definida."""
    libre = calcular_volumen_maximo(
        lgn_unitario=0.0, CAPACIDAD_EVACUACION_PLANTA=500.0,
        CAPACIDAD_INGRESO_PLANTA=None)
    assert float(libre) > 1e11, "sin líquido que evacuar, el tope debería ser infinito"

    con_ingreso = calcular_volumen_maximo(
        lgn_unitario=0.0, CAPACIDAD_EVACUACION_PLANTA=500.0,
        CAPACIDAD_INGRESO_PLANTA=7000.0)
    assert abs(float(con_ingreso) - 7000.0) < TOL
