"""
Canvas drag & connect del sandbox de plantas.
=============================================

Un editor visual (React Flow via `streamlit-flow-component`) que dibuja el
registro de plantas como nodos y las conexiones como aristas, y permite:

  - Mover los nodos (las posiciones se recuerdan en session_state).
  - Crear una conexión ARRASTRANDO desde el borde de una planta a otra.
  - Borrar una conexión desde el menú contextual de la arista.
  - Borrar una planta desde el menú contextual del nodo (las base se reponen).
  - Seleccionar la planta a editar CLICKEÁNDOLA (reemplaza al selectbox).

QUIÉN ES LA FUENTE DE VERDAD
----------------------------
El registro, siempre. El canvas es OTRA capa de edición sobre el mismo
`registro_plantas` que ya edita `plantas_editor`: después de cada interacción,
las aristas del canvas se vuelcan a `PlantaConfig.conexiones` /
`toma_volumen_del_pool` y todo lo demás (validar_registro, resolver_cascada,
el control contra producción) sigue corriendo igual que hoy. Los NÚMEROS de
una conexión (proporción, tope, mismo pool) se siguen afinando en la tabla
del editor: el canvas define la TOPOLOGÍA, la tabla define las cantidades.

Una conexión creada en el canvas nace con defaults honestos: 100% del
sobrante, sin tope, y `comparte_pool` inferido de si origen y destino tienen
el mismo `nombre_pool` (la relación TBX / Dew Point).

MAPEO DE NODOS Y ARISTAS
------------------------
  p::<nombre>      planta               (color de la planta; punteado = inactiva)
  pool::<pool>     pool de gas          (naranja claro, como en el graphviz)
  bypass           sumidero             (rosa, como en el graphviz)

  cx::A=>B         ConexionSalida A->B          <- EDITABLE (crear / borrar)
  in::pool=>P      "P toma volumen de su pool"  <- EDITABLE (borrar = toma=False)
  bp::P            "P manda sobrante a bypass"  <- informativa, no se vuelca

CUÁNDO SE RECONSTRUYE
---------------------
El estado del canvas vive en session_state para no pisarle las posiciones al
usuario en cada rerun. Sólo se reconstruye desde el registro cuando una FIRMA
del registro (nombres, pools, conexiones, flags) cambia por fuera del canvas:
alta/baja de plantas, cargar un escenario, tocar la tabla de conexiones, o el
reset del sandbox (que borra todas las claves `canvas_`).

IMPORT SIEMPRE SEGURO
---------------------
Igual que `ui.gasoductos_editor`: importar ESTE módulo nunca falla. Si
`streamlit-flow-component` no está instalado, `panel_canvas` explica qué falta
y el editor sigue funcionando con el selectbox de siempre.
"""

from __future__ import annotations

import streamlit as st

from pipeline.plantas.registro import ConexionSalida, INFINITO

# ---------------------------------------------------------------------------
# Import defensivo del componente.
# ---------------------------------------------------------------------------
try:
    from streamlit_flow import streamlit_flow
    from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
    from streamlit_flow.state import StreamlitFlowState

    DISPONIBLE = True
    MOTIVO = ""
except Exception as _e:  # noqa: BLE001 - cualquier fallo degrada, no tumba
    DISPONIBLE = False
    MOTIVO = f"{type(_e).__name__}: {_e}"


# Todas las claves arrancan con "canvas_" para que el reset del sandbox
# (PREFIJOS_WIDGETS en ui/sandbox_estado.py) las barra junto con lo demás.
CLAVE_ESTADO = "canvas_estado"        # StreamlitFlowState vivo
CLAVE_FIRMA = "canvas_firma"          # firma del registro con la que se armó
CLAVE_POSICIONES = "canvas_posiciones"  # {node_id: (x, y)} sobrevive rebuilds
CLAVE_SEL_PREVIA = "canvas_sel_previa"  # para avisar sólo cuando CAMBIA el click
CLAVE_WIDGET = "canvas_flow"

_ALTO = 480

_ESTILO_POOL = {"background": "#FDEBD0", "border": "1px solid #E59866",
                "borderRadius": "8px", "fontSize": "12px"}
_ESTILO_BYPASS = {"background": "#FADBD8", "border": "1px solid #EC7063",
                  "borderRadius": "16px", "fontSize": "12px"}


