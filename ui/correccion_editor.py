# -*- coding: utf-8 -*-
"""
Editor de la correccion de ingreso por llenar evacuacion.
=========================================================

Destino: ui/correccion_editor.py

Un solo bloque, `bloque_correccion`, que se reusa en la sidebar de app.py
(una vez por planta) y en el editor de plantas del sandbox.

Tres maneras de fijar el LGN de un corte, elegidas por fila en la tabla:

  1. POR PORCENTAJE — se retiene el X% del corte, pisando el RTP.
     0% = pasa todo sin tratarse.
  2. POR NUMERO — se retienen X tn/d fijas de ese corte (o todo lo que
     produzca, si X supera lo disponible).
  3. LLENAR EL TOPE EN ORDEN — los cortes marcados compiten por un tope
     compartido de tn/d y lo llenan segun su orden (1 primero); lo que no
     entra en el tope no se retiene.

Un corte sin regla conserva su retencion original del RTP.

Las reglas viven en `st.session_state["corr_<key>"]` (dict JSON-friendly,
ver pipeline/plantas/correccion.py) y la funcion ademas las devuelve.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pipeline.plantas.correccion import (
    CORTES, MODO_LIBRE, MODO_PASA, REGLAS_LEGACY,
    copiar_reglas, describir_reglas, es_porcentaje, es_tn, reglas_vacias,
)

# Etiquetas visibles <-> modos internos.
_ETIQUETAS = {
    MODO_LIBRE: "Sin correccion",
    "porcentaje": "Por porcentaje [%]",
    "tn": "Por numero [tn/d]",
    "tope": "Llenar el tope (en orden)",
}
_MODOS = {v: k for k, v in _ETIQUETAS.items()}

_EXPLICATIVO = (
    "Tres maneras de fijar el LGN de un corte — un corte sin regla conserva "
    "su retención del RTP:\n"
    "- **Por porcentaje**: se retiene el X% del corte (0% = pasa todo sin "
    "tratarse).\n"
    "- **Por número**: se retienen X tn/d fijas de ese corte.\n"
    "- **Llenar el tope (en orden)**: los cortes marcados comparten un tope "
    "de tn/d y lo llenan según su orden (1 primero); lo que no entra, no se "
    "retiene."
)

# Widgets cuyo estado hay que resetear cuando un boton pisa las reglas: si
# no, Streamlit conserva el valor viejo del widget y el usuario no ve el
# cambio que acaba de pedir.
_SUFIJOS_WIDGETS = ("_on", "_ed", "_tope", "_solo")


def _clave(key: str) -> str:
    return f"corr_{key}"


def _resetear_widgets(clave: str) -> None:
    for sufijo in _SUFIJOS_WIDGETS:
        st.session_state.pop(clave + sufijo, None)


def obtener_reglas(key: str) -> dict:
    """Para leer las reglas desde afuera (armado de params) sin redibujar."""
    return copiar_reglas(st.session_state.get(_clave(key)))


def _fila_de(corte: str, modo) -> dict:
    """Modo interno -> fila de la tabla (etiqueta + valor)."""
    if isinstance(modo, int):
        return {"Corte": corte, "Modo": _ETIQUETAS["tope"], "Valor": float(modo)}
    if es_porcentaje(modo):
        return {"Corte": corte, "Modo": _ETIQUETAS["porcentaje"],
                "Valor": float(modo["porcentaje"])}
    if es_tn(modo):
        return {"Corte": corte, "Modo": _ETIQUETAS["tn"], "Valor": float(modo["tn"])}
    if modo == MODO_PASA:
        # "pasa" es el caso limite de porcentaje 0: se muestra asi de simple.
        return {"Corte": corte, "Modo": _ETIQUETAS["porcentaje"], "Valor": 0.0}
    return {"Corte": corte, "Modo": _ETIQUETAS[MODO_LIBRE], "Valor": None}


def _modo_de(fila, prioridad_relleno: list) -> object | None:
    """Fila de la tabla -> modo interno. None = sin correccion / incompleta."""
    modo = _MODOS.get(fila["Modo"], MODO_LIBRE)
    valor = fila["Valor"]

    if modo == MODO_LIBRE:
        return None

    if modo == "tope":
        if pd.isna(valor):
            prioridad_relleno[0] += 1     # sin orden cargado -> al final
            return prioridad_relleno[0]
        return max(1, int(valor))

    if pd.isna(valor):
        return None                        # % o tn/d sin numero: incompleta

    if modo == "porcentaje":
        pct = max(0.0, min(100.0, float(valor)))
        return MODO_PASA if pct <= 0 else {"porcentaje": pct}

    # modo == "tn"
    tn = float(valor)
    return MODO_PASA if tn <= 0 else {"tn": tn}


def bloque_correccion(nombre_planta: str, key: str,
                      reglas_iniciales: dict | None = None,
                      expandido: bool = False, rerun=None) -> dict:
    """Dibuja el editor y devuelve las reglas vigentes (dict).

    rerun : callable | None
        Como rerunear despues de un boton que pisa las reglas. None =
        `st.rerun()` a app entera. El sandbox pasa su `_rerun`, que respeta
        el scope del fragment y no redibuja los otros tabs.
    """
    if rerun is None:
        rerun = st.rerun

    clave = _clave(key)

    if clave not in st.session_state:
        st.session_state[clave] = (copiar_reglas(reglas_iniciales)
                                   if reglas_iniciales else reglas_vacias())

    with st.expander(
            f"Correccion de ingreso por llenar evacuacion — {nombre_planta}",
            expanded=expandido):

        st.markdown(_EXPLICATIVO)

        reglas = st.session_state[clave]

        reglas["aplicar"] = st.checkbox(
            "Aplicar esta correccion", key=f"{clave}_on",
            value=bool(reglas.get("aplicar")))

        filas = [_fila_de(c, reglas.get("cortes", {}).get(c, MODO_LIBRE))
                 for c in CORTES]

        editado = st.data_editor(
            pd.DataFrame(filas), hide_index=True, use_container_width=True,
            key=f"{clave}_ed",
            column_config={
                "Corte": st.column_config.TextColumn(disabled=True),
                "Modo": st.column_config.SelectboxColumn(
                    options=list(_MODOS), required=True),
                "Valor": st.column_config.NumberColumn(
                    min_value=0.0, step=1.0,
                    help="Segun el modo: el % retenido (0 = pasa todo), las "
                         "tn/d fijas, o el orden con el que llena el tope "
                         "(1 primero)."),
            })

        prioridad_relleno = [90]   # lista para mutar desde _modo_de
        cortes, incompletos = {}, []
        for _, fila in editado.iterrows():
            modo = _modo_de(fila, prioridad_relleno)
            if modo is not None:
                cortes[fila["Corte"]] = modo
            elif _MODOS.get(fila["Modo"], MODO_LIBRE) != MODO_LIBRE:
                incompletos.append(fila["Corte"])
        reglas["cortes"] = cortes

        if incompletos:
            st.caption("✏️ Falta el **Valor** de: " + ", ".join(incompletos)
                       + " — hasta completarlo quedan sin correccion.")

        hay_tope = any(isinstance(m, int) for m in cortes.values())

        col_a, col_b = st.columns(2)
        reglas["tope"] = col_a.number_input(
            "Tope [tn/d]", key=f"{clave}_tope",
            min_value=0.0, step=50.0, value=float(reglas.get("tope") or 0.0),
            disabled=not hay_tope,
            help="Solo cuenta para «Llenar el tope (en orden)»: los tn/d que "
                 "se reparten entre esos cortes. 0 = usar la capacidad de "
                 "evacuacion de la planta (con ampliaciones incluidas).")
        reglas["solo_si_excede"] = col_b.checkbox(
            "Solo si el LGN excede el tope", key=f"{clave}_solo",
            value=bool(reglas.get("solo_si_excede", True)),
            help="Destildado, la correccion se aplica siempre. Con reglas por "
                 "porcentaje o por numero conviene destildarlo: describen "
                 "como opera la planta, no un mecanismo de desborde.")

        if col_b.button("Reglas clasicas", key=f"{clave}_leg",
                        use_container_width=True,
                        help="Las de siempre: gasolina y etano pasan (0%), y "
                             "el tope se llena primero con butanos y despues "
                             "con propano."):
            legacy = copiar_reglas(REGLAS_LEGACY)
            legacy["aplicar"] = True
            st.session_state[clave] = legacy
            _resetear_widgets(clave)
            rerun()

        # El espejo: que va a hacer el modelo con lo cargado.
        st.info("📖 " + describir_reglas(reglas))

    st.session_state[clave] = reglas
    return copiar_reglas(reglas)
