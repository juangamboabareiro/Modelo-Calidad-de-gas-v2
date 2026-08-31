"""
Escenarios: plantas y gasoductos en un solo archivo.
====================================================

Un escenario es una pregunta completa ("que pasa si abro un ducto de Aguada a
TTY y ademas sumo un tren"), y esa pregunta no se parte en dos archivos. Hasta
ahora el JSON guardaba solo las plantas y las intervenciones sobre ductos se
perdian al recargar la pagina.

DOS FORMATOS, UNO SOLO VIGENTE
------------------------------
    lista   ->  formato viejo: solo plantas. Se sigue leyendo para no romper los
                escenarios ya guardados.
    dict    ->  formato actual: {"plantas": [...], "gasoductos": [...]}
                y opcionalmente {"canvas": {nodo: [x, y]}} con el layout del
                editor visual. Es cosmetico y opcional: un escenario sin esa
                clave se abre igual y el canvas se acomoda solo.

`aplicar` acepta los dos y `serializar` escribe siempre el nuevo.

MERGE, NO REEMPLAZO
-------------------
Las plantas se mezclan por nombre sobre el registro actual (ver
`plantas_editor.aplicar_escenario`): un escenario con una sola planta no se
lleva puestas las tres base, que se siembran desde los parametros de la sidebar.

Las intervenciones sobre ductos, en cambio, SE REEMPLAZAN enteras. Son una lista
ordenada donde el orden importa (las bajas se aplican antes que las altas), y
mezclar dos listas de intervenciones no tiene un significado claro: no hay clave
por la cual identificar "la misma" intervencion.
"""

from __future__ import annotations

import json


CLAVE_PLANTAS = "plantas"
CLAVE_GASODUCTOS = "gasoductos"
CLAVE_CANVAS = "canvas"


def serializar(registro, intervenciones, posiciones=None) -> str:
    """Escenario completo a JSON.

    `posiciones` es el layout del canvas ({nodo: (x, y)}, ver
    `ui.plantas_canvas.obtener_posiciones`). Solo se escribe si hay algo: un
    escenario armado sin tocar el canvas queda igual que antes.
    """
    datos = {
        CLAVE_PLANTAS: [p.a_dict() for p in (registro or {}).values()],
        CLAVE_GASODUCTOS: [i.a_dict() for i in (intervenciones or [])],
    }
    if posiciones:
        datos[CLAVE_CANVAS] = {
            str(nodo): [float(xy[0]), float(xy[1])]
            for nodo, xy in posiciones.items()
            if isinstance(xy, (tuple, list)) and len(xy) == 2
        }
    return json.dumps(datos, indent=2, ensure_ascii=False)


def posiciones_de(datos) -> dict:
    """Las posiciones del canvas de un escenario, si las trae. Tolerante:
    formato viejo (lista), clave ausente o valores rotos devuelven {} en vez
    de romper la carga — el layout es cosmetico, las plantas son lo que vale."""
    if not isinstance(datos, dict):
        return {}
    crudo = datos.get(CLAVE_CANVAS)
    if not isinstance(crudo, dict):
        return {}

    posiciones = {}
    for nodo, xy in crudo.items():
        try:
            x, y = float(xy[0]), float(xy[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        posiciones[str(nodo)] = (x, y)
    return posiciones


def partir(datos) -> tuple[list, list]:
    """Separa un escenario en (plantas, gasoductos), tolerando el formato viejo.

    Raises
    ------
    ValueError
        Si no es ni una lista de plantas ni un dict con las claves esperadas.
        Se falla explicito: un escenario que se lee a medias es peor que uno que
        no se lee, porque deja el sandbox en un estado que nadie pidio.
    """
    if isinstance(datos, list):
        # Formato viejo: la lista ES la lista de plantas.
        return datos, []

    if isinstance(datos, dict):
        plantas = datos.get(CLAVE_PLANTAS, [])
        gasoductos = datos.get(CLAVE_GASODUCTOS, [])

        if not isinstance(plantas, list) or not isinstance(gasoductos, list):
            raise ValueError(
                f"'{CLAVE_PLANTAS}' y '{CLAVE_GASODUCTOS}' tienen que ser listas.")

        return plantas, gasoductos

    raise ValueError(
        "El escenario tiene que ser una lista de plantas (formato viejo) o un "
        f"objeto con '{CLAVE_PLANTAS}' y '{CLAVE_GASODUCTOS}'. "
        f"Llegó un {type(datos).__name__}.")


def resumen(plantas: list, gasoductos: list) -> str:
    """Texto de una linea: que trae el escenario."""
    partes = []

    if plantas:
        partes.append(f"{len(plantas)} planta(s)")

    altas = sum(1 for g in gasoductos if g.get("tipo") == "alta")
    bajas = sum(1 for g in gasoductos if g.get("tipo") == "baja")

    if altas:
        partes.append(f"{altas} ducto(s) nuevo(s)")
    if bajas:
        partes.append(f"{bajas} ducto(s) fuera de servicio")

    return " · ".join(partes) if partes else "sin contenido"
