# CLAUDE.md

> Punto de entrada para cualquier LLM o agente. Corto a propósito: solo lo que
> hay que saber ANTES de tocar nada. El detalle está en los links.

## Qué es

Tablero Streamlit + pipeline pandas que modelan el balance de gas y la
producción de LGN de la cascada **TTY-TBX → TTY-Dew Point → MEGA**. Entrada: un
Excel de inputs multi-hoja. Migración de un modelo que vivía en Excel.

Sobre el pipeline hay tres capas que **no** son el modelo y conviene no
confundir con él: el **sandbox** (cascada configurable, corre aparte), el
**asistente** (tab de ayuda, con una capa opcional de IA) y la **serie
temporal** (el pipeline corrido mes a mes).

## Leé primero, en este orden

1. `docs/dominio.md` — el modelo físico. Sin esto los números no significan nada.
2. `docs/HALLAZGOS.md` — problemas conocidos de datos y config. No los "redescubras".
3. `docs/decisiones/` — antes de cambiar cómo funciona algo.
4. `docs/linaje.md` — si vas a tocar inputs o loaders.
5. `docs/mapa.md` — dónde está el código (generado; regenerar si desconfiás).

`docs/bitacora.md` es el diario de la migración: contexto histórico, con TODOs
que pueden estar resueltos. **No es fuente de verdad.**

El índice completo de la documentación, con qué documento responde qué
pregunta, está en `docs/README.md`.

## Reglas que no se negocian

1. **`vol_disponible = vol_asignado + vol_derivado + bypass`** por eslabón. Si
   un cambio rompe esto, el cambio está mal.
2. **La restricción activa es la evacuación de LGN (tn/d)**, no el ingreso.
3. **TBX→DP es traspaso (mismo gas), DP→MEGA es derivación (mezcla).** No
   unificarlos. Ver `decisiones/0003`.
4. **Cromatografía por `(Area, Gasoducto)` con fallback `Area+Sufijo`.** No
   volver al merge por `Area`. Ver `decisiones/0001`.
5. **Tres escalas de unidades conviven** (unidad de volumen, MMm³/d, tn/d).
   Chequear la escala de cada operando antes de escribir una fórmula
   (`dominio.md` §5).
6. **Las áreas con HUB no inyectan directo a la planta**: entran por el hub,
   que mezcla y reparte. Ver `decisiones/0006` y `dominio.md` §3.1.
7. **Una intervención sobre gasoductos no cambia el total que inyecta un
   área**: solo redistribuye por dónde sale. Ver `decisiones/0005`.
8. **El sandbox no toca las tablas de producción.** Trabaja sobre una copia de
   `comunes`. Ver `decisiones/0002`.

## Trampas activas (no las repitas)

### Del modelo

- **Hay DOS implementaciones de la cascada**: `modelar_TTY`/`modelar_MEGA`
  (las usa `app.py`/`main.py`) y `registro`+`resolver_cascada` (la usa el
  sandbox). Hoy dan idéntico; `TestEquivalenciaCascadas` es lo único que lo
  garantiza. Si tocás una, corré ese test. Ver HALLAZGO-6.
- `comunes["matriz_inyecciones"]` es la versión **cruda y ancha**, no la
  melteada de `inputs`. No reemplazar.
- La fila de una derivación necesita `fillna("derivacion")` en `Origen_tabla`
  o desaparece del panel de orígenes.
- `registro_base` filtra `Retenidos-RTP` por los strings literales `"TBX"`,
  `"Dew point"`, `"TBX MEGA"`. Renombrar en el Excel = planta con retención
  cero, sin error.
- **El ruteo por HUB PISA `tabla_total_yacimientos`** con la versión ajustada
  (sin las rutas ruteadas). Todo lo que consuma esa tabla —`comunes`, la red
  del mapa, los paneles, los CSVs— tiene que ver la versión de después. Si
  movés esa llamada de lugar, el volumen se cuenta dos veces.
- Un hub sin reparto utilizable en `Detalles-HUBs` deja a sus áreas inyectando
  directo, **con aviso**. Es deliberado: perder volumen en silencio es peor.

### De la configuración

- Módulo nuevo que lea `config` a nivel de módulo → agregarlo a
  `_actualizar_config_y_recargar` de `app.py`, o el sidebar no lo afecta.
  Ver `decisiones/0004`. Es el hueco de validación #1.
- `config.py` tiene un bloque duplicado con doble multiplicación
  (HALLAZGO-0). No copiar el patrón.
- El sandbox siembra su registro con `params_efectivos` (las capacidades **con
  las ampliaciones vigentes aplicadas**), no con `PARAMS` crudos. Si usara los
  crudos mientras la cascada oficial corrió con los efectivos, el control daría
  desvío sin haber bug.

### De la UI

- Cada tab se renderiza con `_render_seguro`: un tab que falla muestra su
  traceback adentro y **no tumba a los demás**. Sin eso, una excepción corta el
  script y deja en blanco todos los tabs posteriores. Ya pasó dos veces.
- El editor del sandbox corre dentro de un `st.fragment`. Al pedir rerun desde
  ahí hay que respetar el scope, o se redibuja el tablero entero por cada
  checkbox.
- Un `st.success` seguido de `st.rerun()` no se dibuja nunca. Para eso está el
  mecanismo de *flash* en `session_state`.
- Nada de widgets que dependan de claves que el reset del sandbox no barre:
  los prefijos están en `ui/sandbox_estado.py`.

### Del asistente

- El agente opera **el mismo `session_state` que la UI** (`registro_plantas`,
  `intervenciones_gasoductos`, `sandbox_resultado`): lo que arma queda visible,
  editable y deshacible con Restablecer. No hay un segundo camino de ejecución.
- Los ejecutores de herramientas **nunca levantan**: un fallo es un mensaje de
  texto para el modelo, no una excepción para Streamlit.
- Con el modelo por defecto: no setear `temperature`/`top_p`/`top_k`, ni
  thinking manual — devuelve 400. El corte del prompt caching va al final de la
  documentación, antes de los resultados; moverlo lo rompe. Ver `asistente.md`.

## Antes de dar un cambio por terminado

```bash
pytest -m "not integracion"            # verde sin excepción
pytest                                 # si hay Excel a mano
python tools/mapa_modulos.py --check   # el mapa no quedó viejo
```

Y a ojo, en el tablero:

- El **desvío de balance** en verde (`< 1e-6`).
- El **control del sandbox en cero** con el registro sin tocar. Si da distinto,
  hay un bug en esa capa y no hay que creerle a ningún escenario.

Checklist de documentación:

- ¿Cambiaste una regla del modelo? → test + ADR nuevo en `docs/decisiones/`.
- ¿Descubriste algo que contradice `dominio.md` o `linaje.md`? → corregilos en
  el mismo commit.
- ¿Agregaste una hoja al Excel o una columna calculada? → `linaje.md`.
- ¿Agregaste un chequeo? → `validaciones.md`, con su test negativo.
- Los XFAIL de los tests son a propósito (HALLAZGOS 1 y 2). No los borres: el
  xfail no estricto avisa solo el día que el dato se corrige.
