"""
Adaptadores de proveedor: Anthropic y Gemini detras de una interfaz comun.
==========================================================================

`ia/cliente.py` elige el proveedor; este modulo sabe hablar con cada uno. La
interfaz que los dos cumplen:

    hay_credencial()                        -> bool
    modelo_default                          -> str
    stream(system, mensajes, max_tokens)    -> generator de texto
                                               (deja el uso en `registro_uso`)
    agente(system, mensajes, tools, ...)    -> (texto_final, uso)

`system` siempre llega como la LISTA DE BLOQUES de `ia/contexto.py`. Cada
adaptador la traduce a lo que su API espera; el resto del codigo no se entera.

POR QUE EL LOOP DEL AGENTE VIVE ACA Y NO EN LA UI
-------------------------------------------------
Porque el formato de la conversacion con herramientas es lo mas distinto entre
las dos APIs: Anthropic va con bloques `tool_use` / `tool_result` en el
historial, Gemini con `function_call` / `function_response` en `parts`. Si el
loop viviera en la UI habria que escribirlo dos veces y mantener los dos.
Aca la UI pasa dos callbacks —como ejecutar una herramienta y que hacer para
mostrarla— y no sabe de que proveedor se trata.
"""

from __future__ import annotations

import os

MAX_ITERACIONES = 12

# Gemini gratis limita a ~10 requests por minuto. Un turno del agente son
# varias llamadas seguidas, asi que con el tope de Anthropic (12) se choca el
# rate limit a mitad de camino y el usuario ve un error en vez de una
# respuesta. Mejor cortar antes y decirlo.
MAX_ITERACIONES_GEMINI = 6


class SinAPIKey(RuntimeError):
    """No hay credencial configurada. La UI la atrapa y muestra el como."""


# Reintentos ante errores TRANSITORIOS del proveedor.
#
# Los dos que aparecen de verdad con el tier gratuito de Gemini:
#   503 UNAVAILABLE / "model is overloaded" -> el modelo esta saturado. Al tier
#       gratuito le cortan capacidad primero cuando hay picos de demanda, asi
#       que es frecuente y NO es un problema de configuracion.
#   429 RESOURCE_EXHAUSTED                  -> rate limit propio.
#
# Los dos se arreglan esperando, asi que reintentar es la respuesta correcta;
# mostrarle el error al usuario para que apriete de nuevo es hacerle hacer a
# mano lo que el codigo puede hacer solo.
#
# Lo que NO se reintenta: 401/403 (credencial), 404 (modelo inexistente),
# 400 (pedido mal armado). Esos no mejoran esperando y reintentarlos solo
# demora el mensaje util.
REINTENTOS = 3
ESPERA_BASE = 2.0     # segundos; se duplica en cada intento (2, 4, 8)


def es_transitorio(e: Exception) -> bool:
    t = str(e).lower()
    return any(m in t for m in (
        "503", "unavailable", "overloaded", "high demand", "try again",
        "429", "resource_exhausted", "rate limit", "quota exceeded",
        "500", "internal error", "deadline", "timeout",
    ))


def con_reintentos(fn, descripcion: str = "la llamada"):
    """Corre `fn()` reintentando los errores transitorios, con backoff.

    Devuelve lo que devuelva `fn`. Si se agotan los intentos, levanta el
    ultimo error con el contexto agregado, para que el mensaje de la UI diga
    que ya se reintento y no parezca que fallo al primer golpe.
    """
    import time

    ultimo = None
    for intento in range(REINTENTOS):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if not es_transitorio(e):
                raise
            ultimo = e
            if intento < REINTENTOS - 1:
                time.sleep(ESPERA_BASE * (2 ** intento))

    raise RuntimeError(
        f"El proveedor sigue sin responder despues de {REINTENTOS} intentos "
        f"({descripcion}). Ultimo error: {ultimo}") from ultimo


def leer_secreto(nombre: str) -> str | None:
    """Busca en st.secrets primero, en el entorno despues.

    El import de streamlit va adentro para que este modulo se pueda usar sin
    streamlit (por ejemplo desde `tools/probar_asistente.py`), y el acceso a
    `st.secrets` va en try porque levanta si no existe ningun secrets.toml.
    """
    try:
        import streamlit as st
        valor = st.secrets.get(nombre)  # type: ignore[attr-defined]
        if valor:
            return str(valor)
    except Exception:
        pass
    return os.environ.get(nombre) or None


