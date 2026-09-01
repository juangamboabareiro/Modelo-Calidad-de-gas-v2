"""
El asistente: los tres cuerpos, y el tab que los muestra.
=========================================================

Tres asistentes, cada uno en DOS capas:

                    | sin credencial (siempre)      | con credencial (extra)
  ------------------|-------------------------------|------------------------
  📖 Documentación  | buscador de `docs/` + glosario | chat sobre los docs
  📊 Resultados     | explicador determinista        | chat sobre la corrida
  🛠️ Sandbox        | guía paso a paso               | agente con herramientas

La capa de abajo no usa red, ni key, ni saca un dato del servidor. La de arriba
aparece sola si hay credencial.

UNA SOLA ENTRADA: EL TAB
------------------------
Hubo una versión con burbuja flotante además del tab. Se sacó: dos entradas a
lo mismo obligaban a mantener la posición con CSS y a duplicar claves de
widget, para un beneficio que no compensaba.

Los cuerpos quedan como funciones separadas igual (`cuerpo_documentacion`,
`cuerpo_resultados`, `cuerpo_sandbox`), que es lo que hace que el tab se lea de
un vistazo y que agregar una cuarta sección sea trivial.

El parámetro `sufijo` sobrevive por lo mismo: Streamlit exige claves de widget
únicas, así que si algún día un cuerpo se dibuja dos veces en la misma página,
no revienta. Hoy siempre vale "tab".

Integración en app.py:

    from ui.tab_asistente import panel_asistente

OJO: se le pasa `resultados_fisicos` (STD), no la vista 9.300.
"""

from __future__ import annotations

import streamlit as st

from ia.buscador import (
    construir_indice, buscar, buscar_glosario, preview, obsoletos_presentes,
    GLOSARIO,
)
from ia.explicador import explicar, PREGUNTAS

# La capa de IA es OPCIONAL hasta en el import: si falta el paquete
# `anthropic`, el asistente tiene que seguir funcionando completo sin ella.
try:
    from ia.cliente import (
        stream_texto, completar, hay_credencial, modelo_configurado, SinAPIKey,
        leer_uso, resumen_uso,
    )
    from ia.contexto import cargar_docs, resumen_resultados, bloques_system
    IA_IMPORTABLE = True
    ERROR_IA = ""
except Exception as e:  # noqa: BLE001
    IA_IMPORTABLE = False
    ERROR_IA = f"{type(e).__name__}: {e}"

# Las historias NO llevan sufijo: la conversación es una sola, aunque el
# cuerpo se dibujara en más de un lugar.
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
    """Hay SDK Y credencial: recién ahí se ofrece el chat."""
    return IA_IMPORTABLE and hay_credencial()


# `cache_resource` y no `cache_data`: la diferencia es que `cache_data` COPIA
# el valor en cada acceso (lo deserializa del caché), y estas dos funciones
# devuelven estructuras grandes —el índice son ~300 KB— a las que se accede en
# CADA rerun de la app. `cache_resource` devuelve siempre el mismo objeto, sin
# copiar. Es seguro porque nadie las modifica: se leen y se descartan.
@st.cache_resource(show_spinner=False)
def _docs_crudos() -> str:
    """Los .md concatenados para el contexto de la IA."""
    docs, _ = cargar_docs()
    return docs


@st.cache_resource(show_spinner=False)
def _obsoletos_cacheado(carpeta: str = "docs") -> list[str]:
    """Archivos zombis en docs/.

    Cacheado porque recorre el árbol de directorios, y eso se hacía en cada
    rerun. En un disco local es despreciable; sobre una carpeta sincronizada
    (OneDrive y similares) cada llamada al filesystem puede costar mucho más.
    """
    return obsoletos_presentes(carpeta)


def contexto_ia(resultados, serie, factor_mm) -> tuple[str, str]:
    """(docs, resumen) para los chats del tab. Vacíos si no hay IA."""
    if not ia_disponible():
        return "", ""
    return (_docs_crudos(),
            resumen_resultados(resultados, factor_mm=factor_mm, serie=serie))


# ===========================================================================
# Capa sin IA
# ===========================================================================

@st.cache_resource(show_spinner=False)
def _indice_cacheado(carpeta: str = "docs"):
    """Se relee al limpiar el caché (botón Reindexar) o al cambiar el código."""
    return construir_indice(carpeta)


