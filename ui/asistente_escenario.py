"""
Asistente de escenarios: el "que pasa si", preguntado y respondido.
===================================================================

Un flujo guiado con aspecto de chat que arma el escenario paso a paso —
"¿que pasa si sumo una planta en Aguada con esta cromatografia y 400 tn/d?" —
y lo deja corrido: aplica los cambios al MISMO registro e intervenciones que
edita el resto del sandbox y dispara la cascada (y la serie, si se pide).

POR QUE GUIADO Y NO TEXTO LIBRE
-------------------------------
Sin una API de lenguaje, interpretar texto libre es adivinar, y adivinar
capacidades o conexiones da numeros mal EN SILENCIO, que es lo peor que le
puede pasar a este tablero. El asistente pregunta de a una cosa, con las
opciones reales del modelo, y al final muestra el resumen ANTES de aplicar.
El dia que haya presupuesto para una API key, este mismo modulo es el lugar
donde enchufarla: el contrato de salida (crear_planta + ConexionSalida +
Intervencion) ya queda armado.

COMO SE INTEGRA
---------------
`panel_asistente` dibuja el chat y, cuando el usuario confirma, MUTA el
registro / la lista de intervenciones y deja una orden en session_state
(`bot_orden` = "resolver" | "resolver_y_serie") que `tab_plantas` consume en
el mismo rerun para correr. No hay un segundo camino de ejecucion: el
asistente aprieta el mismo boton que el usuario.

Todas las claves de estado arrancan con `bot_` para que el reset del sandbox
las barra (ver PREFIJOS_WIDGETS en ui/sandbox_estado.py).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.compat import ancho

from pipeline.plantas.registro import (
    PRESETS, ConexionSalida, crear_planta, validar_registro, INFINITO)
# Frontera unica con pipeline.gasoductos: si el paquete no esta, Intervencion
# es None y el paso de ductos se deshabilita con aviso, sin tumbar nada.
from ui.gasoductos_editor import obtener_intervenciones, Intervencion


CLAVE_CHARLA = "bot_charla"      # [(rol, texto)] transcript ya respondido
CLAVE_PASO = "bot_paso"          # id del paso actual
CLAVE_BORRADOR = "bot_borrador"  # dict con las respuestas juntadas
CLAVE_ORDEN = "bot_orden"        # la consume tab_plantas: "resolver" | "resolver_y_serie"

_INTENTS = {
    "planta": "Sumar una planta nueva",
    "capacidad": "Cambiar la capacidad de una planta",
    "servicio": "Sacar de servicio / reactivar una planta",
    "ducto": "Abrir un gasoducto nuevo",
}

_FUENTES = {
    "ducto": "Pool propio, alimentado por un gasoducto nuevo desde un área",
    "tren": "Es otro tren sobre el gas de una planta existente (mismo pool)",
    "derivacion": "Recibe el sobrante de otra planta (otra composición)",
    "croma": "Sólo una corriente propia con cromatografía que voy a pegar",
}


def consumir_orden() -> str | None:
    """La orden pendiente del asistente, si hay. La lee tab_plantas."""
    return st.session_state.pop(CLAVE_ORDEN, None)


def panel_asistente(registro, compuestos, comunes, nombres_areas,
                    factor_mm=1000.0, meses_serie: int = 0):
    """Dibuja el asistente. Muta `registro` e intervenciones al confirmar."""

    st.caption(
        "Contame el **qué pasa si** de a un paso y lo dejo corrido: armo la "
        "planta o el ducto en el sandbox, resuelvo la cascada y, si querés, "
        "calculo la serie para verlo en **Graphs**. Todo lo que arme acá "
        "queda editable en los otros sub-tabs y se descarga como escenario.")

    charla = st.session_state.setdefault(CLAVE_CHARLA, [])
    borrador = st.session_state.setdefault(CLAVE_BORRADOR, {})
    paso = st.session_state.get(CLAVE_PASO, "intent")

    for rol, texto in charla:
        with st.chat_message(rol):
            st.markdown(texto)

    with st.chat_message("assistant"):
        try:
            _PASOS[paso](registro, compuestos, comunes, nombres_areas,
                         factor_mm, meses_serie, borrador)
        except KeyError:
            _reiniciar()
            st.rerun()

    if charla or paso != "intent":
        if st.button("Empezar de nuevo", key="bot_reset"):
            _reiniciar()
            _rerun()


# ===========================================================================
# Mecanica de pasos
# ===========================================================================

def _decir(rol: str, texto: str):
    st.session_state[CLAVE_CHARLA].append((rol, texto))


def _ir_a(paso: str):
    st.session_state[CLAVE_PASO] = paso
    _rerun()


def _reiniciar():
    for clave in (CLAVE_CHARLA, CLAVE_PASO, CLAVE_BORRADOR):
        st.session_state.pop(clave, None)


def _rerun():
    # El asistente vive adentro del fragment del editor: alcanza con rerunear
    # el fragment. `plantas_editor._rerun` ya resuelve el scope correcto.
    from ui.plantas_editor import _rerun as rerun_editor
    rerun_editor()


# ===========================================================================
# Pasos
# ===========================================================================

def _paso_intent(registro, compuestos, comunes, nombres, factor_mm,
                 meses_serie, borrador):
    st.markdown("¿Qué querés probar?")
    eleccion = st.radio(
        "Intención", list(_INTENTS.values()), key="bot_intent",
        label_visibility="collapsed")

    if st.button("Continuar", type="primary", key="bot_go_intent"):
        intent = next(k for k, v in _INTENTS.items() if v == eleccion)
        borrador.clear()
        borrador["intent"] = intent
        _decir("user", eleccion)
        _ir_a({"planta": "p_nombre", "capacidad": "c_planta",
               "servicio": "s_planta", "ducto": "d_datos"}[intent])


# --- Sumar una planta -------------------------------------------------------

def _paso_p_nombre(registro, compuestos, comunes, nombres, factor_mm,
                   meses_serie, borrador):
    st.markdown("¿Cómo se llama la planta y con qué **features** arranca? "
                "El modelo es uno solo: el preset sólo carga los valores "
                "iniciales, después se puede cambiar todo.")
    nombre = st.text_input("Nombre", key="bot_p_nombre")
    preset = st.radio(
        "Preset", list(PRESETS), key="bot_p_preset",
        captions=[_describir_preset(p) for p in PRESETS])

    if st.button("Continuar", type="primary", key="bot_go_p1"):
        nombre = (nombre or "").strip()
        if not nombre:
            st.error("Poné un nombre.")
            return
        if nombre in registro:
            st.error(f"Ya existe una planta llamada '{nombre}'.")
            return
        borrador.update(nombre=nombre, preset=preset)
        _decir("user", f"Se llama **{nombre}**, preset **{preset}**.")
        _ir_a("p_fuente")


def _paso_p_fuente(registro, compuestos, comunes, nombres, factor_mm,
                   meses_serie, borrador):
    st.markdown(f"¿De dónde le llega el gas a **{borrador['nombre']}**?")

    opciones = dict(_FUENTES)
    if Intervencion is None:
        opciones.pop("ducto")
        st.caption("(La opción de gasoducto nuevo no está: falta "
                   "`pipeline/gasoductos/`.)")

    eleccion = st.radio("Fuente", list(opciones.values()), key="bot_p_fuente",
                        label_visibility="collapsed")
    fuente = next(k for k, v in opciones.items() if v == eleccion)

    otras = sorted(registro)

    if fuente == "ducto":
        areas = _areas_disponibles(comunes)
        area = st.selectbox(
            "Área de origen", areas, key="bot_p_area",
            format_func=lambda a: (nombres or {}).get(str(a), str(a)),
            help="El total que inyecta el área no cambia: se redistribuye "
                 "hacia el ducto nuevo.")
        volumen = st.number_input(
            "Volumen por el ducto [MMm3/d]", min_value=0.0, step=0.5,
            key="bot_p_vol_ducto")
    elif fuente == "tren":
        companera = st.selectbox(
            "¿Sobre el gas de qué planta?", otras, key="bot_p_tren",
            help="Mismo pool, cromatografía idéntica: la elegida le pasa el "
                 "sobrante como TBX a Dew Point.")
    elif fuente == "derivacion":
        origen = st.selectbox("¿Qué planta le deriva su sobrante?", otras,
                              key="bot_p_deriv_origen")
        proporcion = st.slider("% del sobrante de esa planta", 5, 100, 100,
                               step=5, key="bot_p_deriv_prop")
        tope = st.number_input("Tope de la derivación [MMm3/d] (0 = sin tope)",
                               min_value=0.0, step=1.0, key="bot_p_deriv_tope")

    if fuente in ("ducto", "tren", "derivacion", "croma"):
        with st.expander("Además, tiene una corriente propia con cromatografía"
                         if fuente != "croma" else
                         "Cromatografía de la corriente", expanded=(fuente == "croma")):
            croma_df, croma_vol = _editor_croma(compuestos)

    if st.button("Continuar", type="primary", key="bot_go_p2"):
        borrador["fuente"] = fuente
        if fuente == "ducto":
            if volumen <= 0:
                st.error("El ducto necesita un volumen mayor a cero.")
                return
            borrador.update(area=area, vol_ducto=volumen)
            _decir("user", f"Pool propio: ducto nuevo desde "
                           f"**{(nombres or {}).get(str(area), str(area))}** por "
                           f"{volumen:,.2f} MMm3/d.")
        elif fuente == "tren":
            borrador["companera"] = companera
            _decir("user", f"Otro tren sobre el gas de **{companera}**.")
        elif fuente == "derivacion":
            borrador.update(deriv_origen=origen, deriv_prop=proporcion / 100.0,
                            deriv_tope=tope)
            _decir("user", f"Recibe el {proporcion}% del sobrante de "
                           f"**{origen}**"
                           + (f" (tope {tope:,.2f} MMm3/d)." if tope > 0 else "."))
        else:
            _decir("user", "Sólo la corriente propia con cromatografía.")

        croma = _leer_croma(croma_df, croma_vol, compuestos, factor_mm)
        if fuente == "croma" and croma is None:
            st.error("Cargá la composición y un volumen mayor a cero.")
            return
        if croma is not None:
            borrador["croma"] = croma
            _decir("user", f"Con una corriente propia de "
                           f"{croma['vol_derivacion'] / factor_mm:,.2f} MMm3/d.")
        _ir_a("p_capacidades")


def _paso_p_capacidades(registro, compuestos, comunes, nombres, factor_mm,
                        meses_serie, borrador):
    st.markdown("Capacidades y retención.")
    evac = st.number_input(
        "Capacidad de evacuación de LGN [tn/d] (0 = sin límite)",
        min_value=0.0, step=100.0, key="bot_p_evac",
        help="Es la restricción activa del modelo.")
    ing = st.number_input(
        "Capacidad de ingreso de gas [MMm3/d] (0 = sin límite)",
        min_value=0.0, step=1.0, key="bot_p_ing")

    fuente_ret = st.selectbox(
        "Retención por compuesto",
        ["Copiar de una planta existente", "Sin retención (todo en 0, la cargo después)"],
        key="bot_p_ret_modo")
    ret_de = None
    if fuente_ret.startswith("Copiar"):
        ret_de = st.selectbox("Copiar de", sorted(registro), key="bot_p_ret_de")

    if st.button("Continuar", type="primary", key="bot_go_p3"):
        borrador.update(evac=evac, ingreso=ing, ret_de=ret_de)
        _decir("user",
               f"Evacuación {evac:,.0f} tn/d" + (" (sin límite)" if evac == 0 else "")
               + f", ingreso {ing:,.1f} MMm3/d" + (" (sin límite)" if ing == 0 else "")
               + (f", retención copiada de **{ret_de}**." if ret_de
                  else ", sin retención por ahora."))
        _ir_a("p_salida")


def _paso_p_salida(registro, compuestos, comunes, nombres, factor_mm,
                   meses_serie, borrador):
    st.markdown(f"¿Y el **sobrante** de {borrador['nombre']}, a dónde va?")
    terminal = st.radio(
        "Salida", ["Es terminal: todo el sobrante es bypass",
                   "Deriva el sobrante a otra planta"],
        key="bot_p_salida", label_visibility="collapsed")

    destino = prop = tope = None
    if terminal.startswith("Deriva"):
        destino = st.selectbox("Destino", sorted(registro), key="bot_p_out_dest")
        prop = st.slider("% del sobrante", 5, 100, 100, step=5,
                         key="bot_p_out_prop")
        tope = st.number_input("Tope [MMm3/d] (0 = sin tope)", min_value=0.0,
                               step=1.0, key="bot_p_out_tope")

    if st.button("Continuar", type="primary", key="bot_go_p4"):
        if destino:
            borrador.update(out_destino=destino, out_prop=prop / 100.0,
                            out_tope=tope)
            _decir("user", f"Deriva el {prop}% del sobrante a **{destino}**"
                           + (f" con tope {tope:,.2f} MMm3/d." if tope > 0 else "."))
        else:
            borrador["out_destino"] = None
            _decir("user", "Terminal: el sobrante que no trata es bypass.")
        _ir_a("p_resumen")


def _paso_p_resumen(registro, compuestos, comunes, nombres, factor_mm,
                    meses_serie, borrador):
    st.markdown("**Resumen del escenario** — esto es lo que voy a armar:")
    st.markdown(_resumen_planta(borrador, nombres, factor_mm))
    _botones_aplicar(meses_serie,
                     lambda: _aplicar_planta(registro, compuestos, borrador,
                                             factor_mm),
                     registro)


# --- Cambiar capacidad ------------------------------------------------------

def _paso_c_planta(registro, compuestos, comunes, nombres, factor_mm,
                   meses_serie, borrador):
    st.markdown("¿A qué planta y qué capacidades?")
    planta = st.selectbox("Planta", sorted(registro), key="bot_c_planta")
    actual = registro[planta]

    evac_actual = (0.0 if actual.capacidad_evacuacion == INFINITO
                   else float(actual.capacidad_evacuacion))
    ing_actual = (0.0 if actual.capacidad_ingreso is None
                  else float(actual.capacidad_ingreso) / factor_mm)

    evac = st.number_input("Evacuación de LGN [tn/d] (0 = sin límite)",
                           value=evac_actual, min_value=0.0, step=100.0,
                           key=f"bot_c_evac_{planta}")
    ing = st.number_input("Ingreso de gas [MMm3/d] (0 = sin límite)",
                          value=ing_actual, min_value=0.0, step=1.0,
                          key=f"bot_c_ing_{planta}")

    def _aplicar():
        actual.capacidad_evacuacion = INFINITO if evac == 0 else evac
        actual.capacidad_ingreso = None if ing == 0 else ing * factor_mm
        return (f"**{planta}**: evacuación → {evac:,.0f} tn/d, "
                f"ingreso → {ing:,.1f} MMm3/d (0 = sin límite).")

    _botones_aplicar(meses_serie, _aplicar, registro)


# --- Servicio ----------------------------------------------------------------

def _paso_s_planta(registro, compuestos, comunes, nombres, factor_mm,
                   meses_serie, borrador):
    st.markdown("¿Qué planta prendo o apago?")
    candidatas = [n for n in sorted(registro) if n != "TTY - TBX"]
    st.caption("TTY - TBX no está en la lista: su estado lo manda la fecha de "
               "PM de la sidebar y se re-fuerza en cada corrida.")
    planta = st.selectbox("Planta", candidatas, key="bot_s_planta")
    if planta is None:
        st.info("No hay plantas para operar.")
        return
    estado = "en servicio" if registro[planta].activa else "fuera de servicio"
    st.markdown(f"Hoy está **{estado}**.")

    def _aplicar():
        registro[planta].activa = not registro[planta].activa
        nuevo = "en servicio" if registro[planta].activa else "fuera de servicio"
        return f"**{planta}** pasa a estar **{nuevo}**."

    _botones_aplicar(meses_serie, _aplicar, registro,
                     etiqueta=f"{'Reactivar' if not registro[planta].activa else 'Sacar de servicio'} y resolver")


# --- Ducto nuevo --------------------------------------------------------------

def _paso_d_datos(registro, compuestos, comunes, nombres, factor_mm,
                  meses_serie, borrador):
    if Intervencion is None:
        st.warning("No se pueden crear ductos: falta `pipeline/gasoductos/`. "
                   "Las bajas y altas se manejan en el sub-tab **Gasoductos**.")
        return

    st.markdown("¿De dónde a dónde, y cuánto gas mueve?")
    areas = _areas_disponibles(comunes)
    area = st.selectbox(
        "Área de origen", areas, key="bot_d_area",
        format_func=lambda a: (nombres or {}).get(str(a), str(a)))
    destinos = _destinos_disponibles(registro, comunes)
    destino = st.selectbox("Destino (pool / planta / gasoducto)", destinos,
                           key="bot_d_destino")
    nombre = st.text_input("Nombre del ducto nuevo", key="bot_d_nombre")
    volumen = st.number_input("Volumen [MMm3/d]", min_value=0.0, step=0.5,
                              key="bot_d_vol")
    st.caption("El total que inyecta el área no cambia: se redistribuye "
               "entre sus destinos. Para DAR DE BAJA un ducto, usá el sub-tab "
               "**Gasoductos**.")

    def _aplicar():
        obtener_intervenciones().append(Intervencion(
            "alta", (nombre or "").strip() or f"Ducto {area}-{destino}",
            area_origen=area, planta_destino=destino,
            volumen=volumen * factor_mm))
        return (f"Ducto nuevo **{(nombre or '').strip() or 'sin nombre'}**: "
                f"**{(nombres or {}).get(str(area), str(area))} → {destino}** "
                f"por {volumen:,.2f} MMm3/d.")

    if volumen <= 0:
        st.info("Poné un volumen mayor a cero para poder aplicar.")
        return
    _botones_aplicar(meses_serie, _aplicar, registro)


# ===========================================================================
# Aplicar
# ===========================================================================

def _botones_aplicar(meses_serie, aplicar, registro,
                     etiqueta="Aplicar y resolver cascada"):
    """Los botones finales de cualquier flujo. `aplicar` muta y devuelve el
    texto para el transcript."""
    col_a, col_b = st.columns(2)

    correr = col_a.button(etiqueta, type="primary", key="bot_aplicar", **ancho())
    correr_serie = False
    if meses_serie:
        correr_serie = col_b.button(
            f"Aplicar, resolver y calcular serie ({meses_serie} meses)",
            key="bot_aplicar_serie", **ancho(),
            help="Además de la cascada del período actual, corre el escenario "
                 "mes a mes para verlo en el tab Graphs.")

    if not (correr or correr_serie):
        return

    resumen = aplicar()

    errores, _ = validar_registro(registro)
    if errores:
        # Se aplicó igual (queda editable en los otros sub-tabs), pero no se
        # corre nada: correr con errores solo produce un traceback.
        st.error("Se aplicó, pero la configuración quedó con errores y no se "
                 "corre hasta corregirlos en el sub-tab **Plantas**:\n\n"
                 + "\n".join(f"- {e}" for e in errores))
        _decir("assistant", f"{resumen}\n\n⚠️ Quedó con errores de validación: "
                            "corregilos en el sub-tab Plantas.")
        _terminar_flujo()
        return

    _decir("assistant", resumen + "\n\nAplicado ✅ — resolviendo…")
    st.session_state[CLAVE_ORDEN] = ("resolver_y_serie" if correr_serie
                                     else "resolver")
    _terminar_flujo()


def _terminar_flujo():
    st.session_state[CLAVE_PASO] = "intent"
    st.session_state[CLAVE_BORRADOR] = {}
    _rerun()


def _aplicar_planta(registro, compuestos, borrador, factor_mm) -> str:
    """Crea la planta del borrador sobre el registro. Devuelve el resumen."""
    nombre = borrador["nombre"]
    fuente = borrador["fuente"]

    nombre_pool = (registro[borrador["companera"]].nombre_pool
                   if fuente == "tren" else nombre)

    retenidos = None
    if borrador.get("ret_de"):
        origen = registro[borrador["ret_de"]].retenidos
        retenidos = origen.copy() if origen is not None else None
    if retenidos is None:
        retenidos = pd.DataFrame([{c: 0.0 for c in compuestos}])

    conexiones = []
    if borrador.get("out_destino"):
        tope = float(borrador.get("out_tope") or 0.0)
        conexiones.append(ConexionSalida(
            destino=borrador["out_destino"],
            proporcion=float(borrador.get("out_prop", 1.0)),
            tope=INFINITO if tope <= 0 else tope * factor_mm,
            comparte_pool=False,
        ))

    registro[nombre] = crear_planta(
        nombre,
        preset=borrador.get("preset"),
        compuestos=compuestos,
        nombre_pool=nombre_pool,
        retenidos=retenidos,
        capacidad_evacuacion=(None if borrador.get("evac", 0) == 0
                              else float(borrador["evac"])),
        capacidad_ingreso=(None if borrador.get("ingreso", 0) == 0
                           else float(borrador["ingreso"]) * factor_mm),
        conexiones=conexiones,
        deriva=bool(conexiones),
        toma_volumen_del_pool=(fuente in ("ducto", "croma")),
    )

    if borrador.get("croma"):
        registro[nombre].cromas_extra = [borrador["croma"]]

    if fuente == "tren":
        registro[borrador["companera"]].conexiones.append(ConexionSalida(
            destino=nombre, proporcion=1.0, tope=INFINITO, comparte_pool=True))
        registro[borrador["companera"]].deriva = True
    elif fuente == "derivacion":
        tope = float(borrador.get("deriv_tope") or 0.0)
        registro[borrador["deriv_origen"]].conexiones.append(ConexionSalida(
            destino=nombre, proporcion=float(borrador.get("deriv_prop", 1.0)),
            tope=INFINITO if tope <= 0 else tope * factor_mm,
            comparte_pool=False))
        registro[borrador["deriv_origen"]].deriva = True
    elif fuente == "ducto" and Intervencion is not None:
        obtener_intervenciones().append(Intervencion(
            "alta", f"Ducto a {nombre}",
            area_origen=borrador["area"], planta_destino=nombre_pool,
            volumen=float(borrador["vol_ducto"]) * factor_mm))

    return _resumen_planta(borrador, None, factor_mm)


def _resumen_planta(b, nombres, factor_mm) -> str:
    fuente = {
        "ducto": (f"pool propio con ducto nuevo desde "
                  f"{(nombres or {}).get(str(b.get('area')), b.get('area'))} "
                  f"por {b.get('vol_ducto', 0):,.2f} MMm3/d"),
        "tren": f"tren sobre el gas de {b.get('companera')}",
        "derivacion": (f"recibe el {b.get('deriv_prop', 1) * 100:.0f}% del "
                       f"sobrante de {b.get('deriv_origen')}"),
        "croma": "sólo su corriente propia",
    }.get(b.get("fuente"), "—")

    lineas = [
        f"- Planta **{b.get('nombre')}** (preset {b.get('preset')})",
        f"- Fuente de gas: {fuente}",
        f"- Evacuación: {b.get('evac', 0):,.0f} tn/d"
        + (" (sin límite)" if not b.get("evac") else ""),
        f"- Retención: " + (f"copiada de {b['ret_de']}" if b.get("ret_de")
                            else "todo en 0 por ahora"),
        "- Sobrante: " + (f"deriva {b.get('out_prop', 1) * 100:.0f}% a "
                          f"{b['out_destino']}" if b.get("out_destino")
                          else "terminal (bypass)"),
    ]
    if b.get("croma"):
        lineas.append(f"- Corriente propia con cromatografía por "
                      f"{b['croma']['vol_derivacion'] / factor_mm:,.2f} MMm3/d")
    return "\n".join(lineas)


# ===========================================================================
# Helpers
# ===========================================================================

def _describir_preset(preset: str) -> str:
    f = PRESETS[preset]
    return " · ".join([
        "deriva el sobrante" if f["deriva"] else "terminal",
        "cabecera de su pool" if f["toma_volumen_del_pool"]
        else "recibe el volumen del tren anterior",
    ])


def _areas_disponibles(comunes) -> list:
    yac = comunes.get("tabla_total_yacimientos")
    if yac is None or "Area" not in getattr(yac, "columns", []):
        return []
    return sorted(pd.Series(yac["Area"]).dropna().astype(str).unique())


def _destinos_disponibles(registro, comunes) -> list:
    destinos = {p.nombre_pool for p in registro.values() if p.nombre_pool}
    for clave in ("tabla_total_yacimientos", "tabla_total_flujos_directos"):
        tabla = comunes.get(clave)
        if tabla is not None and "Gasoducto" in getattr(tabla, "columns", []):
            destinos |= set(pd.Series(tabla["Gasoducto"]).dropna().astype(str))
    return sorted(d for d in destinos if d and d != "0")


def _editor_croma(compuestos):
    """Tabla para pegar la composición molar + volumen. Devuelve (df, vol)."""
    st.caption("Fracciones molares (suman ~1) o porcentajes (suman ~100): "
               "se renormalizan solas. Volumen en MMm3/d.")
    semilla = pd.DataFrame({"Compuesto": list(compuestos),
                            "Fracción": [0.0] * len(compuestos)})
    df = st.data_editor(
        semilla, hide_index=True, key="bot_croma_editor", **ancho(),
        column_config={
            "Compuesto": st.column_config.TextColumn(disabled=True),
            "Fracción": st.column_config.NumberColumn(min_value=0.0, step=0.001,
                                                      format="%.4f"),
        })
    vol = st.number_input("Volumen de la corriente [MMm3/d]", min_value=0.0,
                          step=0.5, key="bot_croma_vol")
    return df, vol


def _leer_croma(df, vol_mm, compuestos, factor_mm) -> dict | None:
    """Convierte el editor a una entrada de `cromas_extra`, o None si vacío.

    Mismo formato que `io_.cromatografias_planta`: se inyecta al pool como una
    derivación más, en unidades de Volumen_inyectado.
    """
    if df is None or not vol_mm or vol_mm <= 0:
        return None
    valores = pd.to_numeric(df.set_index("Compuesto")["Fracción"],
                            errors="coerce").fillna(0.0)
    total = float(valores.sum())
    if total <= 0:
        return None
    croma = (valores / total).reindex(list(compuestos)).fillna(0.0)
    return {
        "vol_derivacion": float(vol_mm) * float(factor_mm),
        "origen": "asistente",
        "cromato_derivacion": croma.astype("float64"),
    }


_PASOS = {
    "intent": _paso_intent,
    "p_nombre": _paso_p_nombre,
    "p_fuente": _paso_p_fuente,
    "p_capacidades": _paso_p_capacidades,
    "p_salida": _paso_p_salida,
    "p_resumen": _paso_p_resumen,
    "c_planta": _paso_c_planta,
    "s_planta": _paso_s_planta,
    "d_datos": _paso_d_datos,
}
