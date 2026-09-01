"""
Cliente de la API de Anthropic: la UNICA puerta de salida a la IA.
==================================================================

Todo lo que llame a la API pasa por aca. Si manana cambia el proveedor, el
modelo o la forma de autenticar, se toca este archivo y nada mas.

Configuracion (en orden de prioridad):

  1. `st.secrets["ANTHROPIC_API_KEY"]`  -> .streamlit/secrets.toml (deploy)
  2. variable de entorno ANTHROPIC_API_KEY (desarrollo local)

El modelo se puede pisar con `st.secrets["ASISTENTE_MODELO"]` o la variable
de entorno del mismo nombre. El default es Sonnet: buen balance costo/calidad
para explicar documentacion. Para el agente del sandbox conviene el mismo o
uno superior, nunca Haiku (usa herramientas y se pierde).

Requiere `anthropic` en requirements.txt.
"""

from __future__ import annotations

import os

MODELO_DEFAULT = "claude-sonnet-5"

# Tope de tokens de salida por respuesta. 4096 alcanza para cualquier
# explicacion; el agente del sandbox usa respuestas cortas entre tools.
MAX_TOKENS = 4096


class SinAPIKey(RuntimeError):
    """No hay credencial configurada. La UI la atrapa y muestra el como."""


def _leer_secreto(nombre: str) -> str | None:
    """Busca en st.secrets primero, en el entorno despues.

    El import de streamlit va adentro para que este modulo se pueda testear
    sin streamlit instalado, y el acceso a `st.secrets` va en try porque
    levanta si no existe ningun secrets.toml.
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


def stream_texto(system: str, messages: list[dict], max_tokens: int = MAX_TOKENS):
    """Generador de texto para `st.write_stream`. Para los bots SIN tools.

    `messages` en el formato de la API: [{"role": "user"|"assistant",
    "content": str}, ...].
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


def completar(system: str, messages: list[dict], tools: list[dict] | None = None,
              max_tokens: int = MAX_TOKENS):
    """Una llamada sin streaming. Devuelve el Message crudo de la SDK.

    Es la que usa el agente del sandbox: con tools el streaming complica el
    loop y no aporta (las respuestas entre herramientas son cortas).
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