# ===========================================================================
# API pública
# ===========================================================================

def panel_canvas(registro: dict, factor_mm: float = 1000.0,
                 compuestos=None) -> tuple[str | None, list[str], bool]:
    """Dibuja el canvas y vuelca las interacciones sobre `registro` IN PLACE.

    Devuelve `(seleccion, avisos, cambio_topologia)`:
      - `seleccion`: nombre de la planta clickeada, SÓLO cuando el click es
        nuevo (para no pisarle el selectbox al usuario en cada rerun), o None.
      - `avisos`: mensajes para mostrar (conexiones creadas con defaults,
        plantas base repuestas, aristas ignoradas...).
      - `cambio_topologia`: True si este rerun el canvas MODIFICÓ el registro
        (conexiones, cabeceras, bajas). El editor tiene que limpiar los deltas
        de los widgets que editan lo mismo (tabla `con_*`, checkbox `cab_*`):
        si sobreviven, en este mismo rerun le escriben encima al registro lo
        que el canvas acaba de cambiar, y el usuario ve la arista "volverse".
    """
    if not DISPONIBLE:
        st.info(
            "El editor visual necesita `streamlit-flow-component` **1.5.0 o "
            "posterior** (en requirements.txt: "
            "`streamlit-flow-component==1.6.1`). Las versiones anteriores no "
            "tienen `StreamlitFlowState`, que es lo que sincroniza el canvas "
            f"con el registro. Detalle: {MOTIVO}\n\n"
            "Mientras tanto el editor de abajo funciona igual.")
        return None, [], False

    if not registro:
        return None, [], False

    avisos: list[str] = []

    estado = _estado_sincronizado(registro, factor_mm)
    firma_antes = st.session_state.get(CLAVE_FIRMA)

    with st.container():
        st.caption(
            "**Arrastrá** para mover · **conectá** arrastrando del borde de un "
            "nodo a otro · **click derecho** sobre nodo/arista para borrar · "
            "**click** en una planta para editarla abajo. Las líneas al bypass "
            "son informativas. Proporciones y topes se afinan en la tabla de "
            "conexiones.")

        try:
            estado_nuevo = streamlit_flow(
                CLAVE_WIDGET,
                estado,
                height=_ALTO,
                fit_view=True,
                allow_new_edges=True,
                animate_new_edges=True,
                get_node_on_click=True,
                get_edge_on_click=True,
                enable_node_menu=True,
                enable_edge_menu=True,
                enable_pane_menu=False,  # el alta de plantas sigue por el expander
                min_zoom=0.2,
                hide_watermark=True,
            )
        except TypeError:
            # Otra versión del componente sin alguno de estos kwargs: se
            # degrada a lo esencial en vez de tumbar el editor entero.
            estado_nuevo = streamlit_flow(
                CLAVE_WIDGET, estado, height=_ALTO, fit_view=True,
                allow_new_edges=True)

    st.session_state[CLAVE_ESTADO] = estado_nuevo
    _guardar_posiciones(estado_nuevo)

    avisos += _volcar_al_registro(estado_nuevo, registro)

    # La firma se recalcula DESPUÉS de volcar: así el propio volcado no
    # dispara una reconstrucción (que pisaría las posiciones a mitad de drag).
    firma_despues = _firma(registro)
    st.session_state[CLAVE_FIRMA] = firma_despues

    cambio_topologia = firma_antes is not None and firma_antes != firma_despues

    return _seleccion_nueva(estado_nuevo, registro), avisos, cambio_topologia


def obtener_posiciones() -> dict[str, tuple[float, float]]:
    """Las posiciones actuales de los nodos, para guardarlas en un escenario."""
    return dict(st.session_state.get(CLAVE_POSICIONES) or {})


def cargar_posiciones(posiciones: dict):
    """Mezcla posiciones (de un escenario) sobre las actuales y fuerza el
    redibujado. Merge y no reemplazo, por la misma razón que las plantas:
    un escenario chico no tiene por qué desacomodar los nodos que no trae."""
    if not posiciones:
        return
    actuales = dict(st.session_state.get(CLAVE_POSICIONES) or {})
    actuales.update(posiciones)
    st.session_state[CLAVE_POSICIONES] = actuales
    invalidar_canvas()


