"""
Las dos garantías estructurales del sandbox.
============================================

Ninguna necesita runtime de Streamlit: son funciones que se pueden llamar
directo. Pero protegen las dos cosas que, si se rompen, rompen la confianza en
todo el tablero.

1. AISLAMIENTO — el sandbox NO puede tocar las tablas de producción.
   `tab_plantas.py` lo dice así: *"Esa es la linea que separa a un sandbox de
   un cambio."* Si `_comunes_con_ductos` modificara en el lugar, el resto del
   tablero pasaría a mostrar números del escenario sin que nadie lo pidiera, y
   nadie se daría cuenta porque no hay error: los números simplemente serían
   otros.

2. ESCENARIOS — round-trip completo. Un escenario que se guarda y se vuelve a
   cargar tiene que dar la misma cascada. Si no, el usuario no puede confiar en
   lo que baja.

3. RESET — `sandbox_estado` tiene que conocer TODAS las claves. Es una lista a
   mano, y una lista a mano se desactualiza. El test la compara contra las
   constantes reales de los módulos.
"""

import json

import pandas as pd
import pytest


# ===========================================================================
# 1. AISLAMIENTO
# ===========================================================================

def test_sin_intervenciones_no_se_copia_de_gusto(comunes):
    """Sin ductos que aplicar, `comunes` se pasa tal cual: copiar tablas
    grandes en cada rerun por las dudas es caro y no aporta nada."""
    from ui.tab_plantas import _comunes_con_ductos

    efectivo, informe = _comunes_con_ductos(comunes, [], comunes["COMPUESTOS"])
    assert efectivo is comunes
    assert informe is None


def test_las_tablas_de_produccion_no_se_tocan(comunes):
    """LA garantía del sandbox. Si esto falla, el tablero oficial empieza a
    mostrar los números del escenario en silencio."""
    pytest.importorskip("pipeline.gasoductos.intervenciones")
    from pipeline.gasoductos.intervenciones import Intervencion
    from ui.tab_plantas import _comunes_con_ductos

    yac_antes = comunes["tabla_total_yacimientos"].copy(deep=True)
    fdi_antes = comunes["tabla_total_flujos_directos"].copy(deep=True)

    interv = [Intervencion("alta", "GNuevo", area_origen="Chivo",
                           planta_destino="TTY", volumen=250.0)]
    efectivo, _ = _comunes_con_ductos(comunes, interv, comunes["COMPUESTOS"])

    assert efectivo is not comunes, "tiene que devolver una copia"

    pd.testing.assert_frame_equal(comunes["tabla_total_yacimientos"], yac_antes)
    pd.testing.assert_frame_equal(comunes["tabla_total_flujos_directos"], fdi_antes)

    # Y la copia SÍ cambió: si no, no se aplicó nada.
    assert "GNuevo" in set(efectivo["tabla_total_yacimientos"]["Gasoducto"])


def test_la_cascada_oficial_no_cambia_por_correr_el_sandbox(
        registro_tres, comunes):
    """Resolver la cascada dos veces sobre el mismo `comunes` da lo mismo.

    Suena obvio, pero sólo se cumple si `resolver_cascada` no deja estado ni
    muta sus entradas. Un `fillna` in-place mal puesto rompe esto.
    """
    from pipeline.plantas.cascada import resolver_cascada
    from pipeline.plantas.registro import registro_base

    _, primera = resolver_cascada(registro_tres, comunes)

    reg2 = registro_base(
        {"CAPACIDAD_EVACUACION_TTY_TBX": 0.9, "CAPACIDAD_EVACUACION_TTY_DP": 0.4,
         "CAPACIDAD_EVACUACION_MEGA": 0.5, "CAPACIDAD_TTY_TBX": 34000,
         "CAPACIDAD_TTY_DP": 28000, "CAPACIDAD_MEGA": 43000,
         "MAX_DERIVACION_TTY_DP_A_MEGA": 5000,
         "MAX_DERIVACION_TTY_TBX_A_TTY_DP": 14800},
        pd.DataFrame([{"Planta": p, **{c: v for c in comunes["COMPUESTOS"]}}
                      for p, v in [("TBX", .5), ("Dew point", .3), ("TBX MEGA", .7)]]),
        comunes["COMPUESTOS"], True)
    _, segunda = resolver_cascada(reg2, comunes)

    pd.testing.assert_frame_equal(
        primera.astype(float, errors="ignore"),
        segunda.astype(float, errors="ignore"))


