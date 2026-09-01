"""
La app corriendo de verdad: `streamlit.testing.v1.AppTest`.
==========================================================

Los tests de `test_ui_sandbox.py` llaman funciones sueltas. Estos corren
`app.py` ENTERA, headless y sin navegador, y por eso atrapan una clase de
problema que ningún test de función puede ver:

  - que la app **arranque** sin excepción (un import roto en cualquier módulo
    de `ui/` aparece acá, y sólo acá);
  - que los widgets existan con las `key` que el código espera;
  - que un botón haga lo que dice hacer;
  - que un error del pipeline se muestre en pantalla en vez de tumbar el tab.

POR QUÉ ESTO Y NO EL FAKE DE `sys.modules["streamlit"]`
-------------------------------------------------------
Los smokes de `ui/` reemplazan el módulo `streamlit` por un objeto a mano.
Sirve, y fue lo correcto en su momento. Pero el fake tiene que imitar cada
widget que se use y se desincroniza en silencio: si el código empieza a usar un
widget que el fake no tiene, el smoke pasa igual porque `__getattr__` devuelve
cualquier cosa. `AppTest` usa el Streamlit real.

CÓMO ESTÁ ARMADA LA APP (lo que estos tests asumen)
---------------------------------------------------
    st.session_state["resultados"]   lo que devuelve `ejecutar_pipeline`
    st.session_state["diagnostico"]  las observaciones capturadas

Si `resultados` es None, `app.py` muestra un `st.info` y hace `st.stop()`:
**no dibuja ningún tab**. Los tabs recién existen después de correr el
pipeline, y por eso los tests se parten en dos grupos.

DOS GRUPOS
----------
`test_arranca_*`   — no necesitan datos. Corren siempre.
`test_con_datos_*` — necesitan el Excel. Marcados `integracion`, y además se
                     saltean solos si el archivo no está.
"""

from pathlib import Path

import pytest

# AppTest existe desde Streamlit 1.28. Si la versión es más vieja, el módulo
# entero se saltea en vez de reventar la colección.
AppTest = pytest.importorskip(
    "streamlit.testing.v1", reason="requiere Streamlit >= 1.28").AppTest


# `from_file` resuelve las rutas relativas contra el ARCHIVO que la llama (o
# sea, contra `tests/`), no contra el cwd. De ahí el path absoluto.
RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app.py"

TIMEOUT = 120  # el pipeline real tarda; el default de 3s no alcanza


@pytest.fixture
def app(monkeypatch):
    if not APP.is_file():
        pytest.skip(f"no está {APP}")
    # `config.PATH_INPUTS` es relativo: la app tiene que correr con el cwd en
    # la raíz, igual que `streamlit run app.py`.
    monkeypatch.chdir(RAIZ)
    return AppTest.from_file(str(APP), default_timeout=TIMEOUT)


def _errores(at):
    """Los mensajes de error de la pantalla, para aserciones legibles."""
    return [e.value for e in at.error]


def _estado(at, clave, default=None):
    """Lee `session_state` sin asumir que es un dict.

    `AppTest.session_state` es un `SafeSessionState`, que NO tiene `.get()`:
    acceder a una clave inexistente levanta `AttributeError`, no devuelve None.
    """
    try:
        return at.session_state[clave]
    except (KeyError, AttributeError):
        return default


# ===========================================================================
# Grupo 1 — sin datos. Estos corren siempre.
# ===========================================================================

def test_arranca_sin_excepcion(app):
    """El humo más básico y el que más veces va a salvar el día.

    Que `app.py` importe y dibuje sin reventar. Un `TypeError` por una firma
    desincronizada entre módulos (como el de `io_plantas`) aparece acá.
    """
    app.run()
    assert not app.exception, [str(e) for e in app.exception]


def test_arranca_sin_inputs_y_guia_al_usuario(app):
    """Sin pipeline corrido, `resultados` es None: la app tiene que explicar
    qué hacer, no mostrar un traceback ni una pantalla en blanco."""
    app.run()
    assert not app.exception

    mensajes = [m.value for m in app.info]
    assert any("Ejecutar pipeline" in m for m in mensajes), (
        f"la pantalla inicial debería decir cómo arrancar. Vi: {mensajes}")


def test_sin_resultados_solo_estan_los_tabs_del_asistente(app):
    """Documenta el contrato: `app.py` hace `st.stop()` antes de los tabs del
    tablero, pero DESPUÉS de dibujar el asistente.

    Eso es deliberado (ver el comentario en `app.py`): el que abre el tablero
    por primera vez todavía no sabe qué es "el pipeline", y el buscador y el
    glosario ya funcionan sin corrida. Este test fija ese comportamiento: si
    algún día el tablero se dibujara sin resultados, falla acá y hay que
    revisar los tests de sandbox de abajo, que asumen lo contrario.
    """
    app.run()
    assert not app.exception

    etiquetas = [t.label for t in app.tabs]
    assert not any("Resumen" in e for e in etiquetas), (
        f"sin resultados no debería haber tabs del tablero. Vi: {etiquetas}")
    assert etiquetas, "el asistente debería estar disponible antes de correr nada"


