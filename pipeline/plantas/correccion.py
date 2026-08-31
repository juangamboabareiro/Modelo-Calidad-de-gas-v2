# -*- coding: utf-8 -*-
"""
Correccion de ingreso por llenar evacuacion — declarativa y por planta.
=======================================================================

Destino: pipeline/plantas/correccion.py

Generaliza `correccion_TTY`: en vez de reglas hardcodeadas (gasolina pasa
100%, etano no se trata, el tope se llena primero con C4 y despues con C3),
las reglas son DATO. El usuario puede escribirlas en castellano y
`parsear_reglas` las interpreta; `describir_reglas` hace el camino inverso
para que siempre pueda verificar que se le entendio.

ESQUEMA DE REGLAS (dict plano, JSON-friendly: entra en los escenarios)
----------------------------------------------------------------------
    {
        "aplicar": bool,          # prendida / apagada
        "tope": float,            # tn/d. 0 = capacidad de evacuacion de la planta
        "solo_si_excede": bool,   # aplicar solo si el LGN del pool supera el tope
        "cortes": {
            "gasolina": "pasa",   # pasa 100%: retencion -> 0
            "etano":    "pasa",
            "butanos":  1,        # entero = prioridad con la que llena el tope
            "propano":  2,        #          (1 llena primero)
            # ausente o "libre" = sin correccion, retencion original
        },
    }

MATEMATICA
----------
Los retenidos son lineales en los coeficientes a composicion y volumen fijos
(es la cuenta de `calcular_retenidos`), asi que para llevar un corte de
`actual` tn/d a `objetivo` tn/d alcanza con escalar sus coeficientes por
`objetivo / actual`. Es exacto a volumen de pool fijo y reemplaza la formula
inversa (opaca) del legacy. Despues de corregir hay que RE-MODELAR el pool
con los coeficientes nuevos (`io_plantas`), igual que hacia TTY_TBX.py.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd


# ---------------------------------------------------------------------------
# Vocabulario
# ---------------------------------------------------------------------------

CORTES = ("etano", "propano", "butanos", "gasolina")

SINONIMOS = {
    "etano":    ("etano", "c2"),
    "propano":  ("propano", "c3"),
    "butanos":  ("butanos", "butano", "c4"),
    "gasolina": ("gasolina", "nafta", "c5+", "c5"),
}

MODO_LIBRE = "libre"   # sin correccion
MODO_PASA = "pasa"     # pasa 100%: retencion -> 0
# int >= 1            -> prioridad con la que el corte llena el tope

# Las reglas que estaban hardcodeadas en correccion_TTY / correccion_TTY_DP.
REGLAS_LEGACY = {
    "aplicar": False,
    "tope": 0.0,               # 0 = capacidad de evacuacion de la planta
    "solo_si_excede": True,
    "cortes": {
        "gasolina": MODO_PASA,  # GASOLINA PASA 100%
        "etano": MODO_PASA,     # NO TRATA ETANO
        "butanos": 1,           # el tope se llena primero con C4...
        "propano": 2,           # ...y despues con C3
    },
}


def reglas_vacias() -> dict:
    """Reglas 'apagadas': sin correccion, todo con retencion original."""
    return {"aplicar": False, "tope": 0.0, "solo_si_excede": True, "cortes": {}}


def copiar_reglas(reglas: dict | None) -> dict:
    """Copia defensiva (los dicts se guardan en session_state y escenarios)."""
    if not reglas:
        return reglas_vacias()
    return {
        "aplicar": bool(reglas.get("aplicar", False)),
        "tope": float(reglas.get("tope") or 0.0),
        "solo_si_excede": bool(reglas.get("solo_si_excede", True)),
        "cortes": dict(reglas.get("cortes") or {}),
    }


# ---------------------------------------------------------------------------
# Texto libre -> reglas
# ---------------------------------------------------------------------------

def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = t.encode("ascii", "ignore").decode("ascii")
    return t.lower()


def _a_numero(s: str) -> float:
    # "5.600" -> 5600 ; "200,5" -> 200.5 ; "200" -> 200
    s = re.sub(r"\.(?=\d{3}\b)", "", s.strip())
    return float(s.replace(",", "."))


def _buscar_corte(fragmento: str) -> str | None:
    """El corte cuyo sinonimo aparece PRIMERO en el fragmento.

    "primero con butanos y despues con propano": el fragmento que sigue a
    "primero" contiene los dos cortes; el que manda es el mas cercano.
    """
    mejor, pos = None, len(fragmento) + 1
    for corte in CORTES:
        for s in SINONIMOS[corte]:
            i = fragmento.find(s)
            if 0 <= i < pos:
                mejor, pos = corte, i
    return mejor


def _patron_sinonimos(corte: str) -> str:
    return "(?:" + "|".join(re.escape(s) for s in SINONIMOS[corte]) + ")"


def parsear_reglas(texto: str) -> tuple[dict, list[str]]:
    """Interpreta una descripcion en castellano y devuelve (reglas, avisos).

    Entiende, en cualquier orden:
      - "la gasolina pasa 100%" / "no se trata etano" / "el etano sin tratar"
      - "hasta 200 tn/d" / "tope de 200 tn" / "limite 200 tn/d"
        (sin numero, el tope queda en 0 = capacidad de evacuacion)
      - "primero butanos y despues propano" / "primero C4, luego C3"

    Los avisos son para que el usuario sepa que NO se entendio: el editor
    estructurado de abajo siempre permite corregir a mano.
    """
    t = _normalizar(texto)
    reglas = reglas_vacias()
    reglas["aplicar"] = True
    avisos: list[str] = []

    if not t.strip():
        return reglas, ["El texto esta vacio: no hay nada que interpretar."]

    # --- tope ------------------------------------------------------------
    m = re.search(
        r"(?:hasta|tope(?:\s+de)?|limite(?:\s+de)?|maximo(?:\s+de)?)\s*"
        r"([\d][\d.,]*)\s*(?:tn|t|ton|toneladas)\b", t)
    if m:
        try:
            reglas["tope"] = _a_numero(m.group(1))
        except ValueError:
            avisos.append(f"No pude leer el numero del tope («{m.group(1)}»).")
    elif "evacuacion" in t:
        reglas["tope"] = 0.0   # explicito: usar la capacidad de evacuacion

    # --- cortes que pasan 100% / no se tratan ------------------------------
    # Patrones ADYACENTES (sin cruzar comas ni otro corte en el medio): asi
    # "primero c4 ... la nafta pasa 100" no marca a los butanos como "pasa".
    _NEG = r"(?:no\s+se\s+trata(?:n)?|no\s+trata(?:n)?|sin\s+tratar|no\s+se\s+retiene(?:n)?)"
    for corte in CORTES:
        syn = _patron_sinonimos(corte)
        patrones = (
            rf"{syn}[^.,;]{{0,30}}?\bpasa(?:n)?\b",   # "la gasolina pasa 100%"
            rf"\bpasa(?:n)?\b[^.,;]{{0,30}}?{syn}",   # "pasa 100% la gasolina"
            rf"{_NEG}[^.,;]{{0,30}}?{syn}",             # "no se trata etano"
            rf"{syn}[^.,;]{{0,30}}?{_NEG}",             # "el etano no se trata"
        )
        if any(re.search(pt, t) for pt in patrones):
            reglas["cortes"][corte] = MODO_PASA

    # --- orden de llenado del tope -----------------------------------------
    marcas = []
    for m in re.finditer(r"\b(primero|1ro|segundo|2do|tercero|despues|luego)\b", t):
        corte = _buscar_corte(t[m.end(): m.end() + 40])
        if corte:
            marcas.append((m.start(), corte))

    prioridad = 1
    for _, corte in sorted(marcas):
        if isinstance(reglas["cortes"].get(corte), int):
            continue
        reglas["cortes"][corte] = prioridad   # pisa un "pasa" mal detectado
        prioridad += 1

    # --- diagnostico --------------------------------------------------------
    if not reglas["cortes"]:
        avisos.append(
            "No reconoci ningun corte (etano/C2, propano/C3, butanos/C4, "
            "gasolina/C5+). Ajusta las reglas a mano en la tabla de abajo.")
    else:
        sin_regla = [c for c in CORTES if c not in reglas["cortes"]]
        if sin_regla:
            avisos.append(
                "Quedan con su retencion original (no los mencionaste): "
                + ", ".join(sin_regla) + ".")
        if not any(isinstance(m_, int) for m_ in reglas["cortes"].values()):
            avisos.append(
                "No entendi que cortes llenan el tope ni en que orden "
                "(proba «primero butanos y despues propano»).")

    return reglas, avisos


# ---------------------------------------------------------------------------
# Reglas -> texto (el espejo, para que el usuario verifique)
# ---------------------------------------------------------------------------

def describir_reglas(reglas: dict | None) -> str:
    reglas = copiar_reglas(reglas)

    if not reglas["aplicar"]:
        return ("Sin correccion: la planta se llena hasta su evacuacion y el "
                "sobrante se deriva o bypasea, como siempre.")

    partes = []

    pasan = [c for c in CORTES if reglas["cortes"].get(c) == MODO_PASA]
    if pasan:
        verbo = "pasan" if len(pasan) > 1 else "pasa"
        partes.append(f"{' y '.join(pasan)} {verbo} 100% (retencion en cero)")

    en_tope = sorted(
        (m, c) for c, m in reglas["cortes"].items() if isinstance(m, int))
    tope_txt = (f"{reglas['tope']:,.0f} tn/d" if reglas["tope"]
                else "la capacidad de evacuacion de la planta")
    if en_tope:
        orden = " → ".join(c for _, c in en_tope)
        partes.append(f"el tope de {tope_txt} se llena en este orden: {orden}")

    libres = [c for c in CORTES
              if reglas["cortes"].get(c, MODO_LIBRE) == MODO_LIBRE]
    if libres:
        verbo = "conservan" if len(libres) > 1 else "conserva"
        partes.append(f"{', '.join(libres)} {verbo} su retencion original")

    cuando = ("solo cuando el LGN del pool excede el tope"
              if reglas["solo_si_excede"] else "siempre que se corra la planta")

    return "Con esta correccion (" + cuando + "): " + "; ".join(partes) + "."


# ---------------------------------------------------------------------------
# La matematica
# ---------------------------------------------------------------------------

def mapa_cortes(ETANO, PROPANO, BUTANOS, GASOLINA) -> dict:
    """{corte -> lista de compuestos}, tolerante a escalares o listas."""
    def lista(x):
        if isinstance(x, (list, tuple, set, pd.Index)):
            return list(x)
        return [x]
    return {"etano": lista(ETANO), "propano": lista(PROPANO),
            "butanos": lista(BUTANOS), "gasolina": lista(GASOLINA)}


def corregir_coeficientes(reglas, retenidos_planta, retenidos_vol,
                          capacidad_evacuacion, cortes_compuestos):
    """Devuelve los coeficientes de retencion corregidos (DataFrame 1 x N).

    Parameters
    ----------
    retenidos_planta : DataFrame de 1 fila, columnas = compuestos
        Los coeficientes con los que se modelo el pool (mismo formato que
        recibe `io_plantas`).
    retenidos_vol : DataFrame de 1 fila con columnas etano/propano/butanos/
        gasolina en tn/d (lo que devuelve `io_plantas` para el pool completo).
    capacidad_evacuacion : float
        Fallback del tope cuando reglas['tope'] == 0.
    cortes_compuestos : dict corte -> [compuestos]  (ver `mapa_cortes`).
    """
    reglas = copiar_reglas(reglas)
    tope = reglas["tope"] or float(capacidad_evacuacion)

    nuevos = retenidos_planta.copy().astype(float)

    # 1) Cortes que pasan 100%: retencion en cero.
    for corte, modo in reglas["cortes"].items():
        if modo != MODO_PASA:
            continue
        for comp in cortes_compuestos.get(corte, ()):
            if comp in nuevos.columns:
                nuevos.loc[:, comp] = 0.0

    # 2) Cortes que compiten por el tope, en orden de prioridad. El escalado
    #    objetivo/actual es exacto: los tn/d retenidos son lineales en el
    #    coeficiente a composicion y volumen de pool fijos.
    en_tope = sorted(
        (m, c) for c, m in reglas["cortes"].items() if isinstance(m, int))
    restante = float(tope)

    for _, corte in en_tope:
        actual = float(retenidos_vol[corte].values.sum())
        objetivo = min(actual, max(restante, 0.0))
        restante -= objetivo
        factor = (objetivo / actual) if actual > 0 else 1.0
        for comp in cortes_compuestos.get(corte, ()):
            if comp in nuevos.columns:
                nuevos.loc[:, comp] = nuevos.loc[:, comp] * factor

    return nuevos


def aplicar_a_planta(reglas, retenidos_planta, retenidos_vol_pool,
                     capacidad_evacuacion, cortes_compuestos):
    """Punto de entrada unico para TTY.py, MEGA.py y planta.py.

    Devuelve los coeficientes corregidos, o None si no hay que re-modelar
    (correccion apagada, o `solo_si_excede` y el LGN del pool entra en el
    tope). El que llama, si recibe algo, vuelve a correr `io_plantas` con
    estos coeficientes.
    """
    reglas = copiar_reglas(reglas)

    if not reglas["aplicar"] or not reglas["cortes"]:
        return None

    tope = reglas["tope"] or float(capacidad_evacuacion)
    lgn_pool = float(retenidos_vol_pool.values.sum())

    if reglas["solo_si_excede"] and lgn_pool <= tope:
        return None

    return corregir_coeficientes(
        reglas=reglas,
        retenidos_planta=retenidos_planta,
        retenidos_vol=retenidos_vol_pool,
        capacidad_evacuacion=capacidad_evacuacion,
        cortes_compuestos=cortes_compuestos,
    )
