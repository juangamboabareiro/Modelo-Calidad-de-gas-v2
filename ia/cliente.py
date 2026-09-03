"""
Cliente de IA: elige el proveedor y expone UNA interfaz al resto del codigo.
============================================================================

Nadie fuera de `ia/` sabe con quien estamos hablando. `ia/proveedores.py` sabe
hablar con cada API; este modulo decide cual y normaliza lo que devuelven.

CONFIGURACION (`.streamlit/secrets.toml` o variables de entorno)
----------------------------------------------------------------
    ANTHROPIC_API_KEY = "sk-ant-..."     # si esta, se usa Anthropic
    GEMINI_API_KEY    = "AIza..."        # si esta, se usa Gemini

    ASISTENTE_PROVEEDOR = "gemini"       # opcional: forzar uno de los dos
    ASISTENTE_MODELO    = "..."          # opcional: pisar el modelo
    ASISTENTE_BOTS      = "docs"         # opcional: que bots tienen IA

Sin ninguna key, la capa de IA queda apagada y el asistente funciona igual con
el buscador y el explicador.

EL INTERRUPTOR POR BOT (`ASISTENTE_BOTS`)
-----------------------------------------
Los tres bots no mandan lo mismo:

    docs       -> la documentacion del proyecto
    resultados -> la documentacion + los NUMEROS de la corrida
    agente     -> lo mismo, y ademas opera el sandbox

Con una key de tier gratuito de Gemini, lo que se envia **puede usarse para
entrenar y ser visto por revisores humanos**, y Google pide explicitamente no
mandar informacion confidencial a los servicios no pagos. Por eso el DEFAULT
con Gemini es `docs` solamente: es una decision de politica de datos, no una
limitacion tecnica.

Para habilitar el resto hay que decirlo:

    ASISTENTE_BOTS = "docs,resultados,agente"

Con Anthropic el default son los tres, porque la API de pago no entrena con lo
que se le manda. Igual conviene validarlo con seguridad de la informacion antes
de usarlo con datos reales: la politica de la empresa manda sobre este archivo.
"""

from __future__ import annotations

from ia.proveedores import PROVEEDORES, Anthropic, Gemini, SinAPIKey, leer_secreto

MAX_TOKENS = 4096

BOTS = ("docs", "resultados", "agente")

# Que bots llevan IA si nadie configuro `ASISTENTE_BOTS`. Ver el encabezado:
# con Gemini gratis, solo el que no manda numeros de produccion.
BOTS_DEFAULT = {"anthropic": BOTS, "gemini": ("docs",)}

__all__ = ["SinAPIKey", "hay_credencial", "modelo_configurado", "proveedor",
           "explicar_error",
           "etiqueta_proveedor", "bot_habilitado", "bots_habilitados",
           "stream_texto", "correr_agente", "leer_uso", "resumen_uso",
           "costo_estimado", "aviso_datos"]


# ===========================================================================
# Que proveedor
# ===========================================================================

def proveedor():
    """La clase del proveedor en uso, o None si no hay credencial.

    Si estan las dos keys y nadie eligio, gana Anthropic: es la que no entrena
    con lo que se le manda, o sea el default mas conservador.
    """
    forzado = (leer_secreto("ASISTENTE_PROVEEDOR") or "").strip().lower()
    if forzado in PROVEEDORES:
        p = PROVEEDORES[forzado]
        return p if p.hay_credencial() else None

    for p in (Anthropic, Gemini):
        if p.hay_credencial():
            return p
    return None


def hay_credencial() -> bool:
    return proveedor() is not None


def etiqueta_proveedor() -> str:
    p = proveedor()
    return p.etiqueta if p else "(sin proveedor)"


def modelo_configurado() -> str:
    p = proveedor()
    if p is None:
        return "(sin modelo)"
    return leer_secreto("ASISTENTE_MODELO") or p.modelo_default


def es_gemini_gratis() -> bool:
    """Heurística: Gemini con una key sin billing es tier gratuito.

    No hay forma de saberlo desde la API, así que se asume lo más cauto: si el
    proveedor es Gemini, se avisa de los términos del tier gratuito salvo que
    el usuario declare `GEMINI_TIER_PAGO = true`.
    """
    if proveedor() is not Gemini:
        return False
    return not (leer_secreto("GEMINI_TIER_PAGO") or "").strip().lower() \
        in ("1", "true", "si", "sí", "yes")


