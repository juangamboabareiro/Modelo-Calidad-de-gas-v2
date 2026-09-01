"""
Contextos para los asistentes: que sabe cada bot antes de leer la pregunta.
===========================================================================

Dos fuentes, dos funciones:

  - `cargar_docs()`          -> los .md de `docs/` (bot 1 y base de todos)
  - `resumen_resultados()`   -> la corrida vigente, aplanada a texto (bot 2 y 3)

La regla es que TODO lo que un bot afirma tiene que poder rastrearse a uno de
estos dos bloques. Por eso los system prompts (abajo) insisten en "si no esta
en el contexto, decilo".
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Presupuesto de caracteres para los docs. ~400k chars son ~100k tokens: entra
# holgado en el contexto del modelo junto con el resumen de resultados.
MAX_CHARS_DOCS = 400_000

# Cuantas filas de una tabla se vuelcan al contexto antes de truncar.
MAX_FILAS_TABLA = 60


# ===========================================================================
# Documentacion (bot 1)
# ===========================================================================

def cargar_docs(carpeta: str | Path = "docs",
                max_chars: int = MAX_CHARS_DOCS) -> tuple[str, list[str]]:
    """Concatena los .md de `docs/` (recursivo). Devuelve (texto, avisos).

    El orden es alfabetico por ruta, que en este repo deja changelog, decisiones
    y linaje en un orden razonable. Cada archivo va precedido por su ruta para
    que el modelo pueda citar "segun docs/validaciones.md".
    """
    carpeta = Path(carpeta)
    avisos: list[str] = []

    if not carpeta.is_dir():
        return "", [f"No existe la carpeta `{carpeta}`: el asistente de "
                    "documentacion no tiene material para responder."]

    partes: list[str] = []
    usado = 0
    for ruta in sorted(carpeta.rglob("*.md")):
        try:
            texto = ruta.read_text(encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - un md ilegible no tumba el resto
            avisos.append(f"No se pudo leer `{ruta}`: {e}")
            continue

        bloque = f"\n\n===== {ruta.as_posix()} =====\n\n{texto}"
        if usado + len(bloque) > max_chars:
            avisos.append(
                f"Se alcanzo el tope de {max_chars:,} caracteres: `{ruta}` y "
                "los siguientes quedaron afuera del contexto.")
            break
        partes.append(bloque)
        usado += len(bloque)

    if not partes:
        avisos.append(f"`{carpeta}` no tiene ningun .md legible.")

    return "".join(partes), avisos


# ===========================================================================
# Resultados de la corrida (bot 2 y 3)
# ===========================================================================

def _tabla_a_texto(df, titulo: str, max_filas: int = MAX_FILAS_TABLA) -> str:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return f"\n## {titulo}\n(sin datos)\n"
    recorte = ""
    if len(df) > max_filas:
        recorte = f"\n(... {len(df) - max_filas} filas mas, truncadas ...)"
        df = df.head(max_filas)
    return f"\n## {titulo}\n{df.to_string()}{recorte}\n"


def _flujos_en_mm(flujos, factor_mm: float):
    """Los flujos vienen en Mm3/d; a MMm3/d que es como se leen en el tablero."""
    if flujos is None or not isinstance(flujos, pd.DataFrame):
        return None
    vista = flujos.copy()
    for col in ["vol_disponible", "vol_maximo", "vol_asignado",
                "sobrante", "vol_derivado", "bypass"]:
        if col in vista.columns:
            vista[col] = vista[col] / factor_mm
    return vista.round(3)


def resumen_resultados(resultados: dict | None, factor_mm: float = 1000.0,
                       serie: dict | None = None) -> str:
    """Aplana la corrida vigente a un bloque de texto para el contexto.

    IMPORTANTE: recibe los resultados FISICOS (STD), no la vista 9.300. Las
    unidades se declaran en el propio texto para que el modelo no invente.
    Todo va envuelto en try/except por seccion: si una tabla cambio de forma,
    esa seccion dice "(no disponible)" y el resto del contexto sobrevive.
    """
    if not resultados:
        return ("Todavia no se corrio el pipeline: no hay resultados. "
                "Decile al usuario que corra el pipeline desde la sidebar.")

    partes: list[str] = ["# Corrida vigente (volumenes en MMm3/d STD, LGN en tn/d)\n"]

    def seccion(nombre, fn):
        try:
            partes.append(fn())
        except Exception as e:  # noqa: BLE001
            partes.append(f"\n## {nombre}\n(no disponible: {type(e).__name__}: {e})\n")

    seccion("Estado general", lambda: (
        f"\n## Estado general\n"
        f"- Desvio de balance por eslabon: {resultados.get('desvio_balance')}\n"
        f"- TBX en servicio (post-PM): {resultados.get('tbx_en_servicio')}\n"
        f"- Plantas modeladas: {', '.join(resultados.get('plantas', {}).keys())}\n"
    ))

    seccion("Reparto del gas entre plantas", lambda: _tabla_a_texto(
        _flujos_en_mm(resultados.get("flujos_plantas"), factor_mm),
        "Reparto del gas entre plantas (vol_disponible = vol_asignado + "
        "vol_derivado + bypass; el vol_derivado de una es el vol_disponible "
        "de la siguiente, NO sumar columnas entre plantas)"))

    def _mezcla():
        m = resultados.get("mezcla_transporte") or {}
        lineas = "".join(f"- {k}: {v}\n" for k, v in m.items())
        return f"\n## Mezcla a sistema de transporte\n{lineas or '(sin datos)'}"
    seccion("Mezcla a transporte", _mezcla)

    seccion("Propiedades del gas de salida", lambda: _tabla_a_texto(
        resultados.get("tablas", {}).get("Propiedades gas de salida"),
        "Propiedades de las corrientes (z, densidad, PCS, IW)"))

    def _hubs():
        info = resultados.get("info_hubs") or {}
        return f"\n## Ruteo por HUBs\n{info}\n"
    seccion("Ruteo por HUBs", _hubs)

    # Serie temporal: solo un resumen anual por planta, no las filas mensuales.
    def _serie():
        if not isinstance(serie, dict):
            return "\n## Serie temporal\n(no corrida)\n"
        plantas_df = serie.get("plantas")
        if plantas_df is None or len(plantas_df) == 0:
            return "\n## Serie temporal\n(no corrida)\n"
        df = plantas_df.copy()
        df["anio"] = pd.to_datetime(df["periodo"]).dt.year
        numericas = df.select_dtypes("number").columns.difference(["anio"])
        resumen = df.groupby(["anio", "planta"])[numericas].mean(numeric_only=True)
        return _tabla_a_texto(resumen.round(3),
                              "Serie temporal: promedio anual por planta")
    seccion("Serie temporal", _serie)

    return "".join(partes)


# ===========================================================================
# System prompts
# ===========================================================================
#
# El `system` que se manda a la API NO es un string sino una lista de bloques,
# ordenados de mas estable a mas volatil:
#
#   [0] documentacion            <- cache_control: identico en los tres bots
#   [1] instrucciones del bot    <- corto, cambia por bot
#   [2] resultados de la corrida <- cambia en cada corrida
#
# El corte del cache va al final del bloque 0 y NO mas adelante. La regla es
# que el cache solo pega si el prefijo hasta el corte es identico entre
# llamadas: si el corte estuviera despues de los resultados, cada corrida
# nueva escribiria una entrada y no leeria ninguna. Con el corte donde esta,
# la documentacion se paga entera una vez y despues se lee a 1/10 del precio,
# aunque cambien la corrida y la pregunta.

_BASE = """Sos el asistente del tablero de modelado de la red de gas \
(migracion del Excel de inyeccion/plantas a Python + Streamlit). Tu publico \
son personas AJENAS al proyecto: gerentes, gente de otras areas, usuarios \
nuevos. Explica en castellano rioplatense, claro y sin jerga innecesaria; \
cuando uses un termino del modelo (cascada, pool, retenidos, PCS, IW, lamina \
objetivo), definilo la primera vez.