# ===========================================================================
# 2. ESCENARIOS
# ===========================================================================

def test_round_trip_escenario_da_la_misma_cascada(registro_tres, comunes):
    """Guardar y volver a cargar tiene que reproducir el resultado exacto."""
    from ui.escenarios import serializar, partir
    from ui.plantas_editor import aplicar_escenario
    from pipeline.plantas.cascada import resolver_cascada

    _, original = resolver_cascada(registro_tres, comunes)

    texto = serializar(registro_tres, [])
    plantas_json, _ = partir(json.loads(texto))

    recargado = {}
    aplicar_escenario(recargado, plantas_json)
    _, vuelta = resolver_cascada(recargado, comunes)

    pd.testing.assert_frame_equal(
        original.astype(float, errors="ignore"),
        vuelta.astype(float, errors="ignore"))


def test_aplicar_escenario_hace_merge_no_reemplazo(registro_tres, compuestos):
    """Un escenario con UNA planta no puede llevarse puestas las tres base."""
    from ui.plantas_editor import aplicar_escenario
    from conftest import planta_dict

    antes = set(registro_tres)
    nueva = planta_dict("Tren Nuevo", pool="TTY", cap_evac=500.0,
                        compuestos=compuestos, cabecera=False)

    nuevas, parcheadas = aplicar_escenario(registro_tres, [nueva])

    assert nuevas == 1
    assert set(registro_tres) == antes | {"Tren Nuevo"}


def test_parche_solo_conexiones_no_toca_capacidades(registro_tres):
    """`solo_conexiones: true` engancha una planta a la cascada sin congelar
    las capacidades de las base con las de otra corrida."""
    from ui.plantas_editor import aplicar_escenario

    cap_antes = registro_tres["TTY - Dew Point"].capacidad_evacuacion

    aplicar_escenario(registro_tres, [{
        "nombre": "TTY - Dew Point",
        "solo_conexiones": True,
        "deriva": True,
        "conexiones": [{"destino": "MEGA", "proporcion": 1.0,
                        "tope": None, "comparte_pool": False}],
    }])

    assert registro_tres["TTY - Dew Point"].capacidad_evacuacion == cap_antes
    assert len(registro_tres["TTY - Dew Point"].conexiones) == 1


def test_escenario_malformado_falla_explicito():
    """Un escenario que se lee A MEDIAS es peor que uno que no se lee: deja el
    sandbox en un estado que nadie pidió."""
    from ui.escenarios import partir

    for malo in ("texto", 42, {"plantas": "no-lista"}, None):
        with pytest.raises(ValueError):
            partir(malo)


def test_formato_viejo_de_escenario_sigue_funcionando():
    from ui.escenarios import partir
    plantas, ductos = partir([{"nombre": "MEGA"}])
    assert len(plantas) == 1 and ductos == []


# ===========================================================================
# 3. RESET
# ===========================================================================

def test_el_reset_conoce_todas_las_claves_de_datos():
    """`CLAVES_DATOS` es una lista a mano y las listas a mano se desactualizan.

    Se compara contra las constantes que declaran los módulos: si alguien
    agrega una CLAVE_* nueva en tab_plantas y se olvida de sumarla al reset, el
    sandbox queda a medias tras restablecer (registro nuevo, resultado viejo).
    """
    import ui.tab_plantas as tp
    from ui.sandbox_estado import CLAVES_DATOS

    declaradas = {
        valor for nombre, valor in vars(tp).items()
        if nombre.startswith("CLAVE_") and isinstance(valor, str)
    }

    # `sandbox_flujos_oficiales` está excluida a propósito: es cache de la
    # corrida OFICIAL, no algo que el usuario configuró.
    excluidas = {"sandbox_flujos_oficiales"}

    faltantes = declaradas - set(CLAVES_DATOS) - excluidas
    assert not faltantes, (
        f"estas claves de tab_plantas no se limpian al restablecer: {faltantes}. "
        "Agregalas a CLAVES_DATOS en ui/sandbox_estado.py")
