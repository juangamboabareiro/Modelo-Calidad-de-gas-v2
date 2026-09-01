"""
Buscador de documentacion SIN IA.
=================================

Es el piso del asistente: funciona siempre, sin credenciales, sin red y sin
costo. No inventa nada porque no genera texto — devuelve los pedazos reales de
`docs/` que mejor matchean la pregunta.

Como funciona
-------------
1. Cada .md se parte en SECCIONES por encabezado (`#`, `##`, `###`). Una
   seccion es la unidad de respuesta: un titulo con su texto.
2. La consulta se normaliza (sin tildes, sin mayusculas) y se parte en
   terminos, descartando muletillas.
3. Cada seccion puntua por cuantos terminos aparecen, con peso extra si el
   termino esta en el TITULO (que un `##` diga "Validaciones" pesa mas que
   la palabra suelta en un parrafo).

No es un motor semantico: si preguntan "por que no cierra el balance" y la doc
dice "desvio por eslabon", no lo va a encontrar. Para eso esta el glosario, que
mapea a mano los terminos del negocio a sus sinonimos.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Palabras que no aportan a la busqueda. Cortita a proposito: de mas, empieza a
# comerse terminos utiles ("area", "planta", "total" NO van aca).
_MULETILLAS = {
    "que", "cual", "cuales", "como", "cuando", "donde", "por", "para", "the",
    "una", "uno", "unos", "unas", "del", "las", "los", "con", "sin", "sobre",
    "esto", "esta", "este", "esa", "ese", "hay", "son", "es", "y", "o", "de",
    "en", "el", "la", "un", "se", "su", "al", "lo", "me", "mi", "si", "no",
    "quiero", "saber", "explicame", "decime", "significa", "sirve", "hace",
}

# Peso de un termino que aparece en el titulo de la seccion.
_PESO_TITULO = 3

MAX_RESULTADOS = 5

# Cuantos caracteres de la seccion se muestran antes de plegar el resto.
_LARGO_PREVIEW = 900


# ===========================================================================
# Glosario
# ===========================================================================
#
# Lo unico escrito a mano de todo el modulo, y lo mas valioso para el que llega
# de afuera: los diez terminos que aparecen en la primera pantalla del tablero
# y no se entienden sin contexto. Cada entrada tiene sinonimos para que el
# buscador la encuentre aunque pregunten distinto.

GLOSARIO: dict[str, dict] = {
    "Cascada": {
        "sinonimos": ["eslabon", "eslabones", "orden", "topologico", "derivar"],
        "texto": (
            "El gas no entra a una sola planta: pasa por una cadena. Cada "
            "planta trata lo que puede (su capacidad) y lo que le sobra se lo "
            "manda a la siguiente. Esa cadena es la cascada. Se resuelve en "
            "orden topologico: una planta se calcula recien cuando ya se "
            "sabe todo lo que le llega."),
    },
    "Pool": {
        "sinonimos": ["nombre_pool", "matriz", "inyecciones", "gas disponible"],
        "texto": (
            "El conjunto de gas que le corresponde a una planta segun la "
            "matriz de inyecciones. Dos plantas pueden compartir pool (TTY-TBX "
            "y TTY-Dew Point tratan el mismo gas, son dos trenes) o tener el "
            "suyo (MEGA)."),
    },
    "Retenidos": {
        "sinonimos": ["retencion", "rtp", "compuesto", "lgn", "recupero"],
        "texto": (
            "El porcentaje de cada compuesto que la planta se queda (etano, "
            "propano, butanos...). Es lo que convierte el gas rico de entrada "
            "en gas residual mas LGN. Se define compuesto por compuesto."),
    },
    "Gas rico / gas residual": {
        "sinonimos": ["gas_rico_in", "residual", "entrada", "salida"],
        "texto": (
            "Rico es el gas como entra a la planta, con los pesados adentro. "
            "Residual es lo que sale despues de retener esos pesados: mas "
            "pobre, con menos poder calorifico."),
    },
    "PCS": {
        "sinonimos": ["poder calorifico", "kcal", "calidad", "9300"],
        "texto": (
            "Poder Calorifico Superior, en kcal/m3: cuanta energia entrega el "
            "gas al quemarse. El sistema de transporte tiene un maximo. El "
            "tablero permite ver los volumenes en 'MMm3/d de 9.300 kcal', que "
            "es el volumen equivalente en energia (V x PCS / 9300)."),
    },
    "IW": {
        "sinonimos": ["indice", "wobbe", "calidad", "intercambiabilidad"],
        "texto": (
            "Indice de Wobbe: PCS dividido la raiz de la densidad relativa. "
            "Mide si dos gases son intercambiables en un quemador. Tambien "
            "tiene un maximo contractual."),
    },
    "Lamina objetivo": {
        "sinonimos": ["mezcla", "transporte", "tpe", "inyeccion a transporte"],
        "texto": (
            "La mezcla final que entra al sistema de transporte: la suma de lo "
            "que sale de las plantas mas lo que va directo a gasoducto, con su "
            "PCS e IW resultantes. Es el numero que se mira al final."),
    },
    "Sandbox": {
        "sinonimos": ["escenario", "simular", "que pasa si", "plantas nuevas"],
        "texto": (
            "El tab 'Plantas (sandbox)' corre su PROPIA cascada, aparte de la "
            "oficial. Sirve para preguntar 'que pasa si' sin tocar los numeros "
            "validados. Si el registro esta sin modificar tiene que dar "
            "identico al oficial: eso es el bloque de control."),
    },
    "Desvio de balance": {
        "sinonimos": ["balance", "cierra", "control", "no cierra"],
        "texto": (
            "Por cada planta tiene que valer vol_disponible = vol_asignado + "
            "vol_derivado + bypass. El desvio es cuanto se aparta de esa "
            "igualdad. Si no es practicamente cero, el resultado no es "
            "confiable."),
    },
    "Bypass": {
        "sinonimos": ["no tratado", "pasa de largo", "sin procesar"],
        "texto": (
            "Gas que llega a la planta pero pasa de largo sin tratarse, "
            "normalmente por limite de capacidad de proceso o de evacuacion. "
            "No es lo mismo que el sobrante derivado: el bypass no va a otra "
            "planta, sigue de largo."),
    },
    "HUB": {
        "sinonimos": ["ruteo", "reparto", "area", "hubs"],
        "texto": (
            "Punto donde se juntan varias areas antes de repartirse a los "
            "gasoductos. El ruteo por hubs decide cuanto de cada hub va a cada "
            "destino."),
    },
}


# ===========================================================================
# Normalizacion
# ===========================================================================

def _plano(texto: str) -> str:
    """Minusculas y sin tildes: 'Inyección' y 'inyeccion' matchean igual."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = sin_tildes.encode("ascii", "ignore").decode()
    return sin_tildes.lower()


