"""
La burbuja de ayuda (arriba a la derecha): glosario y buscador.
===============================================================

Es la ayuda de vocabulario: "¿qué es el bypass?", "¿qué quiere decir que el
balance no cierra?". Nada mas. La lectura de la corrida y la guia del sandbox
viven en el tab Asistente, porque necesitan una corrida y se leen con espacio.

Esa division no es solo de gusto: es lo que hace que la burbuja sea BARATA.
No depende de `resultados`, ni del explicador, ni del resumen de la corrida, y
por eso se puede dibujar antes que todo lo demas.

POR QUE ABRE RAPIDO
-------------------
Hay dos costos distintos y conviene no confundirlos:

  - Abrir el modal es un rerun de APP: Streamlit vuelve a correr el script
    entero. Si la burbuja se dibuja al final, el modal recien aparece despues
    de rehacer los tabs, el graphviz, el mapa y las tablas. **Por eso se llama
    ARRIBA DE TODO en `app.py`**: Streamlit va mandando los elementos a medida
    que los produce, asi que el modal se ve enseguida y el resto de la pagina
    se sigue dibujando abajo.

  - Interactuar DENTRO del modal no es un rerun de app: `st.dialog` hereda el
    comportamiento de `st.fragment`, asi que escribir en el buscador solo
    vuelve a correr la funcion del dialogo. Eso ya venia gratis.

Lo que NO hay que hacer es envolver la burbuja en `st.fragment` para acelerar
la apertura: anidar un dialogo dentro de un fragment tiene bugs conocidos
(modales que no cierran, contenido que desaparece al interactuar). La
documentacion de Streamlit recomienda justamente el patron de abajo — el
dialogo se llama detras de la interaccion con el boton, no dentro de otro
fragment.

Uso en app.py — UNA linea, lo mas ARRIBA posible:

    from ui.asistente_popup import asistente_flotante
    asistente_flotante()
"""

from __future__ import annotations

import streamlit as st

from ui.tab_asistente import cuerpo_documentacion, docs_para_ia, ia_disponible

CLAVE_BOTON = "asistente_burbuja"

# Alto fijo del cuerpo. Sin esto, el panel cambia de tamaño con cada busqueda y
# el contenido salta mientras lo estas leyendo.
ALTO_CUERPO = 440

# `top` esquiva la barra propia de Streamlit (el menu y el boton de deploy
# viven en la esquina superior derecha, ~3.75rem de alto). Si algun dia la
# burbuja se superpone con ese menu, este es el numero a subir.
_CSS = """
<style>
/* `.st-key-asistente_burbuja` es la clase que Streamlit genera a partir de la
   key del container (>= 1.39). Si esta regla no aplica, el boton queda en su
   lugar del flujo: nada se rompe. */
.st-key-%(key)s {
    position: fixed;
    right: 1.5rem;
    top: 4.2rem;
    z-index: 999;
    width: auto;
}
.st-key-%(key)s button {
    border-radius: 999px;
    padding: 0.6rem 1.1rem;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}
@media (max-width: 640px) {
    .st-key-%(key)s { right: 0.6rem; top: 3.6rem; }
}
</style>
""" % {"key": CLAVE_BOTON}


def asistente_flotante():
    """Dibuja la burbuja; si la tocan, abre el modal en ESTE mismo run.

    Se puede llamar desde cualquier punto del script, incluso antes del
    `st.stop()` de la pantalla de bienvenida: no necesita corrida. Pero cuanto
    mas arriba, antes aparece el modal.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.container(key=CLAVE_BOTON):
        abrir = st.button(
            "💬 Ayuda", key="btn_abrir_asistente",
            help="Glosario y buscador sobre la documentación. Disponible "
                 "siempre, haya corrida o no.")

    if not abrir:
        return

    # El patron recomendado por la documentacion: el dialogo se llama detras de
    # la interaccion, no de una bandera en session_state. Con una bandera
    # haria falta apagarla a mano para que el modal no se reabra solo despues
    # de cerrarlo con la X.
    dialogo = getattr(st, "dialog", None)
    if dialogo is None:
        # Streamlit < 1.37: sin modal. Feo pero funcional.
        with st.expander("💬 Ayuda", expanded=True):
            _cuerpo()
        return

    @dialogo("💬 Ayuda", width="large")
    def _modal():
        _cuerpo()

    _modal()


def _cuerpo():
    """Glosario y buscador, con el chat de documentación plegado abajo."""
    with st.container(height=ALTO_CUERPO, border=False):
        cuerpo_documentacion(docs_para_ia(), sufijo="pop")

    if not ia_disponible():
        st.caption("Modo local: sin conexión ni credenciales. Para leer la "
                   "corrida o armar escenarios, mirá el tab **Asistente**.")
    else:
        st.caption("Para leer la corrida o armar escenarios, mirá el tab "
                   "**Asistente**.")
