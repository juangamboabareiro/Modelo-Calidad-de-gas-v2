"""
El registro del escenario, mes a mes.
=====================================

La serie oficial corre el pipeline una vez por mes y las AMPLIACIONES de los
modulos se prenden solas en el mes que les corresponde. El registro del
sandbox, en cambio, se sembro con los parametros de UN periodo: si la serie
del escenario lo usara congelado, un registro SIN TOCAR daria distinto a la
serie oficial en los meses donde las ampliaciones difieren — y el control
(sandbox intacto == oficial) es la unica forma de creerle a esta capa.

La solucion es separar lo que el usuario TOCO de lo que heredo de la siembra:

  1. `diff_contra_semilla` compara el registro del usuario contra la semilla
     de referencia (las tres base con los parametros del periodo actual, la
     MISMA con la que `inicializar` lo sembro) y devuelve, por planta base,
     SOLO los campos que difieren. Lo que el usuario no toco no aparece.

  2. `registro_para_periodo` arma el registro de un mes: siembra las base con
     los parametros DE ESE MES (ampliaciones incluidas), les aplica encima el
     diff del usuario, y suma las plantas agregadas (clonadas, para que un mes
     no le escriba flujos al siguiente).

Asi, capacidad no tocada = sigue las ampliaciones del mes, como la serie
oficial. Capacidad tocada = queda fija en lo que el usuario puso, porque eso
es lo que pidio. Lo mismo vale para las reglas de la correccion por llenar
evacuacion: sin tocar siguen las de la sidebar, tocadas quedan como estan. `activa` de TTY-TBX es la excepcion: la manda la fecha de PM
de cada mes, igual que en `inicializar`, que la fuerza en cada rerun.
"""

from __future__ import annotations

import pandas as pd

from pipeline.plantas.correccion import copiar_reglas
from pipeline.plantas.registro import PlantaConfig, ConexionSalida, registro_base


# Campos de una planta base que el diff compara y, si difieren, pisa por mes.
# `activa` NO esta para TTY-TBX (la manda la fecha de PM del mes); para las
# demas base si se compara, por si algun dia una se puede apagar a mano.
_CAMPOS_ESCALARES = (
    "capacidad_evacuacion", "capacidad_ingreso", "deriva",
    "toma_volumen_del_pool", "nombre_pool", "color",
)

# La planta cuya `activa` sigue a la fecha de PM y no al usuario.
_SIGUE_FECHA_PM = "TTY - TBX"


def diff_contra_semilla(registro: dict, semilla_ref: dict) -> tuple[dict, list]:
    """(overrides_por_base, extras_serializadas).

    `overrides_por_base` es {nombre: {campo: valor}} SOLO con lo que el usuario
    cambio respecto de la semilla de referencia. `extras_serializadas` son las
    plantas no-base, como dicts (`a_dict`) listos para clonar por mes.
    """
    overrides: dict[str, dict] = {}

    for nombre, semilla in semilla_ref.items():
        planta = registro.get(nombre)
        if planta is None:
            # Base ausente del registro del usuario: no deberia pasar (las
            # base no se pueden borrar), pero si pasa no hay nada que heredar.
            continue

        cambios: dict = {}

        for campo in _CAMPOS_ESCALARES:
            if getattr(planta, campo) != getattr(semilla, campo):
                cambios[campo] = getattr(planta, campo)

        if nombre != _SIGUE_FECHA_PM and bool(planta.activa) != bool(semilla.activa):
            cambios["activa"] = bool(planta.activa)

        if not _retenidos_iguales(planta.retenidos, semilla.retenidos):
            cambios["retenidos"] = (
                None if planta.retenidos is None else planta.retenidos.copy())

        if _conexiones_a_lista(planta) != _conexiones_a_lista(semilla):
            cambios["conexiones"] = [c.a_dict() for c in planta.conexiones]

        # Correccion por llenar evacuacion (el bloque 1b, que el sandbox ahora
        # edita por planta). `copiar_reglas` normaliza los dos lados, asi que
        # None y unas reglas apagadas comparan IGUAL: una base que el usuario
        # no toco no genera override y el control "sandbox intacto == oficial"
        # se mantiene.
        if not _correcciones_iguales(planta, semilla):
            cambios["correccion"] = (
                copiar_reglas(planta.correccion) if planta.correccion else None)

        # Las cromatografias extra no son un parametro de la siembra: son datos
        # que el usuario cargo. Si hay, van siempre.
        if planta.cromas_extra:
            cambios["cromas_extra"] = planta.cromas_extra

        if cambios:
            overrides[nombre] = cambios

    extras = [p.a_dict() for p in registro.values() if not p.es_base]

    return overrides, extras


def registro_para_periodo(params_del_mes, retenidos_rtp, compuestos,
                          tbx_en_servicio: bool, overrides: dict,
                          extras: list) -> dict[str, PlantaConfig]:
    """El registro con el que se resuelve la cascada de UN mes de la serie."""
    registro = registro_base(params_del_mes, retenidos_rtp, compuestos,
                             tbx_en_servicio)

    for nombre, cambios in overrides.items():
        planta = registro.get(nombre)
        if planta is None:
            continue
        for campo, valor in cambios.items():
            if campo == "retenidos":
                planta.retenidos = None if valor is None else valor.copy()
            elif campo == "conexiones":
                planta.conexiones = [ConexionSalida.desde_dict(c) for c in valor]
            elif campo == "cromas_extra":
                planta.cromas_extra = valor
            elif campo == "correccion":
                # Copia por mes: 24 meses compartiendo el mismo dict de reglas
                # es la misma invitacion al bug que un registro compartido.
                planta.correccion = copiar_reglas(valor) if valor else None
            else:
                setattr(planta, campo, valor)

    # Las agregadas se CLONAN por mes: `resolver_cascada` no muta la config,
    # pero un registro compartido entre 24 meses es una invitacion a que algun
    # dia si lo haga y el bug sea imposible de ver.
    for datos in extras:
        clon = PlantaConfig.desde_dict(datos)
        registro[clon.nombre] = clon

    return registro


# ---------------------------------------------------------------------------

def _retenidos_iguales(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        va = pd.to_numeric(a.iloc[0], errors="coerce").fillna(0.0)
        vb = pd.to_numeric(b.iloc[0], errors="coerce").fillna(0.0)
        columnas = sorted(set(va.index) | set(vb.index))
        va = va.reindex(columnas).fillna(0.0)
        vb = vb.reindex(columnas).fillna(0.0)
        return bool((va - vb).abs().max() < 1e-12)
    except Exception:  # noqa: BLE001 - ante la duda, se considera tocado
        return False


def _conexiones_a_lista(planta: PlantaConfig) -> list:
    return [c.a_dict() for c in planta.conexiones]


def _correcciones_iguales(a, b) -> bool:
    """`getattr` y no acceso directo: escenarios y tests viejos arman
    PlantaConfig sin el campo `correccion`."""
    return (copiar_reglas(getattr(a, "correccion", None))
            == copiar_reglas(getattr(b, "correccion", None)))