def invalidar_canvas():
    """Fuerza la reconstrucción del canvas en el próximo rerun.

    Llamalo si un flujo externo modifica el registro sin pasar por acá y
    querés el redibujado inmediato (cargar escenario, etc.). No es obligatorio:
    la firma lo detecta sola en el próximo rerun de todas formas.
    """
    st.session_state.pop(CLAVE_FIRMA, None)
    st.session_state.pop(CLAVE_ESTADO, None)


# ===========================================================================
# Registro -> canvas
# ===========================================================================

def _firma(registro) -> tuple:
    """Todo lo del registro que el canvas DIBUJA. Si esto no cambia, el canvas
    no se reconstruye y las posiciones del usuario quedan intactas."""
    partes = []
    for nombre in sorted(registro):
        p = registro[nombre]
        partes.append((
            nombre, p.nombre_pool, bool(p.activa), bool(p.deriva),
            bool(p.toma_volumen_del_pool), p.color,
            tuple(sorted(
                (c.destino,
                 round(float(c.proporcion), 9),
                 None if c.tope == INFINITO else round(float(c.tope), 6),
                 bool(c.comparte_pool))
                for c in p.conexiones)),
        ))
    return tuple(partes)


def _estado_sincronizado(registro, factor_mm) -> "StreamlitFlowState":
    """Devuelve el estado vivo, o lo reconstruye si el registro cambió por
    fuera del canvas (alta/baja, escenario, tabla de conexiones, reset)."""
    estado = st.session_state.get(CLAVE_ESTADO)
    firma = _firma(registro)

    if estado is not None and st.session_state.get(CLAVE_FIRMA) == firma:
        return estado

    estado = _construir_estado(registro, factor_mm)
    st.session_state[CLAVE_ESTADO] = estado
    st.session_state[CLAVE_FIRMA] = firma
    return estado


