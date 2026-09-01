"""
Tab "Asistente" para app.py — HIBRIDO.
======================================

Tres asistentes, cada uno en dos capas:

                    | sin credencial (siempre)      | con credencial (extra)
  ------------------|-------------------------------|------------------------
  📖 Documentación  | buscador + glosario           | chat sobre los docs
  📊 Resultados     | explicador determinista       | chat sobre la corrida
  🛠️ Sandbox        | guia paso a paso              | agente con herramientas

La capa de abajo NO necesita red, ni key, ni que salga un solo dato del
servidor. Es la que ve todo el mundo. La de arriba aparece sola si hay
`ANTHROPIC_API_KEY` configurada, y hasta entonces el tab avisa que existe pero
no molesta.

Por que hibrido y no una cosa u otra
------------------------------------
El buscador y el explicador son mas confiables que un modelo para lo que mas se
pregunta ("que es esto", "por que da esto"): no alucinan y las reglas las
escribimos nosotros. El modelo aporta en lo que ellos no pueden: reformular una
pregunta mal planteada, cruzar dos docs, y operar el sandbox por lenguaje
natural. Tener las dos capas significa que el tablero es util para alguien de
afuera desde el dia uno, y que habilitar la IA despues es cambiar un secreto.

Integracion en app.py (dos lineas + un tab):

    from ui.tab_asistente import panel_asistente
    ...
    with tab_asistente:
        _render_seguro("Asistente", panel_asistente,
                       resultados_fisicos, PARAMS,
                       serie=st.session_state.get("serie"))

OJO: `resultados_fisicos` (STD), no la vista 9.300.
"""

from __future__ import annotations

import streamlit as st

from ia.buscador import (
    construir_indice, buscar, buscar_glosario, preview, GLOSARIO,
)
from ia.explicador import explicar, PREGUNTAS

# La capa de IA es OPCIONAL hasta en el import: si falta el paquete
# `anthropic`, el tab tiene que seguir funcionando completo sin ella.
try:
    from ia.cliente import (
        stream_texto, completar, hay_credencial, modelo_configurado, SinAPIKey,
    )
    from ia.contexto import (
        cargar_docs, resumen_resultados,
        SYSTEM_DOCS, SYSTEM_RESULTADOS, SYSTEM_AGENTE,
    )
    from ia.herramientas import ESQUEMAS, Ejecutor
    IA_IMPORTABLE = True
    ERROR_IA = ""
except Exception as e:  # noqa: BLE001
    IA_IMPORTABLE = False
    ERROR_IA = f"{type(e).__name__}: {e}"

CLAVES_HISTORIA = {
    "docs": "asistente_hist_docs",
    "resultados": "asistente_hist_res",
    "agente": "asistente_hist_agente",
}

MAX_TURNOS_API = 12
MAX_ITERACIONES_AGENTE = 12

_NIVELES = {
    "problema": ("🔴", st.error),
    "atencion": ("🟡", st.warning),
    "ok": ("🟢", st.success),
    "info": ("🔵", st.info),
}


def ia_disponible() -> bool:
    """Hay SDK Y credencial: recien ahi se ofrece el chat."""
    return IA_IMPORTABLE and hay_credencial()


# ===========================================================================
# Capa sin IA
# ===========================================================================

@st.cache_data(show_spinner=False)
def _indice_cacheado(carpeta: str = "docs"):
    """El indice se relee cuando cambia el codigo o se limpia el cache.

    Si estas editando los .md y no ves los cambios, el boton "Reindexar"
    limpia esto.
    """
    return construir_indice(carpeta)


def _bloque_buscador():
    indice = _indice_cacheado()

    col_a, col_b = st.columns([4, 1])
    consulta = col_a.text_input(
        "Buscá en la documentación", key="buscador_q",
        placeholder="cascada, retenidos, por qué no cierra el balance…",
        label_visibility="collapsed")
    if col_b.button("↻ Reindexar", key="btn_reindexar",
                    help="Volvé a leer los .md de docs/."):
        _indice_cacheado.clear()
        st.rerun()

    if not indice:
        st.warning("No encontré archivos .md en `docs/`: el buscador no tiene "
                   "material.")
        return

    st.caption(f"{len(indice)} secciones indexadas. El buscador **no genera "
               "texto**: te muestra los fragmentos reales de la documentación.")

    if not consulta:
        with st.expander("📚 Glosario: los términos del tablero", expanded=True):
            st.caption("Lo mínimo para entender la primera pantalla.")
            for termino, datos in GLOSARIO.items():
                st.markdown(f"**{termino}** — {datos['texto']}")
        return

    # El glosario primero: si preguntan "que es la cascada", la definicion
    # curada le gana a cualquier seccion de un doc tecnico.
    for termino, texto in buscar_glosario(consulta):
        st.info(f"**{termino}** — {texto}")

    resultados = buscar(consulta, indice)
    if not resultados:
        st.warning(
            "Sin resultados. Probá con una palabra sola y del vocabulario del "
            "modelo (planta, hub, cromatografía, retenidos, gasoducto).")
        return

    for r in resultados:
        with st.expander(f"**{r['titulo']}** · `{r['archivo']}`", expanded=False):
            visible, resto = preview(r["cuerpo"])
            st.markdown(visible)
            if resto:
                with st.expander("Ver el resto de la sección"):
                    st.markdown(resto)
            st.caption(f"Coincidencias: {', '.join(r['terminos'])}")