Reglas duras:
- Respondes SOLO con lo que esta en tu contexto. Si algo no esta, decilo \
("eso no figura en la documentacion / en la corrida actual") en vez de inventar.
- Cita la fuente cuando ayude: "segun docs/linaje.md...".
- Se conciso: parrafos cortos, sin listas eternas.
- El tablero tiene ademas un buscador y un explicador que NO usan IA. Si la \
respuesta esta ahi, decilo: "eso lo tenes en el buscador / en la lectura \
automatica de la corrida"."""

_ROL_DOCS = """Tu material es la documentacion del proyecto (bloque anterior). \
Responde preguntas sobre como funciona el modelo, que significa cada termino y \
por que se tomo cada decision."""

_ROL_RESULTADOS = """Ademas de la documentacion tenes los RESULTADOS de la \
corrida vigente. Cuando el usuario pregunte "por que" un numero da lo que da, \
razona con las reglas del modelo (documentacion) sobre los numeros de la \
corrida. Declara siempre las unidades."""

_ROL_AGENTE = """Sos ademas el OPERADOR del tab "Plantas (sandbox)": podes \
armar escenarios y correr la cascada usando herramientas. El sandbox es \
independiente del tablero oficial: nada de lo que hagas toca la corrida de \
produccion.

Como trabajar:
1. Antes de tocar nada, mira el estado con `ver_registro` / `ver_planta`.
2. Los volumenes de las herramientas van en Mm3/d (miles); 1 MMm3/d = 1000. \
Deja siempre claro en tu respuesta en que unidad estas hablando.
3. Si una herramienta devuelve error, lee el mensaje: suele decir que campo \
esperaba. Ajusta y reintenta (maximo 2 reintentos por herramienta).
4. Despues de modificar el escenario, corre `resolver_cascada` y resume el \
resultado comparando contra la corrida oficial si esta disponible.
5. NUNCA digas que hiciste algo que una herramienta no confirmo."""

ROLES = {"docs": _ROL_DOCS, "resultados": _ROL_RESULTADOS, "agente": _ROL_AGENTE}


def bloques_system(tipo: str, docs: str, resultados: str = "") -> list[dict]:
    """Arma el `system` en bloques para la API. `tipo` in ROLES.

    El bloque de documentacion va PRIMERO y es identico para los tres bots, asi
    que comparten la misma entrada de cache (el agente escribe la suya porque
    ademas manda `tools`, que en el prefijo van antes que `system`).
    """
    bloques = [{
        "type": "text",
        "text": f"<documentacion>\n{docs}\n</documentacion>",
        "cache_control": {"type": "ephemeral"},
    }]

    bloques.append({"type": "text", "text": _BASE + "\n\n" + ROLES[tipo]})

    if resultados:
        etiqueta = "resultados_oficiales" if tipo == "agente" else "resultados"
        bloques.append({
            "type": "text",
            "text": f"<{etiqueta}>\n{resultados}\n</{etiqueta}>",
        })

    return bloques