def _construir_estado(registro, factor_mm) -> "StreamlitFlowState":
    posiciones = st.session_state.get(CLAVE_POSICIONES) or {}
    nodes, edges = [], []

    pools = sorted({p.nombre_pool for p in registro.values() if p.nombre_pool})

    # Posiciones por defecto en tres columnas (pools | plantas | bypass).
    # Groseras a propósito: son sólo el punto de partida antes del primer drag.
    def _pos_defecto(prefijo, i):
        x = {"pool": 0, "p": 320, "bypass": 680}[prefijo]
        return (x, 60 + i * 130)

    for i, pool in enumerate(pools):
        nid = f"pool::{pool}"
        nodes.append(StreamlitFlowNode(
            id=nid,
            pos=posiciones.get(nid, _pos_defecto("pool", i)),
            data={"content": f"Pool **{pool}**"},
            node_type="input",
            source_position="right",
            connectable=True,
            style=dict(_ESTILO_POOL),
        ))

    for i, (nombre, p) in enumerate(sorted(registro.items())):
        nid = f"p::{nombre}"
        estilo = {
            "background": p.color or "#EAF2F8",
            "border": ("2px dashed #7f8c8d" if not p.activa
                       else "1px solid #34495e"),
            "borderRadius": "8px",
            "fontSize": "13px",
        }
        sub = p.nombre_pool if p.nombre_pool != nombre else ""
        contenido = f"**{nombre}**" + (f"<br><small>pool: {sub}</small>" if sub else "")
        if not p.activa:
            contenido += "<br><small>fuera de servicio</small>"
        nodes.append(StreamlitFlowNode(
            id=nid,
            pos=posiciones.get(nid, _pos_defecto("p", i)),
            data={"content": contenido},
            node_type="default",
            source_position="right",
            target_position="left",
            connectable=True,
            style=estilo,
        ))

    nodes.append(StreamlitFlowNode(
        id="bypass",
        pos=posiciones.get("bypass", _pos_defecto("bypass", len(registro) // 2)),
        data={"content": "ByPass"},
        node_type="output",
        target_position="left",
        connectable=False,
        style=dict(_ESTILO_BYPASS),
    ))

    # --- Aristas ---------------------------------------------------------
    for nombre, p in registro.items():
        # pool -> planta: "toma volumen de su pool" (editable: borrarla apaga
        # el flag; el volcado la interpreta).
        if p.toma_volumen_del_pool and p.nombre_pool:
            edges.append(StreamlitFlowEdge(
                id=f"in::{p.nombre_pool}=>{nombre}",
                source=f"pool::{p.nombre_pool}",
                target=f"p::{nombre}",
                label="toma del pool",
                edge_type="smoothstep",
                marker_end={"type": "arrow"},
                style={"strokeDasharray": "6 4", "stroke": "#E59866"},
            ))

        # planta -> planta: las conexiones de verdad.
        for c in p.conexiones:
            edges.append(StreamlitFlowEdge(
                id=f"cx::{nombre}=>{c.destino}",
                source=f"p::{nombre}",
                target=f"p::{c.destino}",
                label=_etiqueta_conexion(c, factor_mm),
                animated=not c.comparte_pool,
                edge_type="smoothstep",
                marker_end={"type": "arrowclosed"},
            ))

        # planta -> bypass: informativa, sólo donde el bypass es estructural.
        deriva_todo = p.deriva and abs(
            sum(max(c.proporcion, 0.0) for c in p.conexiones) - 1.0) < 1e-9
        if p.activa and not deriva_todo:
            edges.append(StreamlitFlowEdge(
                id=f"bp::{nombre}",
                source=f"p::{nombre}",
                target="bypass",
                label="bypass",
                edge_type="smoothstep",
                marker_end={"type": "arrow"},
                style={"strokeDasharray": "3 5", "stroke": "#EC7063"},
            ))

    return StreamlitFlowState(nodes, edges)


def _etiqueta_conexion(c: ConexionSalida, factor_mm) -> str:
    partes = [f"{c.proporcion:.0%}"]
    if c.tope != INFINITO:
        partes.append(f"≤{c.tope / factor_mm:,.2f}")
    if c.comparte_pool:
        partes.append("mismo pool")
    return " · ".join(partes)


# ===========================================================================
# Canvas -> registro
# ===========================================================================

def _volcar_al_registro(estado, registro) -> list[str]:
    """Interpreta nodos y aristas del canvas sobre el registro, IN PLACE.

    El canvas manda en la TOPOLOGÍA (qué conexiones existen, quién toma de su
    pool, qué plantas siguen vivas); los parámetros finos de cada conexión que
    ya existía se conservan tal cual.
    """
    avisos: list[str] = []
    forzar_rebuild = False

    nodos_planta = {_nombre_planta(n.id) for n in estado.nodes
                    if str(n.id).startswith("p::")}
    nodos_pool = {str(n.id).split("::", 1)[1] for n in estado.nodes
                  if str(n.id).startswith("pool::")}
    hay_bypass = any(str(n.id) == "bypass" for n in estado.nodes)

    # --- Bajas de nodos --------------------------------------------------
    for nombre in [n for n in list(registro) if n not in nodos_planta]:
        if registro[nombre].es_base:
            avisos.append(
                f"'{nombre}' es una planta base: no se puede borrar desde el "
                "canvas, se repone.")
            forzar_rebuild = True
        else:
            del registro[nombre]
            for p in registro.values():
                p.conexiones = [c for c in p.conexiones if c.destino != nombre]
            avisos.append(f"Planta '{nombre}' eliminada desde el canvas.")

    pools_esperados = {p.nombre_pool for p in registro.values() if p.nombre_pool}
    if not pools_esperados <= nodos_pool or not hay_bypass:
        # Borraron un nodo estructural (pool o bypass). No hay interpretación
        # honesta para eso: se repone y NO se toca `toma_volumen_del_pool`
        # este rerun, porque sus aristas se fueron junto con el nodo.
        avisos.append("Los nodos de pool y bypass no se pueden borrar: se reponen.")
        invalidar_canvas()
        _volcar_solo_conexiones(estado, registro, avisos)
        return avisos

    _volcar_solo_conexiones(estado, registro, avisos)

    # --- pool -> planta ==> toma_volumen_del_pool ------------------------
    con_entrada_de_pool = set()
    for e in estado.edges:
        src, dst = str(e.source), str(e.target)
        if not (src.startswith("pool::") and dst.startswith("p::")):
            continue
        pool, planta = src.split("::", 1)[1], _nombre_planta(dst)
        if planta not in registro:
            continue
        if registro[planta].nombre_pool != pool:
            avisos.append(
                f"La línea del pool '{pool}' a '{planta}' se ignora: esa "
                f"planta filtra por el pool '{registro[planta].nombre_pool}'. "
                "El pool de una planta se cambia en su panel, no conectándola.")
            forzar_rebuild = True
            continue
        con_entrada_de_pool.add(planta)

    for nombre, p in registro.items():
        toma = nombre in con_entrada_de_pool
        if toma != bool(p.toma_volumen_del_pool):
            p.toma_volumen_del_pool = toma
            avisos.append(
                f"'{nombre}' ahora {'toma' if toma else 'NO toma'} volumen de "
                "su pool" + ("" if toma else
                             " (el volumen se lo tiene que pasar otra planta)")
                + ".")

    if forzar_rebuild:
        invalidar_canvas()

    return avisos


def _volcar_solo_conexiones(estado, registro, avisos):
    """Las aristas cx:: (y las planta->planta nuevas) sobre `conexiones`."""
    por_origen: dict[str, list[str]] = {}
    for e in estado.edges:
        src, dst = str(e.source), str(e.target)
        if not (src.startswith("p::") and dst.startswith("p::")):
            continue
        origen, destino = _nombre_planta(src), _nombre_planta(dst)
        if origen not in registro or destino not in registro:
            continue
        if origen == destino:
            avisos.append(f"'{origen}' no se puede conectar a sí misma: se ignora.")
            continue
        por_origen.setdefault(origen, [])
        if destino not in por_origen[origen]:  # sin duplicados
            por_origen[origen].append(destino)

    for nombre, p in registro.items():
        existentes = {c.destino: c for c in p.conexiones}
        destinos = por_origen.get(nombre, [])

        # conservar el orden original de las que ya estaban
        orden_previo = [c.destino for c in p.conexiones if c.destino in destinos]
        nuevas_al_final = [d for d in destinos if d not in existentes]

        conexiones = [existentes[d] for d in orden_previo]
        for d in nuevas_al_final:
            mismo = registro[d].nombre_pool == p.nombre_pool
            conexiones.append(ConexionSalida(
                destino=d, proporcion=1.0, tope=INFINITO, comparte_pool=mismo))
            avisos.append(
                f"Conexión nueva **{nombre} → {d}** creada con defaults "
                f"(100% del sobrante, sin tope, "
                f"{'mismo pool' if mismo else 'derivación real'}). "
                "Afinala en la tabla de conexiones.")

        borradas = [d for d in existentes if d not in destinos]
        for d in borradas:
            avisos.append(f"Conexión **{nombre} → {d}** eliminada desde el canvas.")

        if borradas or nuevas_al_final or orden_previo != list(existentes):
            p.conexiones = conexiones


# ===========================================================================
# Selección y posiciones
# ===========================================================================

def _seleccion_nueva(estado, registro) -> str | None:
    """Nombre de la planta clickeada, sólo si el click es NUEVO."""
    sel = getattr(estado, "selected_id", None)
    if not sel or not str(sel).startswith("p::"):
        return None
    nombre = _nombre_planta(str(sel))
    if nombre not in registro:
        return None
    if st.session_state.get(CLAVE_SEL_PREVIA) == sel:
        return None
    st.session_state[CLAVE_SEL_PREVIA] = sel
    return nombre


def _guardar_posiciones(estado):
    posiciones = dict(st.session_state.get(CLAVE_POSICIONES) or {})
    for n in estado.nodes:
        pos = _pos(n)
        if pos is not None:
            posiciones[str(n.id)] = pos
    st.session_state[CLAVE_POSICIONES] = posiciones


def _pos(node):
    """Posición de un nodo, tolerante a las dos formas del componente."""
    p = getattr(node, "position", None)
    if p is None:
        p = getattr(node, "pos", None)
    if isinstance(p, dict):
        try:
            return float(p.get("x", 0.0)), float(p.get("y", 0.0))
        except (TypeError, ValueError):
            return None
    if isinstance(p, (tuple, list)) and len(p) == 2:
        try:
            return float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None
    return None


def _nombre_planta(node_id: str) -> str:
    return str(node_id).split("::", 1)[1]
