"""
Explicador determinista de la corrida (sin IA).
===============================================

Lee los resultados del pipeline y los narra en castellano. No es un modelo: es
una lista de REGLAS escritas a mano, cada una con su umbral y su texto. Por eso
nunca alucina y siempre dice lo mismo ante los mismos numeros — para explicarle
el tablero a alguien de afuera eso vale mas que la fluidez.

Cada regla devuelve un `Hallazgo`:

    nivel   "ok" | "info" | "atencion" | "problema"   -> como se pinta
    titulo  una linea
    detalle el porque, con los numeros a la vista
    donde   en que tab del tablero mirarlo

Agregar una regla nueva = una funcion que reciba el contexto y devuelva
Hallazgos, sumada a `_REGLAS`. Nada mas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Umbrales. Estan todos juntos a proposito: son las perillas del explicador.
UMBRAL_DESVIO = 1e-6          # arriba de esto, el balance no cierra
UMBRAL_SATURACION = 0.98      # vol_asignado / vol_maximo -> planta al tope
UMBRAL_OCIOSA = 0.60          # abajo de esto, la planta esta holgada
UMBRAL_BYPASS = 1.0           # MMm3/d de bypass que ya merecen mencionarse

FACTOR_MM = 1000.0

# Nombres posibles del maximo contractual en PARAMS. No se cual usa el
# proyecto, asi que se prueban varios y si no aparece ninguno el hallazgo se
# reporta igual, sin la comparacion. Si el tuyo no esta, agregalo aca.
_CANDIDATOS_MAX = {
    "pcs": ("PCS_MAX", "PCS_MAXIMO", "MAX_PCS", "PCS_MAX_TRANSPORTE"),
    "iw": ("IW_MAX", "IW_MAXIMO", "MAX_IW", "IW_MAX_TRANSPORTE"),
}


def _maximo(params: dict, clave: str):
    """Primer candidato presente y no nulo, o None."""
    for nombre in _CANDIDATOS_MAX.get(clave, ()):
        valor = params.get(nombre)
        if valor:
            return float(valor)
    return None


@dataclass
class Hallazgo:
    nivel: str
    titulo: str
    detalle: str
    donde: str = ""


@dataclass
class Contexto:
    """Todo lo que las reglas pueden mirar, ya normalizado."""
    resultados: dict
    flujos: pd.DataFrame | None = None      # en MMm3/d
    plantas: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    serie: dict | None = None


def _armar_contexto(resultados: dict, params=None, serie=None,
                    factor_mm: float = FACTOR_MM) -> Contexto:
    flujos = resultados.get("flujos_plantas")
    if isinstance(flujos, pd.DataFrame) and not flujos.empty:
        flujos = flujos.copy()
        for col in ["vol_disponible", "vol_maximo", "vol_asignado",
                    "sobrante", "vol_derivado", "bypass"]:
            if col in flujos.columns:
                flujos[col] = flujos[col] / factor_mm
    else:
        flujos = None

    # `params` puede ser un dict o un modulo (igual que en el sandbox).
    if params is None:
        dparams = {}
    elif isinstance(params, dict):
        dparams = params
    else:
        dparams = {k: getattr(params, k) for k in dir(params)
                   if k.isupper()}

    return Contexto(resultados=resultados, flujos=flujos,
                    plantas=resultados.get("plantas") or {},
                    params=dparams, serie=serie)


# ===========================================================================
# Reglas
# ===========================================================================

def _r_balance(ctx: Contexto) -> list[Hallazgo]:
    desvio = ctx.resultados.get("desvio_balance")
    if desvio is None:
        return []
    if desvio < UMBRAL_DESVIO:
        return [Hallazgo(
            "ok", "El balance cierra",
            f"Desvio maximo {desvio:.2e}: en cada planta se cumple "
            "vol_disponible = vol_asignado + vol_derivado + bypass. "
            "Ningun metro cubico se pierde ni aparece de la nada.",
            "Resumen")]
    return [Hallazgo(
        "problema", "El balance NO cierra",
        f"Desvio maximo {desvio:,.4f}. Deberia valer vol_disponible = "
        "vol_asignado + vol_derivado + bypass en cada planta. Mientras esto "
        "no de cero, ningun numero de la corrida es confiable.",
        "Resumen")]


def _r_tbx(ctx: Contexto) -> list[Hallazgo]:
    en_servicio = ctx.resultados.get("tbx_en_servicio")
    if en_servicio is None:
        return []
    if en_servicio:
        return [Hallazgo(
            "info", "TTY-TBX en servicio (post-PM)",
            "El pool de TTY entra primero por TTY-TBX y lo que sobra pasa a "
            "TTY-Dew Point. Es la configuracion posterior a la parada de "
            "mantenimiento.",
            "Cascada")]
    return [Hallazgo(
        "info", "TTY-TBX fuera de servicio (pre-PM)",
        "Antes de la parada de mantenimiento, el pool de TTY va directo a "
        "TTY-Dew Point: TBX no trata nada en este periodo.",
        "Cascada")]


def _r_capacidad(ctx: Contexto) -> list[Hallazgo]:
    """Planta por planta: saturada, holgada, con bypass o con sobrante."""
    if ctx.flujos is None:
        return []
    f = ctx.flujos
    if "vol_asignado" not in f.columns or "vol_maximo" not in f.columns:
        return []

    hallazgos = []
    for planta, fila in f.iterrows():
        if not bool(fila.get("activa", True)):
            hallazgos.append(Hallazgo(
                "info", f"{planta}: fuera de servicio",
                "No esta activa en esta corrida, asi que no trata gas.",
                "Reparto del gas"))
            continue

        maximo = float(fila.get("vol_maximo") or 0)
        asignado = float(fila.get("vol_asignado") or 0)
        if maximo <= 0:
            continue
        uso = asignado / maximo

        if uso >= UMBRAL_SATURACION:
            hallazgos.append(Hallazgo(
                "atencion", f"{planta}: al tope de capacidad",
                f"Trata {asignado:,.2f} de un maximo de {maximo:,.2f} MMm3/d "
                f"({uso:.0%}). Todo el gas que le llegue de mas no lo puede "
                "procesar: se deriva o pasa de largo.",
                "Reparto del gas"))
        elif uso <= UMBRAL_OCIOSA:
            hallazgos.append(Hallazgo(
                "info", f"{planta}: con capacidad de sobra",
                f"Trata {asignado:,.2f} de {maximo:,.2f} MMm3/d ({uso:.0%}): "
                "tiene margen para recibir mas gas.",
                "Reparto del gas"))

        bypass = float(fila.get("bypass") or 0)
        if bypass > UMBRAL_BYPASS:
            hallazgos.append(Hallazgo(
                "atencion", f"{planta}: {bypass:,.2f} MMm3/d de bypass",
                "Ese gas llega a la planta pero pasa de largo sin tratarse "
                "(limite de proceso o de evacuacion). No va a otra planta: "
                "sigue de largo tal como esta.",
                "Reparto del gas"))

        derivado = float(fila.get("vol_derivado") or 0)
        if derivado > 0:
            hallazgos.append(Hallazgo(
                "info", f"{planta}: deriva {derivado:,.2f} MMm3/d",
                "Es el sobrante que le pasa a la planta siguiente de la "
                "cascada. Ese volumen es el vol_disponible de la que sigue, "
                "asi que no hay que sumar la columna entre plantas.",
                "Cascada"))

    return hallazgos


def _r_calidad(ctx: Contexto) -> list[Hallazgo]:
    """PCS e IW de la mezcla a transporte contra los maximos, si estan."""
    mezcla = ctx.resultados.get("mezcla_transporte") or {}
    if not mezcla:
        return []

    hallazgos = []
    for clave, etiqueta in (("pcs", "PCS"), ("iw", "IW")):
        valor = mezcla.get(clave)
        if valor is None:
            continue
        maximo = _maximo(ctx.params, clave)
        if maximo:
            margen = float(maximo) - float(valor)
            nivel = "atencion" if margen < 0 else "ok"
            verbo = "SUPERA" if margen < 0 else "esta debajo de"
            hallazgos.append(Hallazgo(
                nivel, f"{etiqueta} de la mezcla: {valor:,.0f} kcal/m3",
                f"{verbo} el maximo de {float(maximo):,.0f} "
                f"(margen {margen:,.0f} kcal/m3).",
                "Graphs"))
        else:
            hallazgos.append(Hallazgo(
                "info", f"{etiqueta} de la mezcla: {valor:,.0f} kcal/m3",
                "Es la calidad del gas que entra al sistema de transporte.",
                "Graphs"))

    volumenes = {k: v for k, v in mezcla.items()
                 if k.startswith("vol_") and v is not None}
    if volumenes:
        total = sum(float(v) for v in volumenes.values())
        partes = ", ".join(
            f"{k.replace('vol_', '').replace('_', ' ')} {float(v):,.2f}"
            for k, v in volumenes.items())
        hallazgos.append(Hallazgo(
            "info", f"Inyeccion a transporte: {total:,.2f} MMm3/d",
            f"Se compone de: {partes}. Es la lamina objetivo del tablero.",
            "Graphs"))

    return hallazgos


def _r_hubs(ctx: Contexto) -> list[Hallazgo]:
    info = ctx.resultados.get("info_hubs")
    if not isinstance(info, dict) or not info:
        return []
    sin_reparto = info.get("sin_reparto") or info.get("hubs_sin_reparto")
    if sin_reparto:
        return [Hallazgo(
            "atencion", f"{len(sin_reparto)} HUB(s) sin reparto",
            f"No se les pudo asignar destino: {sin_reparto}. Su gas no llega "
            "a ninguna planta en esta corrida; suele ser un coeficiente de "
            "inyeccion faltante para el periodo.",
            "Mapa de la red")]
    return []


def _r_diagnostico(ctx: Contexto) -> list[Hallazgo]:
    """El panel de calidad de datos, resumido en una linea."""
    import streamlit as st
    obs = st.session_state.get("diagnostico") or []
    if not obs:
        return [Hallazgo(
            "ok", "Datos de entrada sin observaciones",
            "El pipeline no reporto areas sin cruzar, duplicados ni "
            "cromatografias inconsistentes.",
            "Resumen")]
    return [Hallazgo(
        "info", f"{len(obs)} observacion(es) sobre los datos de entrada",
        "Son avisos de carga y cruce (areas sin match, claves duplicadas, "
        "cromatografias repetidas). No frenan la corrida, pero conviene "
        "leerlos: explican numeros raros.",
        "Resumen > Calidad de los datos de entrada")]


_REGLAS = (_r_balance, _r_diagnostico, _r_tbx, _r_capacidad,
           _r_calidad, _r_hubs)

_ORDEN_NIVEL = {"problema": 0, "atencion": 1, "ok": 2, "info": 3}


def explicar(resultados: dict | None, params=None, serie=None,
             factor_mm: float = FACTOR_MM) -> list[Hallazgo]:
    """Corre todas las reglas. Lo primero que devuelve es lo mas urgente."""
    if not resultados:
        return [Hallazgo(
            "info", "Todavia no se corrio el pipeline",
            "Elegi el archivo de inputs y el periodo en la barra lateral, y "
            "dale a correr. Sin corrida no hay nada que explicar.",
            "Barra lateral")]

    ctx = _armar_contexto(resultados, params, serie, factor_mm)

    hallazgos: list[Hallazgo] = []
    for regla in _REGLAS:
        try:
            hallazgos.extend(regla(ctx))
        except Exception as e:  # noqa: BLE001 - una regla rota no tapa al resto
            hallazgos.append(Hallazgo(
                "info", f"Una regla del explicador fallo ({regla.__name__})",
                f"{type(e).__name__}: {e}. El resto de la lectura sigue "
                "siendo valida.", ""))

    hallazgos.sort(key=lambda h: _ORDEN_NIVEL.get(h.nivel, 9))
    return hallazgos


# ===========================================================================
# Preguntas frecuentes: atajos a una lectura concreta
# ===========================================================================
#
# El buscador responde "que es X"; esto responde "por que pasa X ACA". Cada
# pregunta filtra los hallazgos que le importan.

PREGUNTAS = {
    "¿Cómo viene la corrida en general?":
        lambda hs: hs,
    "¿Alguna planta está saturada?":
        lambda hs: [h for h in hs if "tope" in h.titulo or "bypass" in h.titulo],
    "¿Cierra el balance?":
        lambda hs: [h for h in hs if "balance" in h.titulo.lower()],
    "¿Cómo está la calidad del gas (PCS/IW)?":
        lambda hs: [h for h in hs if "PCS" in h.titulo or "IW" in h.titulo
                    or "transporte" in h.titulo],
    "¿Hay problemas con los datos de entrada?":
        lambda hs: [h for h in hs if "observaci" in h.titulo
                    or "HUB" in h.titulo],
}