def cuerpo_documentacion(docs: str = "", sufijo: str = "tab"):
    """Buscador + glosario, y el chat plegado abajo si hay credencial.

    OJO con el orden: el índice NO se toca hasta que hay una consulta. Este
    cuerpo se ejecuta en cada rerun de la app —Streamlit renderiza todos los
    tabs, no sólo el que estás mirando—, y la ruta normal (sin consulta) tiene
    que ser lo más barata posible: el glosario sale de un dict en memoria.
    """
    col_a, col_b = st.columns([4, 1])
    consulta = col_a.text_input(
        "Buscá en la documentación", key=f"buscador_q_{sufijo}",
        placeholder="cascada, retenidos, por qué no cierra el balance…",
        label_visibility="collapsed")
    if col_b.button("↻", key=f"btn_reindexar_{sufijo}",
                    help="Volvé a leer los documentos de docs/."):
        _indice_cacheado.clear()
        _docs_crudos.clear()
        _obsoletos_cacheado.clear()
        st.rerun()

    if not consulta:
        st.caption("Buscá una palabra para ver los fragmentos de la "
                   "documentación. El buscador **no genera texto**: muestra "
                   "los fragmentos reales.")
        with st.expander("📚 Glosario: los términos del tablero", expanded=True):
            for termino, datos in GLOSARIO.items():
                st.markdown(f"**{termino}** — {datos['texto']}")
    else:
        indice = _indice_cacheado()
        if not indice:
            st.warning("No encontré documentos en `docs/`: el buscador no "
                       "tiene material.")
            return

        # Los archivos que el README da por eliminados pero siguen en la
        # carpeta: el buscador ya los ignora, pero mientras estén ahí alguien
        # los va a abrir a mano y creerles.
        sobrantes = _obsoletos_cacheado()
        if sobrantes:
            st.warning(
                f"Estos archivos figuran como eliminados en el README pero "
                f"siguen en `docs/`: `{'`, `'.join(sobrantes)}`. El buscador "
                "los ignora; conviene borrarlos del repo.")

        # El glosario primero: si preguntan "qué es la cascada", la definición
        # curada le gana a cualquier sección de un documento técnico.
        for termino, texto in buscar_glosario(consulta):
            st.info(f"**{termino}** — {texto}")

        resultados = buscar(consulta, indice)
        if not resultados:
            st.warning(
                "Sin resultados. Probá con una palabra sola y del vocabulario "
                "del modelo (planta, hub, cromatografía, retenidos, bypass).")
        for r in resultados:
            with st.expander(f"**{r['titulo']}** · `{r['archivo']}`"):
                if r.get("aviso"):
                    st.caption(f"⚠️ {r['aviso']}")
                visible, resto = preview(r["cuerpo"])
                st.markdown(visible)
                if resto:
                    with st.expander("Ver el resto de la sección"):
                        st.markdown(resto)

    _bloque_ia("Preguntar a la IA sobre la documentación", "docs", sufijo,
               lambda: _chat("docs", bloques_system("docs", docs), sufijo,
                             "¿qué es la cascada del pool de gas?"))


def cuerpo_resultados(resultados, params, serie, docs: str = "",
                      resumen: str = "", sufijo: str = "tab"):
    """Lectura determinista de la corrida, y el chat plegado abajo."""
    hallazgos = explicar(resultados, params=params, serie=serie)

    pregunta = st.selectbox("¿Qué querés mirar?", list(PREGUNTAS),
                            key=f"explicador_q_{sufijo}")
    filtrados = PREGUNTAS[pregunta](hallazgos) or hallazgos

    for h in filtrados:
        icono, pintar = _NIVELES.get(h.nivel, ("🔵", st.info))
        cuerpo = f"**{icono} {h.titulo}**\n\n{h.detalle}"
        if h.donde:
            cuerpo += f"\n\n*Dónde mirarlo: tab {h.donde}.*"
        pintar(cuerpo)

    st.caption("Reglas escritas a mano sobre los números, no un modelo: ante "
               "los mismos datos dice siempre lo mismo.")

    _bloque_ia("Preguntar a la IA sobre esta corrida", "resultados", sufijo,
               lambda: _chat("resultados",
                             bloques_system("resultados", docs, resumen),
                             sufijo, "¿por qué MEGA tiene sobrante?"))


