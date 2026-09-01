"""
El asistente como burbuja flotante (abajo a la derecha).
========================================================

El mismo asistente que el tab, pero disponible SIEMPRE, sin tener que
abandonar lo que estabas mirando. Es la forma en que la gente espera encontrar
la ayuda de una aplicacion web: una burbuja que sigue ahi mientras mirás los
números.

Como esta hecho, y por que asi
------------------------------
Streamlit no tiene widgets flotantes. Las dos piezas:

1. **El disparador** es un `st.button` normal, metido en un
   `st.container(key=...)`. Desde Streamlit 1.39 esa `key` se traduce en una
   clase CSS `st-key-<key>` en el DOM, que es el hook OFICIAL para estilar
   (tanto que `stylable_container` de streamlit-extras quedo deprecado a favor
   suyo). Con eso, el CSS que fija la burbuja apunta a UNA clase estable en
   vez de a los nombres internos de Streamlit, que cambian entre versiones.

2. **El panel** es un `st.dialog`, que es modal de verdad y lo maneja
   Streamlit. La alternativa —dibujar el panel entero flotando con CSS— obliga
   a pelear con el layout en cada version y se rompe en pantallas chicas.

O sea: de todo el asistente, lo unico que depende de CSS es la POSICION de un
boton. Si algun dia ese CSS deja de aplicar, el boton aparece en su lugar
normal del flujo y todo lo demas sigue funcionando. Es la degradacion mas
barata posible.

3. **La entrada de texto** dentro del modal NO es `st.chat_input`: ese widget
   tiene restricciones de donde puede vivir. Se usa un `text_input` + boton,
   que se comporta igual y no depende de esa lista.

Uso en app.py — UNA linea, y va afuera de los tabs:

    from ui.asistente_popup import asistente_flotante
    asistente_flotante(resultados_fisicos, PARAMS,
                       serie=st.session_state.get("serie"))
"""

from __future__ import annotations

import streamlit as st

from ui.tab_asistente import (
    cuerpo_documentacion, cuerpo_resultados, cuerpo_sandbox,
    contexto_ia, ia_disponible,
)

CLAVE_ABIERTO = "asistente_popup_abierto"
CLAVE_BOTON = "asistente_burbuja"

# Alto fijo del cuerpo del modal. Sin esto, el panel cambia de tamaño en cada
# respuesta y el boton de enviar se te escapa hacia abajo mientras escribis.
ALTO_CUERPO = 420

_CSS = """
<style>
/* La burbuja. `.st-key-asistente_burbuja` es la clase que Streamlit genera a
   partir de la key del container (>= 1.39). Si esta regla no aplica, el boton
   simplemente queda al final de la pagina: nada se rompe. */
.st-key-%(key)s {
    position: fixed;
    right: 1.5rem;
    bottom: 1.5rem;
    z-index: 999;
    width: auto;
}
.st-key-%(key)s button {
    border-radius: 999px;
    padding: 0.6rem 1.1rem;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}
/* En pantallas chicas la burbuja se corre para no taparle el pulgar a nadie. */
@media (max-width: 640px) {
    .st-key-%(key)s { right: 0.75rem; bottom: 0.75rem; }
}
</style>
""" % {"key": CLAVE_BOTON}


def _abrir():
    st.session_state[CLAVE_ABIERTO] = True


def asistente_flotante(resultados: dict | None, params=None,
                       serie: dict | None = None, factor_mm: float = 1000.0):
    """Dibuja la burbuja y, si esta abierta, el modal del asistente.

    Se puede llamar desde cualquier punto del script, incluso ANTES del
    `st.stop()` de la pantalla de bienvenida: el asistente no necesita que haya
    corrida para servir.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    with st.container(key=CLAVE_BOTON):
        st.button("💬 Ayuda", key="btn_abrir_asistente", on_click=_abrir,
                  help="Buscador de documentación, glosario y lectura de la "
                       "corrida. No hace falta cerrar nada para volver.")

    if not st.session_state.get(CLAVE_ABIERTO):
        return

    # `st.dialog` es GA desde Streamlit 1.37. Si la version es mas vieja, en
    # vez de reventar se cae a un expander: fea pero funcional.
    dialogo = getattr(st, "dialog", None)
    if dialogo is None:
        with st.expander("💬 Asistente", expanded=True):
            _cuerpo(resultados, params, serie, factor_mm)
            if st.button("Cerrar", key="btn_cerrar_asistente_exp"):
                st.session_state[CLAVE_ABIERTO] = False
                st.rerun()
        return

    @dialogo("💬 Asistente", width="large")
    def _modal():
        _cuerpo(resultados, params, serie, factor_mm)

    # Al cerrar el modal con la X, Streamlit rerunea y la clave sigue en True,
    # asi que el modal volveria a abrirse solo. Se apaga ACA, apenas se dibuja:
    # el modal ya quedo en pantalla para este run, y el siguiente arranca
    # cerrado salvo que el usuario vuelva a apretar la burbuja.
    st.session_state[CLAVE_ABIERTO] = False
    _modal()


def _cuerpo(resultados, params, serie, factor_mm):
    """El contenido del panel: los mismos tres asistentes que el tab."""
    docs, resumen = contexto_ia(resultados, serie, factor_mm)

    tab_docs, tab_res, tab_sb = st.tabs(["📖 Ayuda", "📊 Corrida", "🛠️ Sandbox"])

    with tab_docs:
        with st.container(height=ALTO_CUERPO, border=False):
            cuerpo_documentacion(docs, sufijo="pop")

    with tab_res:
        with st.container(height=ALTO_CUERPO, border=False):
            cuerpo_resultados(resultados, params, serie, docs, resumen,
                              sufijo="pop")

    with tab_sb:
        with st.container(height=ALTO_CUERPO, border=False):
            cuerpo_sandbox(resultados, docs, resumen, factor_mm, sufijo="pop")

    if not ia_disponible():
        st.caption("Modo local: sin conexión ni credenciales.")