def aviso_datos() -> str:
    """La línea que la UI muestra sobre qué pasa con lo que se envía."""
    p = proveedor()
    if p is None:
        return ""
    if p is Gemini and es_gemini_gratis():
        return ("⚠️ Gemini en tier **gratuito**: lo que enviés puede usarse "
                "para entrenar sus modelos y ser revisado por personas. No "
                "mandes nada confidencial.")
    return (f"Lo que preguntes y el contexto viajan a la API de {p.etiqueta}.")


# ===========================================================================
# Que bots
# ===========================================================================

def bots_habilitados() -> tuple[str, ...]:
    p = proveedor()
    if p is None:
        return ()
    crudo = leer_secreto("ASISTENTE_BOTS")
    if not crudo:
        # El default de Gemini se limita por los términos del tier GRATUITO. Si
        # el usuario declaró que su key es de pago, esa razón desaparece y
        # valen los tres, igual que con Anthropic.
        if p is Gemini and not es_gemini_gratis():
            return BOTS
        return BOTS_DEFAULT.get(p.nombre, BOTS)
    if crudo.strip().lower() in ("todos", "all", "*"):
        return BOTS
    pedidos = {b.strip().lower() for b in crudo.split(",")}
    return tuple(b for b in BOTS if b in pedidos)


def bot_habilitado(bot: str) -> bool:
    return bot in bots_habilitados()


def motivo_bot_apagado(bot: str) -> str:
    """Por qué este bot no tiene IA, en una línea para la UI."""
    if not hay_credencial():
        return ""
    if bot_habilitado(bot):
        return ""
    if proveedor() is Gemini and es_gemini_gratis() and bot != "docs":
        return ("Apagado a propósito: este bot enviaría **números de la "
                "corrida**, y el tier gratuito de Gemini puede usar lo que "
                "recibe para entrenar. Si tu key es de pago, declaralo con "
                "`GEMINI_TIER_PAGO = true`. Para habilitarlo igual, "
                '`ASISTENTE_BOTS = "docs,resultados,agente"`.')
    return ('No está en `ASISTENTE_BOTS`. Para habilitarlo, agregalo: '
            '`ASISTENTE_BOTS = "docs,resultados,agente"`.')


# ===========================================================================
# Uso y costo
# ===========================================================================

def leer_uso(uso) -> dict:
    """Normaliza el uso que ya viene normalizado por el adaptador."""
    return dict(uso or {})


def costo_estimado(uso: dict, modelo: str | None = None) -> float | None:
    """USD aproximados. None si no conocemos el precio (o si es gratis)."""
    p = proveedor()
    if p is None or not uso:
        return None
    precios = p.precios.get(modelo or modelo_configurado())
    if not precios:
        return None
    return (uso.get("entrada", 0) * precios["in"]
            + uso.get("cache_escrito", 0) * precios["cache_write"]
            + uso.get("cache_leido", 0) * precios["cache_read"]
            + uso.get("salida", 0) * precios["out"]) / 1_000_000


def resumen_uso(uso: dict, modelo: str | None = None) -> str:
    """Una línea para el pie de la respuesta en la UI."""
    if not uso:
        return ""
    partes = [f"{uso.get('entrada', 0):,} in", f"{uso.get('salida', 0):,} out"]
    if uso.get("cache_leido"):
        partes.append(f"{uso['cache_leido']:,} desde caché")
    elif uso.get("cache_escrito"):
        partes.append(f"{uso['cache_escrito']:,} escritos al caché")
    texto = " · ".join(partes)
    costo = costo_estimado(uso, modelo)
    if costo is not None:
        texto += f" · ~US$ {costo:.4f}"
    elif proveedor() is Gemini and es_gemini_gratis():
        texto += " · sin costo (tier gratuito)"
    return texto


# ===========================================================================
# Llamadas
# ===========================================================================