def cuerpo_sandbox(resultados, docs: str = "", resumen: str = "",
                   factor_mm: float = 1000.0, sufijo: str = "tab"):
    """Guía del sandbox, y el agente plegado abajo si hay credencial."""
    st.markdown(
        "1. **Tab _Plantas (sandbox)_** → *Plantas*: creá una planta o "
        "cambiale las capacidades a una existente.\n"
        "2. *Gasoductos*: alta o baja de un ducto. El total que inyecta cada "
        "área no cambia, sólo se reparte distinto.\n"
        "3. **Resolver cascada**.\n"
        "4. Mirá el **bloque de control**: con el registro sin tocar tiene que "
        "dar cero. Si no, no le creas al escenario.")
    st.caption("Los escenarios prearmados dejan un caso completo —plantas, "
               "cromatografías y ductos— listo de un click.")

    if resultados:
        _bloque_ia("Que la IA opere el sandbox", "agente", sufijo,
                   lambda: _chat_agente(resultados, docs, resumen, factor_mm,
                                        sufijo))


# ===========================================================================
# Capa con IA
# ===========================================================================

def _historia(clave: str) -> list[dict]:
    return st.session_state.setdefault(CLAVES_HISTORIA[clave], [])


def _mensajes_para_api(historia):
    return [{"role": m["role"], "content": m["content"]}
            for m in historia[-MAX_TURNOS_API:]]


def _bloque_ia(etiqueta: str, clave: str, sufijo: str, cuerpo):
    """Envuelve la capa IA en un expander cerrado.

    Cerrado a propósito: la capa sin IA es la respuesta por defecto y el chat
    es el segundo intento, cuando el buscador no alcanzó.
    """
    st.divider()
    if not ia_disponible():
        with st.expander("🤖 Chat con IA (desactivado)"):
            if not IA_IMPORTABLE:
                st.caption(f"Falta el paquete `anthropic` ({ERROR_IA}).")
            else:
                st.caption("Cargá `ANTHROPIC_API_KEY` en "
                           "`.streamlit/secrets.toml` para sumar un chat que "
                           "responde preguntas abiertas. Todo lo de arriba "
                           "funciona igual sin eso.")
        return

    with st.expander(f"🤖 {etiqueta}"):
        st.caption(f"Modelo `{modelo_configurado()}`. **Lo que preguntes y el "
                   "contexto viajan a la API de Anthropic.**")
        if st.button("🗑️ Limpiar", key=f"btn_limpiar_{clave}_{sufijo}"):
            st.session_state.pop(CLAVES_HISTORIA[clave], None)
            st.rerun()
        cuerpo()


def _entrada(clave: str, sufijo: str, ejemplo: str) -> str | None:
    """La caja de texto. Devuelve el pedido, o None.

    En el modal NO se puede usar `st.chat_input`: ese widget tiene
    restricciones sobre dónde puede vivir. El par text_input + botón se
    comporta igual y no depende de esa lista.
    """
    with st.form(key=f"form_{clave}_{sufijo}", clear_on_submit=True):
        texto = st.text_input("Tu pregunta", placeholder=f"p. ej.: «{ejemplo}»",
                              label_visibility="collapsed")
        enviado = st.form_submit_button("Preguntar")
    return texto.strip() if (enviado and texto.strip()) else None


def _dibujar_historia(historia):
    for msg in historia:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])


def _chat(clave: str, system, sufijo: str, ejemplo: str):
    historia = _historia(clave)
    _dibujar_historia(historia)

    pregunta = _entrada(clave, sufijo, ejemplo)
    if not pregunta:
        return

    historia.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    with st.chat_message("assistant"):
        uso: dict = {}
        try:
            respuesta = st.write_stream(
                stream_texto(system, _mensajes_para_api(historia),
                             registro_uso=uso))
        except SinAPIKey:
            historia.pop()
            st.warning("Se perdió la credencial: revisá `secrets.toml`.")
            return
        except Exception as e:  # noqa: BLE001 - un fallo de API no tumba nada
            historia.pop()
            st.error(f"La llamada a la API falló: {type(e).__name__}: {e}")
            return

        # El consumo va como caption bajo la respuesta: es la única forma de
        # notar que el caching funciona (la segunda pregunta seguida tiene que
        # decir "desde caché" y costar ~10x menos).
        if uso:
            st.caption(resumen_uso(uso))

    historia.append({"role": "assistant", "content": str(respuesta)})


def _extraer_texto(respuesta) -> str:
    return "\n".join(b.text for b in respuesta.content
                     if getattr(b, "type", "") == "text").strip()