def _texto_de_bloques(system: list[dict] | str) -> str:
    """Los bloques de `system` aplanados a un string.

    Es lo que necesita cualquier API que no tenga bloques de sistema. Se pierde
    el punto de corte del cache de Anthropic, que es informacion que solo esa
    API usa.
    """
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system)


# ===========================================================================
# Anthropic
# ===========================================================================

class Anthropic:
    nombre = "anthropic"
    etiqueta = "Anthropic"
    modelo_default = "claude-sonnet-5"
    clave_secreto = "ANTHROPIC_API_KEY"
    paquete = "anthropic"

    # USD por millon de tokens. Solo para el cartelito de la UI: la fuente de
    # verdad es la consola del proveedor.
    precios = {
        "claude-sonnet-5": {"in": 2.0, "out": 10.0,
                            "cache_write": 2.5, "cache_read": 0.20},
        "claude-opus-5": {"in": 5.0, "out": 25.0,
                          "cache_write": 6.25, "cache_read": 0.50},
        "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0,
                                      "cache_write": 1.25, "cache_read": 0.10},
    }

    @classmethod
    def hay_credencial(cls) -> bool:
        return leer_secreto(cls.clave_secreto) is not None

    @classmethod
    def cliente(cls):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "Falta la SDK: agregá `anthropic` a requirements.txt."
            ) from e
        key = leer_secreto(cls.clave_secreto)
        if not key:
            raise SinAPIKey(
                f"No hay {cls.clave_secreto}. Cargala en "
                "`.streamlit/secrets.toml` o como variable de entorno.")
        return anthropic.Anthropic(api_key=key)

    @staticmethod
    def _uso(usage) -> dict:
        if usage is None:
            return {}
        g = (lambda n: int(getattr(usage, n, 0) or 0))
        return {"entrada": g("input_tokens"),
                "cache_escrito": g("cache_creation_input_tokens"),
                "cache_leido": g("cache_read_input_tokens"),
                "salida": g("output_tokens")}

    @classmethod
    def stream(cls, modelo, system, mensajes, max_tokens, registro_uso=None):
        with cls.cliente().messages.stream(
            model=modelo, max_tokens=max_tokens, system=system,
            messages=mensajes,
        ) as stream:
            for texto in stream.text_stream:
                yield texto
            if registro_uso is not None:
                try:
                    final = stream.get_final_message()
                    registro_uso.update(cls._uso(getattr(final, "usage", None)))
                except Exception:  # noqa: BLE001 - el uso es informativo
                    pass

    @classmethod
    def agente(cls, modelo, system, mensajes, tools, ejecutar, on_tool,
               max_tokens, max_iter=MAX_ITERACIONES):
        cliente = cls.cliente()
        # Copia: el historial de herramientas es interno a esta llamada y no
        # tiene por que volver a la UI.
        hist = list(mensajes)
        uso_total: dict = {}

        for _ in range(max_iter):
            r = con_reintentos(
                lambda: cliente.messages.create(
                    model=modelo, max_tokens=max_tokens, system=system,
                    messages=hist, tools=tools),
                "un paso del agente")

            for k, v in cls._uso(getattr(r, "usage", None)).items():
                uso_total[k] = uso_total.get(k, 0) + v

            if r.stop_reason != "tool_use":
                texto = "\n".join(b.text for b in r.content
                                  if getattr(b, "type", "") == "text").strip()
                return texto or "(el modelo no devolvió texto)", uso_total

            hist.append({"role": "assistant", "content": r.content})
            respuestas = []
            for b in r.content:
                if getattr(b, "type", "") != "tool_use":
                    continue
                salida = ejecutar(b.name, b.input)
                on_tool(b.name, b.input, salida)
                respuestas.append({"type": "tool_result",
                                   "tool_use_id": b.id, "content": salida})
            hist.append({"role": "user", "content": respuestas})

        return (f"Corté a las {max_iter} iteraciones para no entrar en un "
                "ciclo. Lo hecho quedó en el sandbox; pedime que siga."), uso_total


# ===========================================================================
# Gemini
# ===========================================================================

