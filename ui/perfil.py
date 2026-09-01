"""
Cronómetro por tab: dónde se va el tiempo de un rerun.
======================================================

Streamlit renderiza el contenido de TODOS los tabs en cada rerun, mires el que
mires. O sea que el costo de un rerun es la suma de los diez, y cuando la app
"se siente lenta" no hay forma de saber cuál es el culpable mirándola.

Uso — envolver los `_render_seguro` de `app.py`:

    from ui.perfil import cronometrar, mostrar_perfil

    with cronometrar("Graphs"):
        _render_seguro("Graphs", panel_graphs, ...)

    with cronometrar("Asistente"):
        _render_seguro("Asistente", panel_asistente, ...)

    ...y al final del script:
    mostrar_perfil()

Se enciende con el secreto `PERFIL` o la variable de entorno `PERFIL=1`.
Apagado no cuesta nada: los context managers no miden y `mostrar_perfil` no
dibuja.

    # Local, PowerShell
    $env:PERFIL = "1"; streamlit run app.py

    # En Streamlit Community Cloud no se pueden setear variables de entorno:
    # va en los secretos de la app (Manage app -> Settings -> Secrets)
    PERFIL = true

EN LA NUBE, MIRÁ PRIMERO LA MEMORIA
-----------------------------------
Streamlit Community Cloud da del orden de 1 GB de RAM y CPU compartida, y
reinicia la app cuando se pasa. Un contenedor cerca del límite se pone lento de
una forma que NO se explica por el tiempo de render: la app se reinicia sola,
el websocket se reconecta, y desde afuera se ve como "hay que apretar el botón
varias veces".

Por eso el panel muestra la memoria del proceso además de los tiempos. Si el
RSS está cerca del techo, ninguna optimización de render va a arreglar nada:
lo que hay que bajar es cuánto se guarda en memoria.

Sospechosos habituales en este proyecto, en orden:

  - la **vista 9.300**, que es una copia completa de todas las tablas: conviven
    en memoria la versión STD y la convertida;
  - la **serie temporal**, que guarda una corrida por mes en `session_state`;
  - el resultado del **sandbox**, que es otra corrida entera;
  - dependencias pesadas en `requirements.txt`. `geopandas` en particular
    arrastra shapely y pyproj; `anthropic` no hace falta hasta que se encienda
    la IA de verdad.

Qué mirar en los tiempos: si el total de los tabs es mucho menor que lo que
tarda la página en responder, el tiempo NO está en el render — está en el
pipeline, en el reload de `config`, en el I/O del Excel o en un reinicio.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager

import streamlit as st

CLAVE = "_perfil_tiempos"


def activo() -> bool:
    if os.environ.get("PERFIL"):
        return True
    try:
        return bool(st.secrets.get("PERFIL"))  # type: ignore[attr-defined]
    except Exception:
        return False


@contextmanager
def cronometrar(nombre: str):
    """Mide un bloque. Sin `PERFIL` no hace absolutamente nada."""
    if not activo():
        yield
        return

    inicio = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - inicio) * 1000
        st.session_state.setdefault(CLAVE, {})[nombre] = ms


# Techo aproximado de Streamlit Community Cloud. No es un valor oficial ni
# estable: sirve para pintar el porcentaje y saber si estamos cerca.
TECHO_MB_CLOUD = 1024


def memoria_mb() -> float | None:
    """RSS del proceso en MB, o None si no está psutil."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def mostrar_perfil():
    """Memoria del proceso + lo que tardó cada bloque. Al final del script."""
    if not activo():
        return

    tiempos = st.session_state.pop(CLAVE, {})
    rss = memoria_mb()

    total = sum(tiempos.values()) if tiempos else 0.0
    titulo = f"⏱️ Perfil — {total:,.0f} ms de render"
    if rss is not None:
        titulo += f" · {rss:,.0f} MB en memoria"

    with st.expander(titulo, expanded=False):
        # La memoria va PRIMERO: en la nube es la que explica los síntomas que
        # el tiempo de render no explica.
        if rss is None:
            st.caption("Agregá `psutil` a requirements.txt para ver la memoria "
                       "del proceso, que en la nube suele ser el problema real.")
        else:
            uso = rss / TECHO_MB_CLOUD
            st.progress(min(uso, 1.0),
                        text=f"{rss:,.0f} MB de ~{TECHO_MB_CLOUD} MB "
                             f"({uso:.0%}) — techo aproximado de Community Cloud")
            if uso > 0.75:
                st.error(
                    "Cerca del límite. Un contenedor así se reinicia solo, y "
                    "desde afuera eso se ve como lentitud y como tener que "
                    "apretar los botones varias veces. Ninguna optimización de "
                    "render lo arregla: hay que bajar lo que se guarda en "
                    "memoria (vista 9.300, serie temporal, sandbox) o achicar "
                    "`requirements.txt`.")

        if not tiempos:
            return

        st.divider()
        st.caption("Tiempo de CADA rerun, mires el tab que mires: Streamlit "
                   "los renderiza todos. El de arriba es el que hay que atacar.")
        for nombre, ms in sorted(tiempos.items(), key=lambda kv: kv[1],
                                 reverse=True):
            st.write(f"`{ms:8,.0f} ms`  {nombre}")
        st.caption("Si este total es mucho menor que lo que tarda la página en "
                   "responder, el tiempo no está en el render sino en el "
                   "pipeline, el reload de `config`, la lectura del Excel o un "
                   "reinicio del contenedor.")
