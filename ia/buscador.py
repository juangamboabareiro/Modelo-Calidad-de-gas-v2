"""
Buscador de documentacion SIN IA.
=================================

Es el piso del asistente: funciona siempre, sin credenciales, sin red y sin
costo. No inventa nada porque no genera texto — devuelve los pedazos reales de
`docs/` que mejor matchean la pregunta.

Como funciona
-------------
1. Cada archivo se parte en SECCIONES por encabezado. Una seccion es la unidad
   de respuesta: un titulo con su texto.
2. La consulta se normaliza (sin tildes, sin mayusculas) y se parte en
   terminos, descartando muletillas.
3. Cada seccion puntua por cuantos terminos aparecen, con peso extra si el
   termino esta en el TITULO, y por el PESO DEL DOCUMENTO (ver abajo).

No es un motor semantico: si preguntan "por que no cierra el balance" y la doc
dice "desvio por eslabon", no lo va a encontrar. Para eso esta el glosario.

LA JERARQUIA DE LOS DOCUMENTOS IMPORTA
--------------------------------------
El README define tres capas y dice explicitamente cuales documentos NO son
fuente de verdad. Un buscador que trate a todos por igual puede contestar con
un TODO de la bitacora resuelto hace meses, y con la misma cara de certeza que
si citara `dominio.md`. Por eso:

  - `PESOS` empuja hacia arriba los documentos de referencia y hunde a los
    historicos;
  - `OBSOLETOS` los saca del indice directamente;
  - `ADVERTENCIAS` marca en pantalla los que hay que leer con reservas.

Si se agrega un documento nuevo a `docs/`, entra solo con peso 1.0. Solo hay
que tocar este archivo si es historico, obsoleto o especialmente autoritativo.
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

_PESO_TITULO = 3
MAX_RESULTADOS = 5
_LARGO_PREVIEW = 900

# ---------------------------------------------------------------------------
# Jerarquia documental (ver README, "La documentacion en tres capas")
# ---------------------------------------------------------------------------

# Archivos que el README declara ELIMINADOS pero que pueden seguir en la
# carpeta. Son plantillas sin llenar, con placeholders y hojas que no existen
# en este proyecto: indexarlos es peor que no tener buscador, porque devuelven
# respuestas con formato de verdad. `changelog.md` ademas es un duplicado
# exacto de `bitacora.md`, asi que duplica todos los resultados historicos.
OBSOLETOS = {"data_dictionary.md", "decisions.md", "changelog.md", "arq.md"}

# Multiplicador del puntaje por documento.
PESOS = {
    "dominio.md": 1.4,        # que significan los numeros: la base de todo
    "manual_usuario.md": 1.3, # como se usa: lo que mas pregunta un recien llegado
    "linaje.md": 1.2,         # de donde viene cada dato
    "operacion.md": 1.2,      # que hago si algo rompe
    "validaciones.md": 1.1,
    "HALLAZGOS.md": 1.1,      # "eso ya esta documentado" es una gran respuesta
    "mapa.md": 0.7,           # generado, y hoy anterior a v2
    "bitacora.md": 0.4,       # historico, NO fuente de verdad
}

ADVERTENCIAS = {
    "bitacora.md": "Diario de la migración: contexto histórico, **no fuente "
                   "de verdad**. Sus TODO pueden estar resueltos hace meses; "
                   "contrastá con dominio.md, linaje.md o HALLAZGOS.md.",
    "mapa.md": "Archivo generado. Si es anterior al último cambio grande, "
               "regeneralo con `python tools/mapa_modulos.py --escribir`.",
    "flujo_pipeline_gas.html": "Snapshot autocontenido: duplica a propósito "
                               "partes de otros documentos. Ante una "
                               "diferencia, gana el `.md`.",
}


# ===========================================================================
# Glosario
# ===========================================================================
#
# Lo unico escrito a mano de todo el modulo, y lo mas valioso para el que llega
# de afuera: los terminos que aparecen en la primera pantalla del tablero y no
# se entienden sin contexto. Cada entrada tiene sinonimos para que el buscador
# la encuentre aunque pregunten distinto.

GLOSARIO: dict[str, dict] = {
    "Cascada": {
        "sinonimos": ["eslabon", "eslabones", "orden", "topologico", "tren"],
        "texto": (
            "El gas no entra a una sola planta: pasa por una cadena, "
            "TTY-TBX -> TTY-Dew Point -> MEGA. Cada planta trata lo que puede "
            "y lo que le sobra se lo pasa a la siguiente. Se resuelve en "
            "orden: una planta se calcula recien cuando ya se sabe todo lo "
            "que le llega."),
    },
    "Evacuacion de LGN": {
        "sinonimos": ["restriccion", "tn/d", "toneladas", "capacidad", "limita"],
        "texto": (
            "LA REGLA QUE ORDENA TODO: lo que limita a una planta NO es "
            "cuanto gas puede recibir, sino cuanto LGN puede sacar, en "
            "toneladas por dia. Cada planta se llena hasta agotar esa "
            "capacidad, deriva el sobrante a la siguiente, y bypasea solo lo "
            "que ni asi entra."),
    },
    "Pool": {
        "sinonimos": ["nombre_pool", "matriz", "inyecciones", "gas disponible"],
        "texto": (
            "El conjunto de gas que le corresponde a una planta segun la "
            "matriz de inyecciones. Dos plantas pueden compartir pool "
            "(TTY-TBX y TTY-Dew Point son dos trenes sobre el mismo gas) o "
            "tener el suyo (MEGA)."),
    },
    "Retenidos y LGN": {
        "sinonimos": ["retencion", "rtp", "compuesto", "recupero", "liquidos"],
        "texto": (
            "El porcentaje de cada compuesto que la planta se queda (etano, "
            "propano, butanos...). Es lo que convierte el gas rico de entrada "
            "en gas residual mas LGN, los liquidos que se venden. Se define "
            "compuesto por compuesto."),
    },
    "Gas rico / gas residual": {
        "sinonimos": ["gas_rico_in", "residual", "entrada", "salida"],
        "texto": (
            "Rico es el gas como entra a la planta, con los pesados adentro. "
            "Residual es lo que sale despues de retener esos pesados. El "
            "residual siempre suma menos que la entrada: es fisicamente "
            "imposible que salga mas de lo que entro."),
    },
    "Bypass": {
        "sinonimos": ["no tratado", "pasa de largo", "sin procesar"],
        "texto": (
            "Gas que llega a la planta pero pasa de largo sin tratarse, por "
            "limite de capacidad. NO es lo mismo que el sobrante derivado: el "
            "derivado va a la planta siguiente, el bypass sigue de largo tal "
            "como esta."),
    },
    "Traspaso y derivacion": {
        "sinonimos": ["derivar", "sobrante", "mezcla", "tbx", "dew point"],
        "texto": (
            "Dos cosas distintas que no hay que unificar. TBX -> Dew Point es "
            "TRASPASO: es el mismo gas, misma composicion, solo cambia el "
            "volumen. Dew Point -> MEGA es DERIVACION: es otro gas, con otra "
            "composicion, y entra a la mezcla."),
    },
    "HUB y ruteo por HUB": {
        "sinonimos": ["hubs", "reparto", "area", "ruteo"],
        "texto": (
            "Un area con HUB asignado NO inyecta directo a la planta: su gas "
            "entra al hub, el hub lo mezcla con el de otras areas y lo "
            "reparte. Por eso el volumen de un area puede figurar contra un "
            "hub y no contra la planta. NO es gas perdido: el total que "
            "inyecta el area no cambia."),
    },
    "Desvio de balance": {
        "sinonimos": ["balance", "cierra", "control", "no cierra", "invariante"],
        "texto": (
            "Por cada planta tiene que valer vol_disponible = vol_asignado + "
            "vol_derivado + bypass. El desvio es cuanto se aparta de esa "
            "igualdad. Si no esta practicamente en cero, el resultado NO es "
            "confiable y no hay que usarlo."),
    },
    "Sandbox y su control": {
        "sinonimos": ["escenario", "simular", "que pasa si", "plantas nuevas"],
        "texto": (
            "El tab Plantas (sandbox) corre su PROPIA cascada, aparte de la "
            "oficial, para preguntar 'que pasa si' sin tocar los numeros "
            "validados. Con el registro sin tocar tiene que dar identico al "
            "oficial: eso es el bloque de control, y es el primer numero a "
            "mirar. Si no da cero, ningun escenario armado encima vale."),
    },
    "MMm3/d de 9.300 kcal": {
        "sinonimos": ["unidad", "std", "9300", "equivalente", "volumen"],
        "texto": (
            "Los volumenes se pueden ver en metros cubicos fisicos (STD) o en "
            "equivalentes de energia de 9.300 kcal. Es un selector de "
            "presentacion. Excepcion: el sandbox re-modela la fisica y "
            "trabaja siempre en STD."),
    },
    "Ampliaciones y PM": {
        "sinonimos": ["ampliacion", "mantenimiento", "parada", "pre-pm", "post-pm"],
        "texto": (
            "Las ampliaciones son incrementos de capacidad que se suman desde "
            "una fecha en adelante. La PM es la parada de mantenimiento: "
            "antes de esa fecha TTY-TBX esta fuera de servicio y el pool de "
            "TTY va directo a Dew Point."),
    },
    # Se conserva a proposito, aunque el modelo ya no lo calcule: quien viene
    # del Excel lo va a buscar, y una respuesta clara vale mas que un "sin
    # resultados" que lo deje pensando que se rompio algo.
    "PCS / Indice de Wobbe (ya no se calculan)": {
        "sinonimos": ["pcs", "iw", "wobbe", "calidad", "poder calorifico", "kcal"],
        "texto": (
            "OJO: el modelo YA NO calcula calidad de gas. No hay poder "
            "calorifico ni indice de Wobbe entre sus salidas (ver "
            "decisiones/0008). La tabla de propiedades por compuesto sigue "
            "siendo un input obligatorio, pero para el calculo de retenidos: "
            "se usa el peso molecular para pasar de fraccion molar a "
            "toneladas por dia."),
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

def _texto_de_html(bruto: str) -> str:
    """HTML a texto plano, suficiente para indexar.

    Sin dependencias: se sacan script/style enteros, se convierten los
    encabezados a markdown (para que el partido en secciones siga funcionando)
    y se tiran el resto de las etiquetas. No pretende ser un parser: pretende
    que `flujo_pipeline_gas.html` sea buscable, porque el README lo llama el
    mejor punto de entrada para alguien que viene del Excel y seria absurdo
    que fuera justo lo unico invisible para el buscador.
    """
    sin_scripts = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", bruto)
    con_titulos = re.sub(
        r"(?is)<h([1-3])[^>]*>(.*?)</h\1>",
        lambda m: "\n\n" + "#" * int(m.group(1)) + " "
                  + re.sub(r"<[^>]+>", "", m.group(2)).strip() + "\n",
        sin_scripts)
    sin_tags = re.sub(r"(?s)<[^>]+>", " ", con_titulos)
    limpio = (sin_tags.replace("&nbsp;", " ").replace("&amp;", "&")
              .replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"[ \t]{2,}", " ", limpio)


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
    """Lista de secciones de todos los documentos. Es barato: cachearlo."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []

    indice: list[dict] = []
    for ruta in sorted(list(carpeta.rglob("*.md")) + list(carpeta.rglob("*.html"))):
        if ruta.name in OBSOLETOS:
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 - un archivo ilegible no rompe el indice
            continue
        if ruta.suffix == ".html":
            texto = _texto_de_html(texto)

        peso = PESOS.get(ruta.name, 1.0)
        aviso = ADVERTENCIAS.get(ruta.name, "")
        for seccion in _partir_en_secciones(texto, ruta.as_posix()):
            seccion["titulo_plano"] = _plano(seccion["titulo"])
            seccion["cuerpo_plano"] = _plano(seccion["cuerpo"])
            seccion["peso"] = peso
            seccion["aviso"] = aviso
            indice.append(seccion)
    return indice


def obsoletos_presentes(carpeta: str | Path = "docs") -> list[str]:
    """Archivos que el README da por eliminados pero siguen en la carpeta.

    El buscador ya los ignora; esto es para poder AVISARLO en pantalla, porque
    mientras esten ahi alguien los va a abrir a mano y creerles.
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    return sorted(p.name for p in carpeta.rglob("*")
                  if p.name in OBSOLETOS)


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
                "puntaje": puntaje * seccion.get("peso", 1.0),
                "terminos": encontrados,
                "cobertura": len(encontrados) / len(terminos),
            })

    # Primero cuantos terminos DISTINTOS cubre, despues el puntaje ya pesado:
    # una seccion que menciona los tres terminos de la pregunta le gana a otra
    # que repite uno solo diez veces.
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