def explicar_error(e: Exception) -> str:
    """Traduce un error de la API a algo accionable para el usuario.

    Los tres que aparecen de verdad, en orden de frecuencia con Gemini gratis:
    rate limit, modelo inexistente y credencial mala. Sin esto la UI muestra el
    repr de una excepcion de la SDK, que no le dice nada a nadie.
    """
    texto = str(e)
    bajo = texto.lower()

    # El 503 va ANTES del 429: cuando el modelo esta saturado, Google a veces
    # devuelve los dos codigos en el mismo mensaje, y la causa real es la
    # sobrecarga, no la cuota del usuario. Decirle "llegaste a tu limite" a
    # alguien que no llego lo manda a buscar el problema donde no esta.
    if "503" in texto or "unavailable" in bajo or "overloaded" in bajo \
            or "high demand" in bajo:
        return ("El modelo está saturado del lado de Google (pico de demanda), "
                "no es un problema de tu configuración ni de tu cuota. Ya "
                "reintenté solo unas cuantas veces. Opciones: esperar unos "
                "minutos, o probar `ASISTENTE_MODELO = \"gemini-flash-lite-latest\"` "
                "en los secretos, que suele estar menos congestionado. Al tier "
                "gratuito le cortan capacidad primero cuando hay picos.")

    if "429" in texto or "resource_exhausted" in bajo or "quota" in bajo \
            or "rate limit" in bajo:
        extra = ""
        if proveedor() is Gemini and es_gemini_gratis():
            extra = (" El tier gratuito permite pocas llamadas por minuto y un "
                     "turno del agente son varias seguidas, así que es fácil "
                     "chocarlo. Esperá un minuto y pedile UN cambio por vez, o "
                     "habilitá billing para subir el límite.")
        return f"Llegaste al límite de llamadas por minuto.{extra}"

    if "sigue sin responder despues de" in texto:
        # Viene de `con_reintentos`: ya se agotaron los intentos y el mensaje
        # trae el ultimo error adentro. Se pasa tal cual, que ya es claro.
        return texto

    if "404" in texto or "not found" in bajo:
        return (f"El modelo `{modelo_configurado()}` no existe o tu key no lo "
                "tiene habilitado. Corré `python tools/probar_asistente.py "
                "--modelos` para ver los disponibles y fijá uno con "
                "`ASISTENTE_MODELO` en los secretos.")

    if "401" in texto or "403" in texto or "api key" in bajo \
            or "permission" in bajo:
        return ("La credencial fue rechazada. Revisá que la key esté completa "
                "y sin espacios en `secrets.toml`.")

    if "safety" in bajo or "blocked" in bajo:
        return ("El proveedor bloqueó la respuesta por sus filtros de "
                "contenido. Reformulá el pedido.")

    return f"{type(e).__name__}: {texto}"


def _proveedor_o_error():
    p = proveedor()
    if p is None:
        raise SinAPIKey(
            "No hay credencial de IA. Cargá ANTHROPIC_API_KEY o "
            "GEMINI_API_KEY en `.streamlit/secrets.toml`.")
    return p


def stream_texto(system, mensajes: list[dict], max_tokens: int = MAX_TOKENS,
                 registro_uso: dict | None = None):
    """Generador de texto para `st.write_stream`. Para los bots SIN tools.

    `registro_uso`, si se pasa, se rellena al terminar el stream. Es un dict de
    salida y no un valor de retorno porque un generador ya usa el `return`.
    """
    p = _proveedor_o_error()
    yield from p.stream(modelo_configurado(), system, mensajes, max_tokens,
                        registro_uso)


def correr_agente(system, mensajes: list[dict], tools: list[dict],
                  ejecutar, on_tool, max_tokens: int = MAX_TOKENS):
    """El loop de herramientas. Devuelve (texto_final, uso_acumulado).

    `ejecutar(nombre, argumentos) -> str` corre la herramienta.
    `on_tool(nombre, argumentos, salida)` es para mostrarla en la UI.

    El loop en sí vive en el adaptador: el formato de la conversación con
    herramientas es lo más distinto entre las dos APIs (bloques `tool_use` vs
    `function_call` en `parts`), y escribirlo dos veces en la UI sería
    garantizar que uno de los dos se desactualice.
    """
    p = _proveedor_o_error()
    return p.agente(modelo_configurado(), system, mensajes, tools,
                    ejecutar, on_tool, max_tokens)
