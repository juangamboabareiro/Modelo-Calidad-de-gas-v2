"""
Cliente de la API de Anthropic: la UNICA puerta de salida a la IA.
==================================================================

Todo lo que llame a la API pasa por aca. Si manana cambia el proveedor, el
modelo o la forma de autenticar, se toca este archivo y nada mas.

Configuracion (en orden de prioridad):

  1. `st.secrets["ANTHROPIC_API_KEY"]`  -> .streamlit/secrets.toml (deploy)
  2. variable de entorno ANTHROPIC_API_KEY (desarrollo local)

El modelo se puede pisar con `ASISTENTE_MODELO` (secreto o entorno).

PROMPT CACHING
--------------
El asistente manda la documentacion entera en CADA pregunta. Sin caching eso
se paga a precio de input completo todas las veces; con caching, la segunda
pregunta en adelante lo lee a 1/10 del precio.

Por eso `system` NO es un string sino una LISTA de bloques, ordenados de mas
estable a mas volatil, con el punto de corte del cache al final de lo estable:

    [0] documentacion            <- cache_control, identico en los tres bots
    [1] instrucciones del bot    <- corto, cambia por bot
    [2] resultados de la corrida <- cambia en cada corrida

El prefijo se arma en orden `tools -> system -> messages`, asi que todo lo que
esta antes del corte entra al cache. Como el bloque [0] es identico para los
tres bots, comparten la misma entrada (salvo el agente, que ademas lleva
`tools` adelante y por eso escribe la suya).

Un bloque tiene que superar el minimo del modelo para que el cache se active
(1.024 tokens en Sonnet 5). La documentacion del proyecto lo supera holgado;
si algun dia quedara por debajo, la API no da error, simplemente no cachea.

Requiere `anthropic` en requirements.txt.
"""

from __future__ import annotations

import os

MODELO_DEFAULT = "claude-sonnet-5"

# Tope de tokens de salida por respuesta. 4096 alcanza para cualquier
# explicacion; el agente usa respuestas cortas entre herramientas.
MAX_TOKENS = 4096

# Precios en USD por millon de tokens. Solo para el cartelito de costo de la
# UI: es una ESTIMACION, la fuente de verdad es la consola de Anthropic.
# Si cambias de modelo, actualiza esto o el numero va a mentir.
PRECIOS = {
    "claude-sonnet-5": {"in": 2.0, "out": 10.0, "cache_write": 2.5, "cache_read": 0.20},
    "claude-opus-5": {"in": 5.0, "out": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0, "cache_write": 1.25, "cache_read": 0.10},
}


class SinAPIKey(RuntimeError):
    """No hay credencial configurada. La UI la atrapa y muestra el como."""


def _leer_secreto(nombre: str) -> str | None:
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


def hay_credencial() -> bool:
    return _leer_secreto("ANTHROPIC_API_KEY") is not None


def modelo_configurado() -> str:
    return _leer_secreto("ASISTENTE_MODELO") or MODELO_DEFAULT


def obtener_cliente():
    """Devuelve el cliente de la SDK, o levanta con un mensaje accionable."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "Falta la SDK: agrega `anthropic` a requirements.txt "
            "(`pip install anthropic`) y redeploya."
        ) from e

    key = _leer_secreto("ANTHROPIC_API_KEY")
    if not key:
        raise SinAPIKey(
            "No hay ANTHROPIC_API_KEY. Cargala en `.streamlit/secrets.toml` "
            '(`ANTHROPIC_API_KEY = "sk-ant-..."`) o como variable de entorno.'
        )
    return anthropic.Anthropic(api_key=key)


# ===========================================================================
# Uso y costo
# ===========================================================================

def leer_uso(usage) -> dict:
    """Normaliza el `usage` de la respuesta a un dict plano.

    Los cuatro numeros que importan:
      entrada        tokens NUEVOS (los que van despues del corte del cache)
      cache_escrito  tokens que se guardaron en el cache (se pagan 1.25x)
      cache_leido    tokens que vinieron del cache (se pagan 0.1x)
      salida         tokens generados
    """
    if usage is None:
        return {}
    g = (lambda n: int(getattr(usage, n, 0) or 0))
    return {
        "entrada": g("input_tokens"),
        "cache_escrito": g("cache_creation_input_tokens"),
        "cache_leido": g("cache_read_input_tokens"),
        "salida": g("output_tokens"),
    }


def costo_estimado(uso: dict, modelo: str | None = None) -> float | None:
    """USD aproximados de una llamada. None si no conocemos el precio."""
    precios = PRECIOS.get(modelo or modelo_configurado())
    if not precios or not uso:
        return None
    return (
        uso.get("entrada", 0) * precios["in"]
        + uso.get("cache_escrito", 0) * precios["cache_write"]
        + uso.get("cache_leido", 0) * precios["cache_read"]
        + uso.get("salida", 0) * precios["out"]
    ) / 1_000_000


def resumen_uso(uso: dict, modelo: str | None = None) -> str:
    """Una linea para el pie de la respuesta en la UI."""
    if not uso:
        return ""
    costo = costo_estimado(uso, modelo)
    partes = [f"{uso.get('entrada', 0):,} in", f"{uso.get('salida', 0):,} out"]
    if uso.get("cache_leido"):
        partes.append(f"{uso['cache_leido']:,} desde caché")
    elif uso.get("cache_escrito"):
        partes.append(f"{uso['cache_escrito']:,} escritos al caché")
    texto = " · ".join(partes)
    if costo is not None:
        texto += f" · ~US$ {costo:.4f}"
    return texto


# ===========================================================================
# Llamadas
# ===========================================================================

def stream_texto(system: list[dict] | str, messages: list[dict],
                 max_tokens: int = MAX_TOKENS, registro_uso: dict | None = None):
    """Generador de texto para `st.write_stream`. Para los bots SIN tools.

    `system` es la lista de bloques (ver el encabezado del modulo); se acepta
    un string suelto para no romper llamadas viejas.

    `registro_uso`, si se pasa, se rellena con el uso de la llamada cuando
    termina el stream. Es un dict de salida y no un valor de retorno porque un
    generador ya usa el `return` para cortar.
    """
    cliente = obtener_cliente()
    with cliente.messages.stream(
        model=modelo_configurado(),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as stream:
        for texto in stream.text_stream:
            yield texto

        if registro_uso is not None:
            try:
                final = stream.get_final_message()
                registro_uso.update(leer_uso(getattr(final, "usage", None)))
            except Exception:  # noqa: BLE001 - el uso es informativo, no critico
                pass


def completar(system: list[dict] | str, messages: list[dict],
              tools: list[dict] | None = None, max_tokens: int = MAX_TOKENS):
    """Una llamada sin streaming. Devuelve el Message crudo de la SDK.

    Es la que usa el agente: con tools el streaming complica el loop y no
    aporta, porque las respuestas entre herramientas son cortas.
    """
    cliente = obtener_cliente()
    kwargs = dict(
        model=modelo_configurado(),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    if tools:
        kwargs["tools"] = tools
    return cliente.messages.create(**kwargs)