def _bloque_explicador(resultados, params, serie):
    st.caption(
        "Lectura **automática y determinista** de la corrida: son reglas "
        "escritas a mano sobre los números, no un modelo. Ante los mismos "
        "datos dice siempre lo mismo.")

    hallazgos = explicar(resultados, params=params, serie=serie)

    pregunta = st.selectbox(
        "¿Qué querés mirar?", list(PREGUNTAS), key="explicador_q")
    filtrados = PREGUNTAS[pregunta](hallazgos) or hallazgos

    if not filtrados:
        st.info("Nada para reportar en ese punto.")
        return

    for h in filtrados:
        icono, pintar = _NIVELES.get(h.nivel, ("🔵", st.info))
        cuerpo = f"**{icono} {h.titulo}**\n\n{h.detalle}"
        if h.donde:
            cuerpo += f"\n\n*Dónde mirarlo: tab {h.donde}.*"
        pintar(cuerpo)


def _bloque_guia_sandbox(resultados):
    st.caption(
        "Sin IA el sandbox se opera a mano, y no es difícil: son cuatro pasos.")
    st.markdown(
        "1. **Tab _Plantas (sandbox)_** → sub-tab *Plantas*: creá una planta "
        "o cambiale capacidades a una existente.\n"
        "2. Sub-tab *Gasoductos*: das de alta o de baja un ducto. El total que "
        "inyecta cada área no cambia, solo se reparte distinto.\n"
        "3. **Resolver cascada**.\n"
        "4. Mirá el **bloque de control**: con el registro sin tocar tiene que "
        "dar cero. Si da distinto, no le creas al escenario.")
    st.info(
        "Los **escenarios prearmados** (sub-tab *Escenarios*) son el atajo: "
        "dejan un caso completo — plantas, cromatografías y ductos — listo de "
        "un click, y se pueden guardar y compartir como `.json`.")


# ===========================================================================
# Capa con IA
# ===========================================================================

def _historia(clave: str) -> list[dict]:
    return st.session_state.setdefault(CLAVES_HISTORIA[clave], [])


def _dibujar_historia(historia):
    for msg in historia:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def _mensajes_para_api(historia):
    return [{"role": m["role"], "content": m["content"]}
            for m in historia[-MAX_TURNOS_API:]]


def _boton_limpiar(clave: str):
    if st.button("🗑️ Limpiar conversación", key=f"btn_limpiar_{clave}"):
        st.session_state.pop(CLAVES_HISTORIA[clave], None)
        st.rerun()


def _chat_simple(clave: str, system: str, placeholder: str):
    historia = _historia(clave)
    _dibujar_historia(historia)

    pregunta = st.chat_input(placeholder, key=f"chat_{clave}")
    if not pregunta:
        return

    historia.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        try:
            respuesta = st.write_stream(
                stream_texto(system, _mensajes_para_api(historia)))
        except SinAPIKey:
            historia.pop()
            st.warning("Se perdió la credencial: revisá `secrets.toml`.")
            return
        except Exception as e:  # noqa: BLE001 - un fallo de API no tumba el tab
            historia.pop()
            st.error(f"La llamada a la API falló: {type(e).__name__}: {e}")
            return

    historia.append({"role": "assistant", "content": str(respuesta)})


def _extraer_texto(respuesta) -> str:
    return "\n".join(b.text for b in respuesta.content
                     if getattr(b, "type", "") == "text").strip()


def _correr_agente(system, mensajes, ejecutor, log) -> str:
    """messages -> (tool_use -> ejecutar -> tool_result)* -> texto final."""
    for _ in range(MAX_ITERACIONES_AGENTE):
        respuesta = completar(system, mensajes, tools=ESQUEMAS)

        if respuesta.stop_reason != "tool_use":
            return _extraer_texto(respuesta) or "(el modelo no devolvió texto)"

        mensajes.append({"role": "assistant", "content": respuesta.content})

        resultados_tools = []
        for bloque in respuesta.content:
            if getattr(bloque, "type", "") != "tool_use":
                continue
            with log:
                with st.status(f"🔧 {bloque.name}", expanded=False) as estado:
                    st.code(str(bloque.input), language="json")
                    salida = ejecutor.ejecutar(bloque.name, bloque.input)
                    st.text(salida[:2000])
                    estado.update(state="complete")
            resultados_tools.append({
                "type": "tool_result",
                "tool_use_id": bloque.id,
                "content": salida,
            })

        mensajes.append({"role": "user", "content": resultados_tools})

    return (f"Corté a las {MAX_ITERACIONES_AGENTE} iteraciones para no entrar "
            "en un ciclo. Lo hecho quedó en el sandbox; pedime que siga.")


