"""
Herramientas del agente del sandbox (bot 3).
============================================

Dos mitades que tienen que mantenerse a mano:

  - ESQUEMAS: lo que se declara a la API (nombre, descripcion, input_schema).
  - EJECUTORES: la funcion python que corre cuando el modelo pide esa tool.

Principios de diseño:

  1. El agente opera sobre EL MISMO estado que la UI del sandbox
     (`st.session_state["registro_plantas"]`, `"intervenciones_gasoductos"`,
     `"sandbox_resultado"`). Lo que arma el agente queda visible y editable en
     el tab Plantas (sandbox), y viceversa.

  2. Nada de este modulo conoce los campos internos de `PlantaConfig` mas alla
     de lo minimo: para editar se hace round-trip por `a_dict()`/`desde_dict()`
     y para conectar se usa `ConexionSalida.desde_dict`. Si el registro cambia
     de forma, el error textual vuelve al modelo, que ve los campos reales via
     `ver_planta` y se corrige solo. Es la misma filosofia que los escenarios.

  3. TODO ejecutor devuelve str y NUNCA levanta: el loop del agente envuelve
     igual en try/except, pero la regla es que un fallo de herramienta es un
     mensaje para el modelo, no una excepcion para Streamlit.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

# Frontera unica con el pipeline de gasoductos, igual que ui/tab_plantas.py:
# si el paquete no esta, estas funciones existen igual y devuelven vacio.
from ui.gasoductos_editor import (
    obtener_intervenciones,
    DISPONIBLE as GASODUCTOS_DISPONIBLE,
)

CLAVE_REGISTRO = "registro_plantas"
CLAVE_INTERVENCIONES = "intervenciones_gasoductos"
CLAVE_RESULTADO = "sandbox_resultado"
CLAVE_INFORME = "sandbox_informe_ductos"

_COLS_VOL = ["vol_disponible", "vol_maximo", "vol_asignado",
             "sobrante", "vol_derivado", "bypass"]


# ===========================================================================
# Esquemas (lo que ve la API)
# ===========================================================================

ESQUEMAS = [
    {
        "name": "ver_registro",
        "description": (
            "Lista las plantas del sandbox: nombre, si esta activa, si es base "
            "y a que plantas manda el sobrante. Empeza siempre por aca."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ver_planta",
        "description": (
            "Devuelve la configuracion COMPLETA de una planta como JSON "
            "(capacidades, retenidos, conexiones, con los nombres de campo "
            "reales). Usalo antes de editar para saber que campos existen."),
        "input_schema": {
            "type": "object",
            "properties": {"nombre": {"type": "string"}},
            "required": ["nombre"],
        },
    },
    {
        "name": "crear_planta",
        "description": (
            "Crea una planta nueva en el sandbox a partir de un preset. "
            "Arranca sin retencion, sin capacidades y sin conexiones: despues "
            "hay que configurarla con editar_planta / conectar_plantas."),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "preset": {"type": "string",
                           "description": "Uno de los presets del registro. "
                           "Si no sabes cuales hay, proba y el error los lista."},
                "nombre_pool": {"type": "string",
                                "description": "Columna de la matriz de "
                                "inyecciones de la que toma gas. Omitir si es "
                                "igual al nombre."},
            },
            "required": ["nombre", "preset"],
        },
    },
    {
        "name": "editar_planta",
        "description": (
            "Modifica campos de una planta. `cambios` es un objeto con pares "
            "campo->valor que se aplican sobre el dict de la planta (los "
            "campos validos son los que muestra ver_planta). Ejemplos tipicos: "
            "activa (bool), capacidades y topes (numeros, en Mm3/d)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "cambios": {"type": "object"},
            },
            "required": ["nombre", "cambios"],
        },
    },
    {
        "name": "conectar_plantas",
        "description": (
            "Define a donde manda el sobrante una planta. `conexiones` "
            "REEMPLAZA la lista actual: es una lista de objetos con la misma "
            "forma que muestra ver_planta en su campo de conexiones (destino, "
            "proporcion/tope segun corresponda)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "conexiones": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["nombre", "conexiones"],
        },
    },
    {
        "name": "intervenir_gasoducto",
        "description": (
            "Alta o baja de un gasoducto en el sandbox. Para 'baja' alcanza "
            "con el nombre del ducto. Para 'alta' hay que dar area_origen, "
            "planta_destino y fraccion (0-1, porcion de lo que inyecta el "
            "area) — la cromatografia se toma del area. El total inyectado "
            "por el area no cambia: solo se redistribuye."),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["alta", "baja"]},
                "nombre": {"type": "string"},
                "area_origen": {"type": "string"},
                "planta_destino": {"type": "string"},
                "fraccion": {"type": "number"},
            },
            "required": ["tipo", "nombre"],
        },
    },
    {
        "name": "resolver_cascada",
        "description": (
            "Valida el registro, aplica las intervenciones de ductos y corre "
            "la cascada del sandbox. Devuelve la tabla de flujos en MMm3/d y "
            "deja el resultado visible en el tab Plantas (sandbox)."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "comparar_con_oficial",
        "description": (
            "Diferencia de vol_asignado por planta entre la ultima corrida "
            "del sandbox y la corrida oficial del tablero. Positivo = la "
            "planta trata MAS gas en el escenario."),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ===========================================================================
# Ejecutores
# ===========================================================================

class Ejecutor:
    """Ata las herramientas al estado de ESTA sesion de Streamlit.

    `comunes` y `flujos_oficiales` llegan desde `resultados` (fisicos, STD),
    igual que los recibe el tab del sandbox.
    """

    def __init__(self, comunes: dict, flujos_oficiales, factor_mm: float = 1000.0):
        self.comunes = comunes
        self.flujos_oficiales = flujos_oficiales
        self.factor_mm = factor_mm

    # -- helpers ------------------------------------------------------------

    def _registro(self) -> dict:
        registro = st.session_state.get(CLAVE_REGISTRO)
        if not registro:
            raise RuntimeError(
                "El registro del sandbox no esta inicializado. El usuario "
                "tiene que abrir el tab 'Plantas (sandbox)' al menos una vez, "
                "o correr el pipeline.")
        return registro

    def _planta_a_dict(self, planta) -> dict:
        if hasattr(planta, "a_dict"):
            return planta.a_dict()
        return {k: v for k, v in vars(planta).items()}  # ultimo recurso

    # -- tools ----------------------------------------------------------------

    def ver_registro(self) -> str:
        registro = self._registro()
        lineas = []
        for nombre, p in registro.items():
            destinos = ", ".join(
                getattr(c, "destino", "?") for c in getattr(p, "conexiones", [])
            ) or "(sin conexiones)"
            lineas.append(
                f"- {nombre}: activa={getattr(p, 'activa', '?')}, "
                f"base={getattr(p, 'es_base', '?')}, sobrante -> {destinos}")
        ductos = obtener_intervenciones()
        lineas.append(f"\nIntervenciones de ductos pendientes: {len(ductos)}")
        if not GASODUCTOS_DISPONIBLE:
            lineas.append("(el paquete de gasoductos NO esta disponible: "
                          "intervenir_gasoducto va a fallar)")
        return "\n".join(lineas)

    def ver_planta(self, nombre: str) -> str:
        registro = self._registro()
        if nombre not in registro:
            return (f"No existe '{nombre}'. Plantas: "
                    f"{', '.join(registro)}")
        d = self._planta_a_dict(registro[nombre])
        return json.dumps(d, default=str, ensure_ascii=False, indent=1)

    def crear_planta(self, nombre: str, preset: str,
                     nombre_pool: str | None = None) -> str:
        from pipeline.plantas.registro import crear_planta, PRESETS
        registro = self._registro()
        nombre = (nombre or "").strip()
        if not nombre:
            return "Falta el nombre."
        if nombre in registro:
            return f"Ya existe '{nombre}'. Usa editar_planta si queres tocarla."
        try:
            registro[nombre] = crear_planta(
                nombre, preset=preset,
                compuestos=self.comunes["COMPUESTOS"],
                nombre_pool=(nombre_pool or "").strip() or None)
        except Exception as e:  # noqa: BLE001
            return (f"crear_planta fallo: {type(e).__name__}: {e}. "
                    f"Presets disponibles: {list(PRESETS)}")
        return (f"'{nombre}' creada con preset {preset}. Arranca sin "
                "retencion, capacidades ni conexiones: configurala.")

    def editar_planta(self, nombre: str, cambios: dict) -> str:
        from pipeline.plantas.registro import PlantaConfig
        registro = self._registro()
        if nombre not in registro:
            return f"No existe '{nombre}'. Plantas: {', '.join(registro)}"
        base = self._planta_a_dict(registro[nombre])
        desconocidos = [k for k in cambios if k not in base]
        if desconocidos:
            return (f"Campos inexistentes: {desconocidos}. Los validos son: "
                    f"{sorted(base)}")
        try:
            registro[nombre] = PlantaConfig.desde_dict({**base, **cambios})
        except Exception as e:  # noqa: BLE001
            return (f"No se pudo aplicar: {type(e).__name__}: {e}. "
                    "Mira ver_planta para la forma exacta de cada campo.")
        return f"'{nombre}' actualizada: {sorted(cambios)}."

    def conectar_plantas(self, nombre: str, conexiones: list[dict]) -> str:
        from pipeline.plantas.registro import ConexionSalida
        registro = self._registro()
        if nombre not in registro:
            return f"No existe '{nombre}'. Plantas: {', '.join(registro)}"
        try:
            nuevas = [ConexionSalida.desde_dict(c) for c in conexiones]
        except Exception as e:  # noqa: BLE001
            ejemplo = "?"
            for p in registro.values():
                if getattr(p, "conexiones", None):
                    ejemplo = json.dumps(
                        self._planta_a_dict(p).get("conexiones"), default=str)
                    break
            return (f"Conexiones invalidas: {type(e).__name__}: {e}. "
                    f"Un ejemplo valido del registro actual: {ejemplo}")
        faltan = [c.destino for c in nuevas if c.destino not in registro]
        if faltan:
            return f"Destinos inexistentes: {faltan}. Plantas: {', '.join(registro)}"
        registro[nombre].conexiones = nuevas
        return f"'{nombre}' ahora deriva a: {[c.destino for c in nuevas]}."

    def intervenir_gasoducto(self, tipo: str, nombre: str,
                             area_origen: str | None = None,
                             planta_destino: str | None = None,
                             fraccion: float | None = None) -> str:
        if not GASODUCTOS_DISPONIBLE:
            return "El paquete de gasoductos no esta disponible en este deploy."
        from ui.gasoductos_editor import Intervencion
        try:
            if tipo == "baja":
                iv = Intervencion(tipo="baja", nombre=nombre)
            else:
                if not (area_origen and planta_destino and fraccion is not None):
                    return ("Para un alta hacen falta area_origen, "
                            "planta_destino y fraccion (0-1).")
                iv = Intervencion(tipo="alta", nombre=nombre,
                                  area_origen=area_origen,
                                  planta_destino=planta_destino,
                                  fraccion=float(fraccion))
        except Exception as e:  # noqa: BLE001
            return f"No se pudo armar la intervencion: {type(e).__name__}: {e}"

        st.session_state.setdefault(CLAVE_INTERVENCIONES, []).append(iv)
        return (f"Intervencion registrada: {tipo} de '{nombre}'. Se aplica al "
                "correr resolver_cascada.")

    def resolver_cascada(self) -> str:
        from pipeline.plantas.registro import validar_registro
        from pipeline.plantas.cascada import resolver_cascada

        registro = self._registro()
        try:
            errores = validar_registro(registro) or []
        except Exception:  # noqa: BLE001 - firma distinta: que valide la cascada
            errores = []
        if errores:
            return "El registro no valida:\n- " + "\n- ".join(map(str, errores))

        # Mismas dos etapas que el boton del tab: ductos primero, cascada
        # despues. `_comunes_con_ductos` es privado del tab pero es EXACTAMENTE
        # la logica que hay que replicar; si algun dia se renombra, el fallback
        # corre sin intervenciones y lo dice.
        comunes_efectivo, informe = self.comunes, None
        intervenciones = obtener_intervenciones()
        if intervenciones:
            try:
                from ui.tab_plantas import _comunes_con_ductos
                comunes_efectivo, informe = _comunes_con_ductos(
                    self.comunes, intervenciones, self.comunes["COMPUESTOS"])
            except Exception as e:  # noqa: BLE001
                return (f"No se pudieron aplicar las intervenciones de ductos: "
                        f"{type(e).__name__}: {e}")

        try:
            plantas, flujos = resolver_cascada(registro, comunes_efectivo)
        except Exception as e:  # noqa: BLE001
            st.session_state.pop(CLAVE_RESULTADO, None)
            return f"La cascada fallo: {type(e).__name__}: {e}"

        st.session_state[CLAVE_RESULTADO] = (plantas, flujos)
        st.session_state[CLAVE_INFORME] = informe

        vista = flujos.copy()
        for col in _COLS_VOL:
            if col in vista.columns:
                vista[col] = vista[col] / self.factor_mm
        extra = ""
        if informe is not None:
            avisos = list(getattr(informe, "avisos", [])) + \
                     list(getattr(informe, "errores", []))
            if avisos:
                extra = "\nAvisos de ductos:\n- " + "\n- ".join(map(str, avisos))
        return ("Cascada resuelta (MMm3/d, LGN tn/d). El resultado quedo "
                "visible en el tab Plantas (sandbox).\n"
                + vista.round(3).to_string() + extra)

    def comparar_con_oficial(self) -> str:
        guardado = st.session_state.get(CLAVE_RESULTADO)
        if guardado is None:
            return "Todavia no corriste resolver_cascada."
        if self.flujos_oficiales is None or not isinstance(
                self.flujos_oficiales, pd.DataFrame):
            return "No hay corrida oficial cargada para comparar."
        _, flujos = guardado
        comunes_idx = flujos.index.intersection(self.flujos_oficiales.index)
        diff = (flujos.loc[comunes_idx, "vol_asignado"]
                - self.flujos_oficiales.loc[comunes_idx, "vol_asignado"]) \
            / self.factor_mm
        solo_sandbox = flujos.index.difference(self.flujos_oficiales.index)
        texto = ("Delta de vol_asignado (sandbox - oficial), MMm3/d:\n"
                 + diff.round(3).to_string())
        if len(solo_sandbox):
            texto += f"\nPlantas solo en el sandbox: {list(solo_sandbox)}"
        return texto

    # -- dispatch -------------------------------------------------------------

    def ejecutar(self, nombre: str, argumentos: dict) -> str:
        fn = getattr(self, nombre, None)
        if fn is None or nombre.startswith("_"):
            return f"Herramienta desconocida: {nombre}"
        try:
            return fn(**(argumentos or {}))
        except TypeError as e:
            return f"Argumentos invalidos para {nombre}: {e}"
        except Exception as e:  # noqa: BLE001 - el error es un mensaje para el modelo
            return f"{nombre} fallo: {type(e).__name__}: {e}"