class Gemini:
    nombre = "gemini"
    etiqueta = "Google Gemini"
    # UN ALIAS, NO UNA VERSION. Los nombres de modelo de Gemini rotan
    # rapidisimo: 3.8 Flash salio tres semanas despues de 3.7, y las versiones
    # 2.x se van apagando con fecha (2.0 en junio de 2026, 2.5 en octubre).
    # Cualquier numero escrito aca queda viejo en semanas y devuelve 404 — ya
    # paso con `gemini-2.5-flash`. `gemini-flash-latest` apunta siempre al
    # Flash estable del momento.
    #
    # La contra del alias: el modelo cambia abajo sin avisar, asi que una
    # respuesta puede mejorar o empeorar de un dia para el otro sin que nadie
    # toque nada. Para este uso (explicar documentacion, operar el sandbox) es
    # un precio razonable a cambio de no romperse cada mes; si alguna vez hace
    # falta reproducibilidad, se fija una version con ASISTENTE_MODELO.
    #
    # Alternativa: `gemini-flash-lite-latest` es mas barato y —lo que importa
    # mas en el tier gratuito— tiene mas requests por minuto, asi que aguanta
    # mejor al agente del sandbox. A cambio de menos capacidad de razonamiento.
    #
    # Y del lado del Pro: el tier gratuito NO lo incluye desde el 1/4/2026, asi
    # que un modelo Pro por default daria 429 o 404 con una key gratuita.
    #
    # Para ver que tiene habilitado TU key:
    #     python tools/probar_asistente.py --modelos
    modelo_default = "gemini-flash-latest"
    clave_secreto = "GEMINI_API_KEY"
    paquete = "google-genai"

    # Sin precios: en el tier gratuito no hay costo, y para el pago los valores
    # cambian seguido. La UI muestra tokens y no inventa un número en dólares.
    precios: dict = {}

    @classmethod
    def hay_credencial(cls) -> bool:
        return leer_secreto(cls.clave_secreto) is not None

    @classmethod
    def cliente(cls):
        try:
            from google import genai
        except ImportError as e:
            raise RuntimeError(
                "Falta la SDK: agregá `google-genai` a requirements.txt. "
                "OJO: NO es `google-generativeai`, que está archivada."
            ) from e
        key = leer_secreto(cls.clave_secreto)
        if not key:
            raise SinAPIKey(
                f"No hay {cls.clave_secreto}. Sacala de Google AI Studio y "
                "cargala en `.streamlit/secrets.toml`.")
        return genai.Client(api_key=key)

    @staticmethod
    def _uso(metadata) -> dict:
        if metadata is None:
            return {}
        g = (lambda n: int(getattr(metadata, n, 0) or 0))
        return {"entrada": g("prompt_token_count"),
                "cache_leido": g("cached_content_token_count"),
                "cache_escrito": 0,
                "salida": g("candidates_token_count")}

    @classmethod
    def _config(cls, system, max_tokens, tools=None):
        """El equivalente de `system` + `tools` en esta API.

        Gemini no tiene bloques de sistema: van todos aplanados en
        `system_instruction`. Se pierde el punto de corte del prompt caching de
        Anthropic, que era información que solo esa API usaba. Los modelos 2.5
        hacen caching implícito, sin nada que declarar.
        """
        from google.genai import types
        kwargs = dict(system_instruction=_texto_de_bloques(system),
                      max_output_tokens=max_tokens)
        if tools:
            kwargs["tools"] = [types.Tool(
                function_declarations=[cls._declarar(t) for t in tools])]
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _declarar(tool: dict) -> dict:
        """Un esquema de herramienta de Anthropic traducido a Gemini.

        El JSON Schema es casi el mismo; cambia el nombre del campo
        (`input_schema` -> `parameters`). La excepción importante: una
        herramienta SIN parámetros tiene que ir sin `parameters`, porque un
        objeto con `properties` vacío hace que la API rechace la declaración.
        """
        esquema = dict(tool.get("input_schema") or {})
        declaracion = {"name": tool["name"],
                       "description": tool.get("description", "")}
        if esquema.get("properties"):
            declaracion["parameters"] = esquema
        return declaracion

    @staticmethod
    def _a_contents(mensajes: list[dict]):
        """Los mensajes normalizados al formato de Gemini.

        Dos diferencias: el rol del asistente se llama "model", y el contenido
        va en `parts`. Los mensajes que llegan acá son siempre de texto — el
        historial con herramientas lo arma `agente` por su cuenta.
        """
        from google.genai import types
        contents = []
        for m in mensajes:
            rol = "model" if m["role"] == "assistant" else "user"
            contents.append(types.Content(
                role=rol, parts=[types.Part(text=str(m["content"]))]))
        return contents

    @classmethod
    def stream(cls, modelo, system, mensajes, max_tokens, registro_uso=None):
        cliente = cls.cliente()
        contents = cls._a_contents(mensajes)
        config = cls._config(system, max_tokens)

        # El reintento envuelve la APERTURA del stream, no su consumo: si el
        # modelo ya empezo a escribir y se corta, reintentar duplicaria el
        # texto que el usuario vio. Un 503 aparece casi siempre al abrir.
        iterador = con_reintentos(
            lambda: cliente.models.generate_content_stream(
                model=modelo, contents=contents, config=config),
            "abrir el stream")

        ultimo = None
        for trozo in iterador:
            ultimo = trozo
            if trozo.text:
                yield trozo.text

        if registro_uso is not None and ultimo is not None:
            try:
                registro_uso.update(
                    cls._uso(getattr(ultimo, "usage_metadata", None)))
            except Exception:  # noqa: BLE001
                pass

    @classmethod
    def agente(cls, modelo, system, mensajes, tools, ejecutar, on_tool,
               max_tokens, max_iter=MAX_ITERACIONES_GEMINI):
        from google.genai import types

        cliente = cls.cliente()
        contents = cls._a_contents(mensajes)
        config = cls._config(system, max_tokens, tools)
        uso_total: dict = {}

        for _ in range(max_iter):
            # Cada paso del agente reintenta por su cuenta: un 503 en la
            # iteracion 4 no tiene por que tirar abajo las tres anteriores,
            # que ya modificaron el sandbox.
            r = con_reintentos(
                lambda: cliente.models.generate_content(
                    model=modelo, contents=contents, config=config),
                "un paso del agente")

            for k, v in cls._uso(getattr(r, "usage_metadata", None)).items():
                uso_total[k] = uso_total.get(k, 0) + v

            # Las llamadas a herramientas vienen como `function_call` dentro de
            # las parts, no como un `stop_reason` aparte.
            llamadas = []
            partes = []
            candidatos = getattr(r, "candidates", None) or []
            if candidatos and getattr(candidatos[0], "content", None):
                partes = list(getattr(candidatos[0].content, "parts", None) or [])
            for parte in partes:
                fc = getattr(parte, "function_call", None)
                if fc is not None:
                    llamadas.append(fc)

            if not llamadas:
                return (r.text or "(el modelo no devolvió texto)").strip(), uso_total

            # El turno del modelo va ENTERO al historial, y las respuestas de
            # las herramientas en un turno de usuario, una part por llamada.
            contents.append(types.Content(role="model", parts=partes))
            respuestas = []
            for fc in llamadas:
                args = dict(fc.args or {})
                salida = ejecutar(fc.name, args)
                on_tool(fc.name, args, salida)
                respuestas.append(types.Part.from_function_response(
                    name=fc.name, response={"resultado": salida}))
            contents.append(types.Content(role="user", parts=respuestas))

        return (f"Corté a las {max_iter} iteraciones. Con el tier gratuito el "
                "límite es de pocas llamadas por minuto, así que conviene "
                "pedir de a un cambio. Lo hecho quedó en el sandbox."), uso_total

    @classmethod
    def listar_modelos(cls) -> list[str]:
        """Los modelos que ESTA key tiene habilitados.

        Existe porque los nombres de modelo de Gemini rotan rápido y un default
        escrito en el código envejece. Preguntarle a la API es más confiable.
        """
        modelos = []
        for m in cls.cliente().models.list():
            acciones = getattr(m, "supported_actions", None) or []
            if not acciones or "generateContent" in acciones:
                modelos.append(str(getattr(m, "name", "")).replace("models/", ""))
        return sorted(modelos)


PROVEEDORES = {p.nombre: p for p in (Anthropic, Gemini)}
