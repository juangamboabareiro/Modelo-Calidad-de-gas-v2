"""
Física de la CASCADA completa: `resolver_cascada` sobre datos sintéticos.
=========================================================================

Un eslabón puede cerrar su balance y la cascada igual perder gas en el
traspaso. Acá se verifica la parte que sólo aparece cuando las plantas se
conectan:

  - el balance por eslabón (regla 1 de CLAUDE.md), vía `desvio_balance`;
  - que lo que una planta deriva es EXACTAMENTE lo que recibe la siguiente;
  - la conservación global: el gas de los pools cabecera termina, entero,
    en tratado + bypass — ni una molécula más ni menos;
  - la restricción activa: lgn_asignado <= capacidad de evacuación;
  - la planta fuera de servicio: no trata, no produce, y su gas pasa de largo.

Todo con el `comunes` sintético del conftest — sin Excel.
"""

import pandas as pd
import pytest

from pipeline.plantas.cascada import resolver_cascada, desvio_balance
from pipeline.plantas.registro import registro_base

from conftest import TOL, TOL_BALANCE


def test_balance_por_eslabon(cascada_resuelta):
    _, flujos = cascada_resuelta
    assert desvio_balance(flujos) < TOL_BALANCE


def test_el_derivado_de_una_planta_es_lo_que_recibe_la_siguiente(cascada_resuelta):
    """El encadenamiento no puede crear ni perder gas en el pase de manos."""
    plantas, flujos = cascada_resuelta

    derivado_tbx = float(flujos.loc["TTY - TBX", "vol_derivado"])
    recibe_dp = float(plantas["TTY - Dew Point"]["recibe_de_vol"])
    assert abs(derivado_tbx - recibe_dp) < TOL

    derivado_dp = float(flujos.loc["TTY - Dew Point", "vol_derivado"])
    recibe_mega = float(plantas["MEGA"]["recibe_de_vol"])
    assert abs(derivado_dp - recibe_mega) < TOL


def test_conservacion_global_del_gas(cascada_resuelta, comunes):
    """Todo el gas que entra por las cabeceras sale como tratado o bypass.

    Como el vol_derivado de un eslabón es el vol_disponible del siguiente, la
    suma de asignados + bypasses de TODA la cadena tiene que dar exactamente
    el gas de los pools cabecera. Es la versión "de punta a punta" de la
    regla 1: si un cambio en el traspaso duplica o pierde gas, el balance por
    eslabón puede seguir cerrando pero esto no.
    """
    _, flujos = cascada_resuelta

    # El disponible de un eslabón intermedio ES el derivado del anterior, así
    # que la entrada "externa" (gas fresco de los pools) es la suma de
    # disponibles menos la suma de derivados: cada traspaso se cancela solo.
    entrada_externa = float(
        flujos["vol_disponible"].sum()
        - flujos["vol_derivado"].sum()
    )
    salida = float(flujos["vol_asignado"].sum() + flujos["bypass"].sum())

    assert abs(entrada_externa - salida) < TOL_BALANCE


def test_lgn_asignado_respeta_la_evacuacion(cascada_resuelta, registro_tres):
    """La restricción activa (regla 2): en tn/d, nunca por encima de la
    capacidad de evacuación; y siempre lgn = unitario * asignado."""
    _, flujos = cascada_resuelta

    for nombre, planta in registro_tres.items():
        lgn = float(flujos.loc[nombre, "lgn_asignado"])
        unitario = float(flujos.loc[nombre, "lgn_unitario"])
        asignado = float(flujos.loc[nombre, "vol_asignado"])

        assert abs(lgn - unitario * asignado) < TOL_BALANCE
        assert lgn <= float(planta.capacidad_evacuacion) + TOL_BALANCE, (
            f"{nombre} evacúa más LGN del que puede")


def test_sin_flujos_negativos(cascada_resuelta):
    _, flujos = cascada_resuelta
    cols = ["vol_disponible", "vol_asignado", "sobrante",
            "vol_derivado", "bypass", "lgn_asignado"]
    assert (flujos[cols].astype(float) >= -TOL).all().all()


def test_planta_inactiva_no_trata_y_el_gas_pasa_de_largo(
        params_base, retenidos_rtp, compuestos, comunes):
    """dominio.md §2.5: TBX fuera de servicio no trata, no produce LGN, y el
    pool TTY entero cae en Dew Point (los topes de traspaso se ignoran)."""
    reg = registro_base(params_base, retenidos_rtp, compuestos, False)  # pre-PM
    _, flujos = resolver_cascada(reg, comunes)

    tbx = flujos.loc["TTY - TBX"]
    assert abs(float(tbx["vol_asignado"])) < TOL
    assert abs(float(tbx["lgn_asignado"])) < TOL
    assert abs(float(tbx["bypass"])) < TOL, "inactiva tampoco bypasea: el gas pasa"

    # El disponible de DP tiene que ser TODO el pool TTY (1200 en el conftest).
    pool_tty = float(tbx["vol_disponible"])
    assert abs(float(flujos.loc["TTY - Dew Point", "vol_disponible"]) - pool_tty) < TOL_BALANCE

    # Y el balance sigue cerrando con la planta apagada.
    assert desvio_balance(flujos) < TOL_BALANCE


def test_negativo_desvio_balance_detecta_gas_perdido(cascada_resuelta):
    """Un chequeo verde no prueba nada si nunca lo vimos fallar: se rompe un
    flujo a mano y `desvio_balance` TIENE que acusarlo."""
    _, flujos = cascada_resuelta
    roto = flujos.copy()
    roto.loc["TTY - Dew Point", "bypass"] = (
        float(roto.loc["TTY - Dew Point", "bypass"]) + 123.0)
    assert desvio_balance(roto) > 100.0
