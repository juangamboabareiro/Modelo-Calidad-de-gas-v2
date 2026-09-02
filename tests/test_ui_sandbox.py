"""
Las garantías estructurales del sandbox.
========================================

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

4. CORRECCIÓN 1b POR PLANTA — el bloque de la sidebar existe además por planta
   del sandbox, y eso abre tres formas de perder lo que el usuario configuró:
   que no viaje en el escenario, que se caiga en la serie mes a mes, o que el
   reset se lleve puestas las reglas de la corrida OFICIAL por compartir
   prefijo de clave. Una por test.

   El test de física de esa sección vive acá por ahora porque no hay
   `test_correccion.py`; si algún día se crea, va para allá.
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


def test_el_reset_conoce_las_claves_de_plantas_editor():
    """Lo mismo que el test de arriba, pero para el editor.

    `plantas_editor` declara cuatro claves de estado (el registro, el buffer de
    cromatografías, el flash y el espejo del bloque 1b). Cualquiera que no esté
    en `CLAVES_DATOS` sobrevive al reset y deja el sandbox a medias.
    """
    import ui.plantas_editor as pe
    from ui.sandbox_estado import CLAVES_DATOS

    declaradas = {
        valor for nombre, valor in vars(pe).items()
        if nombre.startswith("CLAVE") and isinstance(valor, str)
    }

    faltantes = declaradas - set(CLAVES_DATOS)
    assert not faltantes, (
        f"estas claves de plantas_editor no se limpian al restablecer: "
        f"{faltantes}. Agregalas a CLAVES_DATOS en ui/sandbox_estado.py")


def test_las_claves_de_arranque_no_encienden_el_boton_de_reset():
    """`hay_algo_que_restablecer` ignora las claves que existen desde que el
    sandbox se abre. Si el espejo del bloque 1b no estuviera en esa lista, el
    botón quedaría encendido SIEMPRE —el espejo se escribe en el primer
    dibujado— y dejaría de significar "tocaste algo".

    Antes esto era un slice posicional (`CLAVES_DATOS[2:]`): agregar una clave
    arriba en la tupla lo rompía en silencio. De ahí el test.
    """
    from ui.plantas_editor import CLAVE_CORR_ESPEJO
    from ui.sandbox_estado import CLAVES_DATOS, CLAVES_DE_ARRANQUE

    assert set(CLAVES_DE_ARRANQUE) <= set(CLAVES_DATOS), (
        "una clave de arranque que no esté en CLAVES_DATOS no se borra nunca")
    assert CLAVE_CORR_ESPEJO in CLAVES_DE_ARRANQUE, (
        "el espejo de la corrección existe desde el primer rerun: si cuenta "
        "como 'algo que restablecer', el botón nunca se apaga")


# ===========================================================================
# 4. CORRECCIÓN 1b POR PLANTA
# ===========================================================================

REGLAS_TOPE = {
    "aplicar": True,
    "tope": 150.0,
    "solo_si_excede": False,
    "cortes": {"gasolina": "pasa", "butanos": 1, "propano": 2},
}


def _planta_con_reglas(compuestos, cap_evac, reglas, nombre="Tren Nuevo"):
    """Una planta AGREGADA (`es_base=False`) sobre el pool TTY, con reglas 1b.

    `planta_dict` del conftest no conoce `correccion` a propósito: es el formato
    de los escenarios y no hay por qué congelarlo desde acá. La clave se agrega
    a mano, que es exactamente lo que hace un escenario guardado —
    `PlantaConfig.desde_dict` la lee con `.get`.
    """
    from pipeline.plantas.registro import PlantaConfig
    from conftest import planta_dict

    d = planta_dict(nombre, pool="TTY", cap_evac=cap_evac,
                    compuestos=compuestos, retencion=0.5,
                    deriva=False, cabecera=True)
    d["correccion"] = reglas
    return {nombre: PlantaConfig.desde_dict(d)}


def test_una_planta_agregada_puede_tener_correccion_y_trata_mas_gas(
        compuestos, comunes):
    """EL test de la feature: hasta ahora la corrección sólo se podía
    configurar para las tres base y desde la sidebar.

    Es la física de `dominio.md` §2.2 leída al revés: bajar la recuperación
    baja el `lgn_unitario`, y con la evacuación fija eso sube el `vol_maximo`.
    La planta acepta MÁS gas a costa de recuperar MENOS líquido — que es el
    sentido entero de la corrección.

    Nada de números mágicos: la capacidad se calibra contra el LGN que da el
    pool sintético, así el test sobrevive a un cambio del conftest.
    """
    from pipeline.plantas.cascada import resolver_cascada, desvio_balance
    from pipeline.plantas.correccion import REGLAS_LEGACY, copiar_reglas

    from conftest import TOL_BALANCE

    SIN_LIMITE = 1.0e12

    # 1. Calibración: cuánto LGN produce el pool entero sin restricción.
    _, holgada = resolver_cascada(
        _planta_con_reglas(compuestos, SIN_LIMITE, None), comunes)
    lgn_pool = float(holgada.loc["Tren Nuevo", "lgn_asignado"])
    assert lgn_pool > 0, "el escenario necesita retención real para tener sentido"

    # 2. Una evacuación que la satura: la mitad del LGN del pool.
    cap = lgn_pool / 2.0

    _, sin_corr = resolver_cascada(
        _planta_con_reglas(compuestos, cap, None), comunes)

    reglas = copiar_reglas(REGLAS_LEGACY)
    reglas["aplicar"] = True
    _, con_corr = resolver_cascada(
        _planta_con_reglas(compuestos, cap, reglas), comunes)

    disponible = float(sin_corr.loc["Tren Nuevo", "vol_disponible"])
    asignado_sin = float(sin_corr.loc["Tren Nuevo", "vol_asignado"])
    asignado_con = float(con_corr.loc["Tren Nuevo", "vol_asignado"])

    assert asignado_sin < disponible - TOL_BALANCE, (
        "la planta tiene que quedar saturada sin corrección, si no el test no "
        "prueba nada")
    assert asignado_con > asignado_sin, (
        f"con la corrección prendida la planta debería tratar más gas: "
        f"{asignado_con:,.1f} vs {asignado_sin:,.1f}. Si son iguales, "
        "`modelar_planta` no está leyendo `planta.correccion`.")

    # Y las dos reglas que no se negocian siguen valiendo en ambos casos.
    for etiqueta, flujos in (("sin", sin_corr), ("con", con_corr)):
        assert desvio_balance(flujos) < TOL_BALANCE, f"balance roto {etiqueta}"
        assert float(flujos.loc["Tren Nuevo", "lgn_asignado"]) <= cap + TOL_BALANCE, (
            f"{etiqueta} corrección: evacúa más LGN del que puede")


def test_las_reglas_1b_viajan_en_el_escenario(registro_tres, compuestos):
    """Configurar la corrección son varias interacciones: si no se guarda con
    el escenario, se pierde al recargar la página."""
    from ui.escenarios import serializar, partir
    from ui.plantas_editor import aplicar_escenario

    registro_tres["MEGA"].correccion = REGLAS_TOPE
    registro_tres.update(_planta_con_reglas(compuestos, 500.0, REGLAS_TOPE))

    plantas_json, _ = partir(json.loads(serializar(registro_tres, [])))
    vuelta = {}
    aplicar_escenario(vuelta, plantas_json)

    assert vuelta["MEGA"].correccion == REGLAS_TOPE
    assert vuelta["Tren Nuevo"].correccion == REGLAS_TOPE


def test_reglas_vacias_no_cuentan_como_cambio(compuestos):
    """`_corr_efectiva` es lo que protege el control del sandbox.

    Abrir el bloque y no cargar nada devuelve un dict apagado con
    `cortes: {}`. Si eso se escribiera en el registro, el diff de la serie lo
    leería como un cambio del usuario y lo propagaría como override a los 24
    meses — sin cambiar un número, pero rompiendo la propiedad de que una base
    sin tocar hereda los parámetros de cada mes.
    """
    from ui.plantas_editor import _corr_efectiva

    apagadas = {"aplicar": False, "tope": 0.0, "solo_si_excede": True,
                "cortes": {}}
    assert _corr_efectiva(apagadas) is None
    assert _corr_efectiva(None) is None
    assert _corr_efectiva({"aplicar": True, "tope": 300.0, "cortes": {}}) is None, (
        "un tope sin cortes no corrige nada: no es un cambio")

    assert _corr_efectiva(REGLAS_TOPE) == REGLAS_TOPE


def test_la_serie_del_escenario_respeta_la_correccion_tocada(
        registro_tres, params_base, retenidos_rtp, compuestos):
    """Sin el campo en el diff, la regla editada en el sandbox se pierde y no
    salta ningún error: cada mes re-siembra las base y aplica sólo el diff."""
    from pipeline.plantas.registro import registro_base
    from pipeline.plantas.serie_escenario import (
        diff_contra_semilla, registro_para_periodo)

    semilla = registro_base(params_base, retenidos_rtp, compuestos, True)
    registro_tres["MEGA"].correccion = REGLAS_TOPE

    overrides, extras = diff_contra_semilla(registro_tres, semilla)
    assert "correccion" in overrides.get("MEGA", {}), (
        "la corrección tocada tiene que entrar al diff, o la serie del "
        "escenario corre sin ella. Ver _CAMPOS_ESCALARES en serie_escenario.py")

    uno = registro_para_periodo(params_base, retenidos_rtp, compuestos, True,
                                overrides, extras)
    otro = registro_para_periodo(params_base, retenidos_rtp, compuestos, True,
                                 overrides, extras)

    assert uno["MEGA"].correccion["tope"] == REGLAS_TOPE["tope"]
    assert uno["MEGA"].correccion is not otro["MEGA"].correccion, (
        "cada mes necesita su propia copia de las reglas: un dict compartido "
        "entre 24 meses es el mismo bug que un registro compartido")


def test_apagar_la_correccion_en_el_sandbox_tambien_es_un_cambio(
        params_base, retenidos_rtp, compuestos):
    """El caso inverso, que un diff mal hecho se come: la sidebar TIENE reglas
    y el usuario las apaga en el sandbox. La serie no puede re-heredarlas mes a
    mes."""
    from pipeline.plantas.registro import registro_base
    from pipeline.plantas.serie_escenario import (
        diff_contra_semilla, registro_para_periodo)

    params = dict(params_base, CORRECCION_MEGA=REGLAS_TOPE)
    semilla = registro_base(params, retenidos_rtp, compuestos, True)
    registro = registro_base(params, retenidos_rtp, compuestos, True)
    registro["MEGA"].correccion = None

    overrides, extras = diff_contra_semilla(registro, semilla)
    assert overrides["MEGA"]["correccion"] is None

    mes = registro_para_periodo(params, retenidos_rtp, compuestos, True,
                                overrides, extras)
    assert mes["MEGA"].correccion is None, (
        "apagar la corrección tiene que sobrevivir a la re-siembra del mes")


def test_un_registro_sin_tocar_no_genera_override_de_correccion(
        registro_tres, params_base, retenidos_rtp, compuestos):
    """El control 'sandbox intacto == oficial' no se puede romper por 1b.

    `None` (la sidebar sin reglas) y unas reglas apagadas describen lo mismo, y
    `copiar_reglas` normaliza los dos lados para que comparen igual.
    """
    from pipeline.plantas.registro import registro_base
    from pipeline.plantas.serie_escenario import diff_contra_semilla

    semilla = registro_base(params_base, retenidos_rtp, compuestos, True)
    overrides, _ = diff_contra_semilla(registro_tres, semilla)

    assert all("correccion" not in cambios for cambios in overrides.values()), (
        f"una base sin tocar no debería aparecer en el diff: {overrides}")


def test_el_reset_del_sandbox_no_barre_la_correccion_de_la_sidebar():
    """Las reglas de la sidebar (`corr_tbx` / `corr_dp` / `corr_mega`) son de
    la corrida OFICIAL. Con el prefijo `corr_` a secas, apretar "Restablecer el
    sandbox" cambiaría los números del tablero."""
    from ui.sandbox_estado import PREFIJOS_WIDGETS

    assert any(p.startswith("corr_sbx") for p in PREFIJOS_WIDGETS), (
        "los widgets del bloque 1b del sandbox tienen que barrerse en el reset")

    de_la_sidebar = ("corr_tbx", "corr_dp", "corr_mega",
                     "corr_tbx_ed", "corr_mega_tope", "corr_dp_solo")
    colisiones = [c for c in de_la_sidebar if c.startswith(PREFIJOS_WIDGETS)]
    assert not colisiones, (
        f"el reset del sandbox se lleva puestas claves de la sidebar: "
        f"{colisiones}. El prefijo tiene que ser `corr_sbx`, no `corr_`.")