def _terminos(consulta: str) -> list[str]:
    palabras = re.findall(r"[a-z0-9_]{2,}", _plano(consulta))
    return [p for p in palabras if p not in _MULETILLAS]


# ===========================================================================
# Indice
# ===========================================================================

def _partir_en_secciones(texto: str, ruta: str) -> list[dict]:
    """Parte un markdown en secciones por encabezado.

    Lo que va antes del primer encabezado se guarda igual, con el nombre del
    archivo como titulo: varios docs arrancan con parrafos utiles antes del
    primer `##` y perderlos seria perder justo la introduccion.
    """
    secciones: list[dict] = []
    titulo_actual = Path(ruta).stem
    buffer: list[str] = []

    def cerrar():
        cuerpo = "\n".join(buffer).strip()
        if cuerpo:
            secciones.append({"archivo": ruta, "titulo": titulo_actual,
                              "cuerpo": cuerpo})

    for linea in texto.splitlines():
        if re.match(r"^#{1,3} ", linea):
            cerrar()
            titulo_actual = linea.lstrip("#").strip()
            buffer = []
        else:
            buffer.append(linea)
    cerrar()
    return secciones


def construir_indice(carpeta: str | Path = "docs") -> list[dict]:
    """Lista de secciones de todos los .md. Es barato: cachearlo en la UI."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []

    indice: list[dict] = []
    for ruta in sorted(carpeta.rglob("*.md")):
        try:
            texto = ruta.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 - un md ilegible no rompe el indice
            continue
        for seccion in _partir_en_secciones(texto, ruta.as_posix()):
            seccion["titulo_plano"] = _plano(seccion["titulo"])
            seccion["cuerpo_plano"] = _plano(seccion["cuerpo"])
            indice.append(seccion)
    return indice


# ===========================================================================
# Busqueda
# ===========================================================================

def buscar(consulta: str, indice: list[dict],
           max_resultados: int = MAX_RESULTADOS) -> list[dict]:
    """Secciones ordenadas por relevancia. Cada una con su puntaje y preview."""
    terminos = _terminos(consulta)
    if not terminos or not indice:
        return []

    resultados = []
    for seccion in indice:
        puntaje = 0
        encontrados = []
        for t in terminos:
            en_titulo = t in seccion["titulo_plano"]
            apariciones = seccion["cuerpo_plano"].count(t)
            if en_titulo:
                puntaje += _PESO_TITULO
            if apariciones:
                # Se satura en 3: una seccion larga que repite la palabra no
                # es mas relevante que una corta y al punto.
                puntaje += min(apariciones, 3)
            if en_titulo or apariciones:
                encontrados.append(t)

        if puntaje:
            resultados.append({
                **seccion,
                "puntaje": puntaje,
                "terminos": encontrados,
                "cobertura": len(encontrados) / len(terminos),
            })

    # Primero cuantos terminos DISTINTOS cubre, despues el puntaje bruto: una
    # seccion que menciona los tres terminos de la pregunta le gana a otra que
    # repite uno solo diez veces.
    resultados.sort(key=lambda r: (r["cobertura"], r["puntaje"]), reverse=True)
    return resultados[:max_resultados]


def buscar_glosario(consulta: str) -> list[tuple[str, str]]:
    """Entradas del glosario que matchean. Devuelve [(termino, texto), ...]."""
    terminos = _terminos(consulta)
    if not terminos:
        return []

    hallazgos = []
    for nombre, datos in GLOSARIO.items():
        claves = [_plano(nombre)] + [_plano(s) for s in datos["sinonimos"]]
        # Match por substring en las dos direcciones: "pcs" encuentra "PCS" y
        # "cascadas" encuentra "Cascada".
        if any(t in c or c in t for t in terminos for c in claves):
            hallazgos.append((nombre, datos["texto"]))
    return hallazgos


def preview(cuerpo: str, largo: int = _LARGO_PREVIEW) -> tuple[str, str]:
    """Parte el cuerpo en (visible, resto) para no volcar secciones enormes."""
    if len(cuerpo) <= largo:
        return cuerpo, ""
    corte = cuerpo.rfind("\n", 0, largo)
    if corte < largo // 2:
        corte = largo
    return cuerpo[:corte], cuerpo[corte:]