def _chat_agente(resultados, docs, resumen, factor_mm):
    comunes = resultados.get("comunes")
    if not comunes:
        st.info("El agente necesita `comunes` del pipeline para poder correr "
                "la cascada.")
        return

    if "registro_plantas" not in st.session_state:
        try:
            from ui.plantas_editor import inicializar
            inicializar(resultados["retenidos_rtp"], comunes["COMPUESTOS"],
                        resultados.get("params_efectivos", {}),
                        bool(resultados.get("tbx_en_servicio", True)))
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo sembrar el registro del sandbox: {e}. "
                     "Abrí una vez el tab Plantas (sandbox) y volvé.")
            return

    ejecutor = Ejecutor(comunes=comunes,
                        flujos_oficiales=resultados.get("flujos_plantas"),
                        factor_mm=factor_mm)
    system = SYSTEM_AGENTE.format(docs=docs, resultados=resumen)

    historia = _historia("agente")
    _dibujar_historia(historia)

    pedido = st.chat_input(
        "p. ej.: «bajá el gasoducto VMN y contame qué planta pierde gas»",
        key="chat_agente")
    if not pedido:
        return

    historia.append({"role": "user", "content": pedido})
    with st.chat_message("user"):
        st.markdown(pedido)

    with st.chat_message("assistant"):
        log = st.container()
        try:
            with st.spinner("Trabajando en el sandbox…"):
                final = _correr_agente(
                    system, _mensajes_para_api(historia), ejecutor, log)
        except Exception as e:  # noqa: BLE001
            historia.pop()
            st.error(f"El agente falló: {type(e).__name__}: {e}")
            return
        st.markdown(final)

    historia.append({"role": "assistant", "content": final})

    if st.session_state.get("sandbox_resultado") is not None:
        st.rerun()


def _con_ia(etiqueta: str, clave: str, cuerpo):
    """Envuelve la capa IA en un expander cerrado.

    Cerrado a proposito: la capa sin IA es la respuesta por defecto, y el chat
    es el segundo intento cuando el buscador no alcanzo.
    """
    with st.expander(f"🤖 {etiqueta}", expanded=False):
        st.caption(
            f"Modelo `{modelo_configurado()}`. **Lo que preguntes y el "
            "contexto viajan a la API de Anthropic.**")
        _boton_limpiar(clave)
        cuerpo()


def _aviso_ia_apagada():
    with st.expander("🤖 Chat con IA (desactivado)", expanded=False):
        if not IA_IMPORTABLE:
            st.caption(f"Falta el paquete `anthropic` ({ERROR_IA}). "
                       "Agregalo a requirements.txt si querés habilitarlo.")
        else:
            st.caption(
                "Cargá `ANTHROPIC_API_KEY` en `.streamlit/secrets.toml` para "
                "sumar un chat que responde preguntas abiertas. Todo lo de "
                "arriba funciona igual sin eso.")


# ===========================================================================
# Panel
# ===========================================================================

def panel_asistente(resultados: dict | None, params=None,
                    serie: dict | None = None, factor_mm: float = 1000.0):
    """Dibuja el tab completo. `resultados` FÍSICOS (STD) o None."""

    st.subheader("Asistente")
    hay_ia = ia_disponible()
    st.caption(
        "Buscador de documentación, lectura automática de la corrida y guía "
        "del sandbox. Todo local: no sale ningún dato del servidor."
        + ("" if hay_ia else " El chat con IA está desactivado."))

    # Los docs completos y el resumen solo se arman si hay IA: son la parte
    # cara y la capa de abajo no los usa (el buscador tiene su propio indice).
    docs = resumen = ""
    if hay_ia:
        docs, avisos = cargar_docs()
        for aviso in avisos:
            st.warning(aviso)
        resumen = resumen_resultados(resultados, factor_mm=factor_mm, serie=serie)

    tab_docs, tab_res, tab_op = st.tabs(
        ["📖 Documentación", "📊 Resultados", "🛠️ Sandbox"])

    with tab_docs:
        _bloque_buscador()
        st.divider()
        if hay_ia:
            _con_ia("Preguntale a la IA sobre la documentación", "docs",
                    lambda: _chat_simple(
                        "docs", SYSTEM_DOCS.format(docs=docs),
                        "p. ej.: «¿qué es la cascada del pool de gas?»"))
        else:
            _aviso_ia_apagada()

    with tab_res:
        _bloque_explicador(resultados, params, serie)
        st.divider()
        if hay_ia:
            _con_ia("Preguntale a la IA sobre esta corrida", "resultados",
                    lambda: _chat_simple(
                        "resultados",
                        SYSTEM_RESULTADOS.format(docs=docs, resultados=resumen),
                        "p. ej.: «¿por qué MEGA tiene sobrante este período?»"))
        else:
            _aviso_ia_apagada()

    with tab_op:
        _bloque_guia_sandbox(resultados)
        st.divider()
        if hay_ia and resultados:
            _con_ia("Que la IA opere el sandbox por vos", "agente",
                    lambda: _chat_agente(resultados, docs, resumen, factor_mm))
        elif hay_ia:
            st.info("Corré el pipeline para habilitar el operador con IA.")
        else:
            _aviso_ia_apagada()