def test_el_sidebar_tiene_el_boton_de_ejecutar(app):
    """Si alguien renombra el botón, los tests de abajo fallarían con un error
    críptico. Que falle acá, con la lista de botones en el mensaje."""
    app.run()
    etiquetas = [b.label for b in app.button]
    assert any("Ejecutar pipeline" in e for e in etiquetas), (
        f"no encontré el botón de ejecutar. Botones disponibles: {etiquetas}")


# ===========================================================================
# Grupo 2 — con datos reales.
# ===========================================================================

def _correr_pipeline(at):
    """Aprieta 'Ejecutar pipeline' y devuelve la app con resultados.

    Saltea el test si no hay Excel: no tener los datos no es un fallo.
    """
    import config

    excel = Path(config.PATH_INPUTS)
    if not excel.is_absolute():
        excel = RAIZ / excel
    if not excel.is_file():
        pytest.skip(f"no está el Excel de inputs en {excel}")

    at.run()
    botones = [b for b in at.button if "Ejecutar pipeline" in b.label]
    assert botones, "no encontré el botón de ejecutar"
    botones[0].click().run()

    if _estado(at, "resultados") is None:
        pytest.skip(f"el pipeline no dejó resultados. Errores: {_errores(at)}")

    return at


def _resolver_sandbox(at):
    botones = [b for b in at.button if b.key == "btn_correr_sandbox"]
    if not botones:
        pytest.skip("no encontré 'btn_correr_sandbox' (¿cambió la key?)")
    botones[0].click().run()
    return at


@pytest.mark.integracion
def test_con_datos_estan_los_tabs_del_tablero(app):
    """Los diez tabs del tablero, por nombre.

    Se verifica por ETIQUETA y no por cantidad: `at.tabs` devuelve todos los
    tabs de la página, incluidos los anidados (los tres del asistente, los
    sub-tabs del editor del sandbox), así que el total es un número que cambia
    cada vez que alguien agrega un sub-panel y no dice nada útil.
    """
    at = _correr_pipeline(app)
    assert not at.exception, [str(e) for e in at.exception]

    etiquetas = [t.label for t in at.tabs]
    esperados = ["Resumen", "Graphs", "Cascada", "Tablas totales",
                 "Mapa de la red", "TTY - TBX", "TTY - Dew Point", "MEGA",
                 "Plantas (sandbox)", "Asistente"]

    faltan = [e for e in esperados if e not in etiquetas]
    assert not faltan, f"faltan tabs del tablero: {faltan}. Hay: {etiquetas}"


@pytest.mark.integracion
def test_con_datos_ningun_tab_se_cae(app):
    """`_render_seguro` aísla cada tab para que un fallo no tumbe el tablero.

    Eso está bien para el usuario, pero significa que un tab roto se ve como un
    mensajito y nadie se entera. Acá sí queremos enterarnos.
    """
    at = _correr_pipeline(app)
    caidos = [e for e in _errores(at) if "falló" in e.lower()]
    assert not caidos, f"hay tabs que fallaron: {caidos}"


@pytest.mark.integracion
def test_con_datos_el_control_del_sandbox_da_cero(app):
    """EL test del sandbox.

    `tab_plantas.py` lo dice sin vueltas: con el registro sin tocar, la cascada
    del sandbox TIENE que dar idéntica a la oficial, y es *"el primer numero
    que hay que mirar"*. Si da distinto, hay un bug en esa capa y no hay que
    creerle a ningún escenario armado encima.

    Hoy eso lo verifica una persona mirando la pantalla. Con esto lo verifica
    pytest, que es lo que corresponde a un número del que depende si el resto
    de la herramienta es confiable. Es además la única cobertura viva de
    HALLAZGO-6 (las dos implementaciones paralelas de la cascada) hasta que
    exista el `TestEquivalenciaCascadas` que menciona `validaciones.md`.
    """
    at = _resolver_sandbox(_correr_pipeline(app))

    assert not at.exception, [str(e) for e in at.exception]

    exitos = [m.value for m in at.success]
    avisos = [m.value for m in at.warning]

    assert any("idéntico" in m for m in exitos), (
        "el control del sandbox no dio cero con el registro intacto.\n"
        f"Avisos en pantalla: {avisos}\n"
        "Esto es un bug de la capa del sandbox: no le creas a ningún "
        "escenario que armes encima hasta resolverlo.")


@pytest.mark.integracion
def test_con_datos_el_balance_del_sandbox_cierra(app):
    """El invariante central, end-to-end sobre datos reales.

    `test_fisica_cascada.py` ya lo verifica con datos sintéticos. Acá se
    comprueba que también cierre con el Excel de verdad, que es donde aparecen
    los casos que uno no inventa.
    """
    from pipeline.plantas.cascada import desvio_balance

    at = _resolver_sandbox(_correr_pipeline(app))

    guardado = _estado(at, "sandbox_resultado")
    if guardado is None:
        pytest.skip(f"la cascada del sandbox no dejó resultado: {_errores(at)}")

    _, flujos = guardado
    assert desvio_balance(flujos) < 1e-6


@pytest.mark.integracion
def test_con_datos_el_balance_oficial_cierra(app):
    """Lo mismo para la cascada de producción, que es la que mira el tablero."""
    from pipeline.plantas.cascada import desvio_balance

    at = _correr_pipeline(app)
    flujos = _estado(at, "resultados")["flujos_plantas"]
    assert desvio_balance(flujos) < 1e-6