def _correr_agente(system, mensajes, ejecutor, log, uso_total: dict) -> str:
    """messages -> (tool_use -> ejecutar -> tool_result)* -> texto final.

    `uso_total` acumula TODAS las iteraciones: un pedido del agente son varias
    llamadas, y mostrar sólo la última subestimaría el costo del turno.
    """
    from ia.herramientas import ESQUEMAS

    for _ in range(MAX_ITERACIONES_AGENTE):
        respuesta = completar(system, mensajes, tools=ESQUEMAS)

        for clave, valor in leer_uso(getattr(respuesta, "usage", None)).items():
            uso_total[clave] = uso_total.get(clave, 0) + valor

        if respuesta.stop_reason != "tool_use":
            return _extraer_texto(respuesta) or "(el modelo no devolvió texto)"

        mensajes.append({"role": "assistant", "content": respuesta.content})

        resultados_tools = []
        for bloque in respuesta.content:
            if getattr(bloque, "type", "") != "tool_use":
                continue
            with log:
                with st.status(f"🔧 {bloque.name}") as estado:
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


def _chat_agente(resultados, docs, resumen, factor_mm, sufijo):
    from ia.herramientas import Ejecutor

    comunes = resultados.get("comunes")
    if not comunes:
        st.info("El agente necesita `comunes` del pipeline para correr la "
                "cascada.")
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

    st.caption("⚠️ Modifica el sandbox, nunca la corrida oficial. Lo que arme "
               "queda visible en el tab *Plantas (sandbox)* y se deshace con "
               "**Restablecer**.")

    ejecutor = Ejecutor(comunes=comunes,
                        flujos_oficiales=resultados.get("flujos_plantas"),
                        factor_mm=factor_mm)
    system = bloques_system("agente", docs, resumen)

    historia = _historia("agente")
    _dibujar_historia(historia)

    pedido = _entrada("agente", sufijo,
                      "bajá el gasoducto VMN y decime qué planta pierde gas")
    if not pedido:
        return

    historia.append({"role": "user", "content": pedido})
    with st.chat_message("user"):
        st.markdown(pedido)

    with st.chat_message("assistant"):
        log = st.container()
        uso_total: dict = {}
        try:
            with st.spinner("Trabajando en el sandbox…"):
                final = _correr_agente(system, _mensajes_para_api(historia),
                                       ejecutor, log, uso_total)
        except Exception as e:  # noqa: BLE001
            historia.pop()
            st.error(f"El agente falló: {type(e).__name__}: {e}")
            return
        st.markdown(final)
        if uso_total:
            st.caption(resumen_uso(uso_total) + " · suma de todas las llamadas")

    historia.append({"role": "assistant", "content": final})


# ===========================================================================
# El tab
# ===========================================================================

def _envolver_en_fragment(funcion):
    """Devuelve `funcion` envuelta en `st.fragment`, si esta versión lo tiene.

    Mismo patrón que `ui/tab_plantas.py`. Sin esto, escribir una letra en el
    buscador rerenderiza el script ENTERO —los otros nueve tabs, el graphviz,
    el mapa y las tablas—, que es exactamente lo que hace que el asistente se
    sienta lento aunque él mismo sea barato.

    Se prueban los dos nombres porque `st.fragment` se llamó
    `st.experimental_fragment` entre 1.33 y 1.36, y se verifica que lo devuelto
    sea invocable: si no, se degrada al comportamiento de siempre en vez de
    romper el tab.
    """
    for nombre in ("fragment", "experimental_fragment"):
        decorador = getattr(st, nombre, None)
        if decorador is None:
            continue
        try:
            envuelta = decorador(funcion)
        except Exception:
            continue
        if callable(envuelta):
            return envuelta
    return funcion


def _cuerpo_panel(resultados, params, serie, factor_mm):
    st.subheader("Asistente")
    st.caption(
        "Buscador de documentación, lectura automática de la corrida y guía "
        "del sandbox. Todo local: no sale ningún dato del servidor."
        + ("" if ia_disponible() else " El chat con IA está desactivado."))

    docs, resumen = contexto_ia(resultados, serie, factor_mm)

    tab_docs, tab_res, tab_sb = st.tabs(
        ["📖 Documentación", "📊 Resultados", "🛠️ Sandbox"])

    with tab_docs:
        cuerpo_documentacion(docs, sufijo="tab")

    with tab_res:
        if not resultados:
            st.info("Todavía no hay corrida.")
        cuerpo_resultados(resultados, params, serie, docs, resumen, sufijo="tab")

    with tab_sb:
        cuerpo_sandbox(resultados, docs, resumen, factor_mm, sufijo="tab")


_panel_envuelto = _envolver_en_fragment(_cuerpo_panel)


def panel_asistente(resultados: dict | None, params=None,
                    serie: dict | None = None, factor_mm: float = 1000.0):
    """El asistente como tab. `resultados` FÍSICOS (STD) o None."""
    _panel_envuelto(resultados, params, serie, factor_mm)
