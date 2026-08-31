# -*- coding: utf-8 -*-
"""
Editor amigable de la correccion de ingreso por llenar evacuacion.
==================================================================

Destino: ui/correccion_editor.py

Un solo bloque, `bloque_correccion`, que se reusa en:

  - la sidebar de app.py (una vez por planta: TTY-TBX, TTY-DP, MEGA), y
  - el editor de plantas del sandbox (ui/plantas_editor.py).

El flujo para el usuario:

  1. Escribe el mecanismo con sus palabras ("la gasolina pasa 100%, no se
     trata etano, hasta 200 tn/d primero butanos y despues propano").
  2. Aprieta "Interpretar": el parser llena la tabla estructurada.
  3. Lee la traduccion de vuelta ("Con esta correccion: ...") y, si algo no
     coincide con lo que quiso decir, lo corrige a mano en la tabla.

IMPORTANTE: NO meter este bloque adentro de un `st.form`. El boton
"Interpretar" necesita su propio rerun y adentro de un form los botones
comunes no existen (solo `form_submit_button`). En app.py va ANTES del form.

Las reglas viven en `st.session_state["corr_<key>"]` (dict JSON-friendly,
ver pipeline/plantas/correccion.py) y la funcion ademas las devuelve.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pipeline.plantas.correccion import (
    CORTES, MODO_LIBRE, MODO_PASA, REGLAS_LEGACY,
    copiar_reglas, describir_reglas, parsear_reglas, reglas_vacias,
)

# Etiquetas visibles <-> modos internos.
_ETIQUETAS = {
    MODO_LIBRE: "Sin correccion",
    MODO_PASA: "Pasa 100%",
    "tope": "Entra al tope",
}
_MODOS = {v: k for k, v in _ETIQUETAS.items()}

_PLACEHOLDER = (
    "Ej: la gasolina pasa 100%, no se trata etano, y hasta 200 tn/d se "
    "llena primero con butanos y despues con propano"
)

# Widgets cuyo estado hay que resetear cuando el parser (o el boton de reglas
# clasicas) pisa las reglas: si no, Streamlit conserva el valor viejo del
# widget y el usuario no ve lo que se acaba de interpretar.
_SUFIJOS_WIDGETS = ("_on", "_ed", "_tope", "_solo")


def _clave(key: str) -> str:
    return f"corr_{key}"


def _resetear_widgets(clave: str) -> None:
    for sufijo in _SUFIJOS_WIDGETS:
        st.session_state.pop(clave + sufijo, None)


def obtener_reglas(key: str) -> dict:
    """Para leer las reglas desde afuera (armado de params) sin redibujar."""
    return copiar_reglas(st.session_state.get(_clave(key)))


def bloque_correccion(nombre_planta: str, key: str,
                      reglas_iniciales: dict | None = None,
                      expandido: bool = False, rerun=None) -> dict:
    """Dibuja el editor y devuelve las reglas vigentes (dict).

    rerun : callable | None
        Como rerunear despues de "Interpretar" / "Reglas clasicas". None =
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

        st.caption(
            "Cuando el LGN del pool no entra en la evacuacion, en vez de "
            "rechazar gas la planta **baja la recuperacion** segun estas "
            "reglas: que corte pasa de largo, y con que orden se llena el "
            "tope de tn/d.")

        # ---------- 1) texto libre + interpretar --------------------------
        texto = st.text_area(
            "Explica el mecanismo con tus palabras",
            key=f"{clave}_txt", placeholder=_PLACEHOLDER, height=80)

        col_a, col_b = st.columns(2)

        if col_a.button("✨ Interpretar", key=f"{clave}_btn",
                        use_container_width=True):
            nuevas, avisos = parsear_reglas(texto)
            st.session_state[clave] = nuevas
            st.session_state[f"{clave}_avisos"] = avisos
            _resetear_widgets(clave)
            rerun()

        if col_b.button("Reglas clasicas", key=f"{clave}_leg",
                        use_container_width=True,
                        help="Las que estaban hardcodeadas: gasolina pasa "
                             "100%, etano no se trata, el tope se llena "
                             "primero con butanos y despues con propano."):
            legacy = copiar_reglas(REGLAS_LEGACY)
            legacy["aplicar"] = True
            st.session_state[clave] = legacy
            _resetear_widgets(clave)
            rerun()

        for aviso in st.session_state.pop(f"{clave}_avisos", []):
            st.warning(aviso)

        reglas = st.session_state[clave]

        # ---------- 2) editor estructurado (la verdad esta aca) -----------
        reglas["aplicar"] = st.checkbox(
            "Aplicar esta correccion", key=f"{clave}_on",
            value=bool(reglas.get("aplicar")))

        filas = []
        for corte in CORTES:
            modo = reglas.get("cortes", {}).get(corte, MODO_LIBRE)
            es_tope = isinstance(modo, int)
            filas.append({
                "Corte": corte,
                "Modo": _ETIQUETAS["tope"] if es_tope else _ETIQUETAS[modo],
                "Prioridad": int(modo) if es_tope else None,
            })

        editado = st.data_editor(
            pd.DataFrame(filas), hide_index=True, use_container_width=True,
            key=f"{clave}_ed",
            column_config={
                "Corte": st.column_config.TextColumn(disabled=True),
                "Modo": st.column_config.SelectboxColumn(
                    options=list(_MODOS), required=True,
                    help="Pasa 100% = retencion en cero. Entra al tope = "
                         "compite por los tn/d del tope segun su prioridad."),
                "Prioridad": st.column_config.NumberColumn(
                    min_value=1, step=1,
                    help="Solo cuenta para los cortes que entran al tope: "
                         "1 llena primero."),
            })

        cortes = {}
        prioridad_relleno = 90   # sin prioridad cargada -> al final, estable
        for _, fila in editado.iterrows():
            modo = _MODOS.get(fila["Modo"], MODO_LIBRE)
            if modo == "tope":
                prio = fila["Prioridad"]
                if pd.isna(prio):
                    prioridad_relleno += 1
                    prio = prioridad_relleno
                cortes[fila["Corte"]] = int(prio)
            elif modo == MODO_PASA:
                cortes[fila["Corte"]] = MODO_PASA
        reglas["cortes"] = cortes

        col_c, col_d = st.columns(2)
        reglas["tope"] = col_c.number_input(
            "Tope [tn/d]", key=f"{clave}_tope",
            min_value=0.0, step=50.0, value=float(reglas.get("tope") or 0.0),
            help="0 = usar la capacidad de evacuacion de la planta "
                 "(con las ampliaciones vigentes al periodo).")
        reglas["solo_si_excede"] = col_d.checkbox(
            "Solo si el LGN excede el tope", key=f"{clave}_solo",
            value=bool(reglas.get("solo_si_excede", True)),
            help="Destildado, la correccion se aplica siempre (por ejemplo "
                 "para forzar que la gasolina pase 100% aunque sobre "
                 "evacuacion).")

        # ---------- 3) el espejo: que entendio la app ----------------------
        st.info("📖 " + describir_reglas(reglas))

    st.session_state[clave] = reglas
    return copiar_reglas(reglas)
