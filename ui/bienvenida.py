"""
La pantalla de bienvenida, antes de correr el pipeline.
=======================================================

Lo que ve alguien que abre el tablero y todavia no ejecuto nada. Antes era una
sola linea ("elegi los parametros y apreta Ejecutar"), que no alcanza para
alguien ajeno al proyecto: no sabe que es el pipeline, ni que va a ver despues,
ni en que unidades cargar las capacidades.

No lleva asistente embebido a proposito: esta pantalla tiene que decir una sola
cosa —como arrancar— y el asistente completo esta en su tab apenas hay corrida.
"""

from __future__ import annotations

import streamlit as st


def panel_bienvenida():
    """Guia de uso + el aviso del boton. No depende de que haya corrida."""

    st.info("Elegí los parámetros en la barra lateral y apretá "
            "**▶️ Ejecutar pipeline**.")

    # El aviso va ARRIBA de los pasos, no al final: es lo que hace que alguien
    # no abandone pensando que el tablero esta roto.
    st.warning(
        "**Si apretás Ejecutar y no pasa nada, volvé a apretarlo.** A veces "
        "hacen falta varios clicks hasta que terminan de cargar todos los "
        "procesos. No estás haciendo nada mal y no se duplica ningún cálculo: "
        "insistí hasta que aparezcan los tabs de resultados.")

    st.markdown("### Cómo usar el tablero")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(
            "**1. Cargá el Excel** *(opcional)*  \n"
            "Sidebar, sección 1. Sin archivo se usa el que está configurado "
            "por defecto; el nombre del que está en uso aparece abajo del "
            "cargador.\n\n"
            "**2. Completá los parámetros**  \n"
            "Período (`MM-YYYY`), fecha de parada de mantenimiento, "
            "ampliaciones, capacidades y topes de derivación.\n\n"
            "**3. Ejecutá**  \n"
            "Los parámetros están dentro de un formulario: **Enter no ejecuta "
            "nada**, sólo confirma el valor. Hay que apretar el botón.")

    with col_b:
        st.markdown(
            "**4. Mirá los resultados**  \n"
            "Resumen (reparto del gas), Cascada, Tablas totales, Mapa de la "
            "red y una pestaña por planta.\n\n"
            "**5. Serie temporal** *(opcional)*  \n"
            "Definí un rango de meses y corré la serie: es lo que alimenta el "
            "tab Graphs y el reporte PDF.\n\n"
            "**6. Escenarios** *(opcional)*  \n"
            "El tab *Plantas (sandbox)* responde \"¿qué pasa si…?\" sin tocar "
            "la corrida oficial.")

    st.error(
        "**El error más caro, y no da ningún mensaje: las unidades.** La "
        "capacidad de evacuación va en **tn/d** y la de ingreso en "
        "**MMm³/d**. Cargar `25` donde va `25000` no falla — devuelve números "
        "mal. Ante un resultado raro, revisá esto primero.")

    st.caption("Una vez que corras el pipeline, el tab **Asistente** tiene un "
               "glosario, un buscador sobre toda la documentación y una "
               "lectura automática de la corrida. Funciona sin conexión.")
