"""
Fixtures sintéticas para los tests de física.
=============================================

Todo lo de acá es inventado a propósito: números redondos, composición
uniforme, dos pools. La idea es que los invariantes físicos se puedan verificar
SIN el Excel real — si un test de esta carpeta necesita `datos/inputs.xlsx`,
está mal ubicado (va con marca `integracion`).

El patrón de `comunes` copia el de los smoke tests de `ui/`: tablas mínimas con
`Area`, `HUB`, `Gasoducto`, `Volumen_inyectado` y una columna por compuesto con
la fracción molar.
"""

import pandas as pd
import pytest

try:
    from domain.ctes_gas import COMPUESTOS as _COMPUESTOS
    COMPUESTOS = list(_COMPUESTOS)
except Exception:  # pragma: no cover - por si el módulo cambia de lugar
    COMPUESTOS = ["C1", "C2", "C3", "iC4", "nC4", "iC5", "nC5",
                  "nC6", "nC7", "nC8", "nC9", "nC10", "N2", "CO2"]

TOL = 1e-9          # los invariantes de balance son identidades, no aproximaciones
TOL_BALANCE = 1e-6  # el umbral que la app pinta en verde


@pytest.fixture(scope="session")
def compuestos():
    return COMPUESTOS


@pytest.fixture(scope="session")
def croma_uniforme(compuestos):
    """Fracciones molares uniformes que suman 1. Sin física real, pero válida."""
    n = len(compuestos)
    return {c: 1.0 / n for c in compuestos}


@pytest.fixture
def params_base():
    """Los mismos parámetros que usa el smoke test de ui/test_tab_plantas."""
    return dict(
        CAPACIDAD_EVACUACION_TTY_TBX=0.9,
        CAPACIDAD_EVACUACION_TTY_DP=0.4,
        CAPACIDAD_EVACUACION_MEGA=0.5,
        CAPACIDAD_TTY_TBX=34000,
        CAPACIDAD_TTY_DP=28000,
        CAPACIDAD_MEGA=43000,
        MAX_DERIVACION_TTY_DP_A_MEGA=5000,
        MAX_DERIVACION_TTY_TBX_A_TTY_DP=14800,
    )


@pytest.fixture
def retenidos_rtp(compuestos):
    """Una fila por planta base, retención plana por compuesto."""
    return pd.DataFrame([
        {"Planta": p, **{c: v for c in compuestos}}
        for p, v in [("TBX", 0.5), ("Dew point", 0.3), ("TBX MEGA", 0.7)]
    ])


@pytest.fixture
def comunes(compuestos, croma_uniforme):
    """Dos pools: TTY (600 vía yacimiento + 600 directo) y MEGA (400)."""
    yac = pd.DataFrame([
        {"Area": "Chivo", "HUB": "H1", "Gasoducto": "VMN",
         "Volumen_inyectado": 600.0, **croma_uniforme},
        {"Area": "Chivo", "HUB": "H1", "Gasoducto": "MEGA",
         "Volumen_inyectado": 400.0, **croma_uniforme},
    ])
    fdi = pd.DataFrame([
        {"Area": "VMN", "HUB": "-", "Gasoducto": "TTY",
         "Volumen_inyectado": 600.0, **croma_uniforme},
    ])
    return dict(
        matriz_inyecciones=None,
        calcular_retenidos=None,
        propiedades=None,
        COMPUESTOS=compuestos,
        tabla_total_yacimientos=yac,
        tabla_total_flujos_directos=fdi,
    )


@pytest.fixture
def registro_tres(params_base, retenidos_rtp, compuestos):
    """Las tres plantas de siempre, TBX en servicio."""
    from pipeline.plantas.registro import registro_base
    return registro_base(params_base, retenidos_rtp, compuestos, True)


@pytest.fixture
def cascada_resuelta(registro_tres, comunes):
    from pipeline.plantas.cascada import resolver_cascada
    return resolver_cascada(registro_tres, comunes)


def planta_dict(nombre, *, pool, cap_evac, compuestos, retencion=0.3,
                conexiones=(), deriva=True, cabecera=True, activa=True,
                cap_ingreso=None):
    """Arma un dict apto para `PlantaConfig.desde_dict`.

    Se usa el formato de los escenarios JSON — la interfaz pública más estable
    del registro — en vez del constructor, para que un cambio de firma interna
    no rompa toda la suite.
    """
    return {
        "nombre": nombre,
        "nombre_pool": pool,
        "capacidad_evacuacion": float(cap_evac),
        "capacidad_ingreso": cap_ingreso,
        "retenidos": {c: retencion for c in compuestos},
        "conexiones": list(conexiones),
        "deriva": deriva,
        "toma_volumen_del_pool": cabecera,
        "activa": activa,
        "color": "#CCCCCC",
        "es_base": False,
        "cromas_extra": [],
    }


def conexion(destino, proporcion, tope=None, comparte_pool=True):
    return {"destino": destino, "proporcion": proporcion,
            "tope": tope, "comparte_pool": comparte_pool}
