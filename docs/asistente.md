# Asistente

Tab del tablero pensado para gente **ajena al proyecto**. Tres asistentes, cada
uno en **dos capas**: una que funciona siempre y otra que se enciende sola si
hay credencial de IA.

|  | sin credencial (siempre) | con credencial (extra) |
|---|---|---|
| 📖 Documentación | buscador de `docs/` + glosario | chat sobre los docs |
| 📊 Resultados | explicador determinista de la corrida | chat sobre la corrida |
| 🛠️ Sandbox | guía paso a paso | agente que opera el sandbox |

**La capa de abajo no usa red, ni key, ni saca un solo dato del servidor.** Es
la que ve todo el mundo. La de arriba aparece si existe `ANTHROPIC_API_KEY`;
hasta entonces el tab avisa que existe y no molesta.

## Dos presentaciones, un solo cuerpo

El mismo asistente se muestra de dos formas:

- **La burbuja 💬** abajo a la derecha, disponible en todo momento sin salir de
  lo que estás mirando. Es la entrada principal.
- **El tab Asistente**, para cuando querés leer con espacio.

Para que no se desincronicen, la lógica vive en `cuerpo_documentacion`,
`cuerpo_resultados` y `cuerpo_sandbox` (`ui/tab_asistente.py`) y cada
presentación sólo decide dónde dibujarlas. De ahí el parámetro `sufijo`:
Streamlit exige claves de widget únicas y las dos presentaciones dibujan los
mismos botones. **Las historias de conversación NO llevan sufijo**: se
comparten a propósito, así preguntás en la burbuja y la charla sigue estando en
el tab.

### Cómo flota la burbuja

Streamlit no tiene widgets flotantes. El disparador es un `st.button` dentro de
un `st.container(key=...)`: desde Streamlit **1.39** esa key se traduce en una
clase `st-key-<key>` en el DOM, que es el hook oficial para CSS (tanto que
`stylable_container` de streamlit-extras quedó deprecado a favor suyo). El
panel es un `st.dialog` (GA desde **1.37**), modal de verdad y manejado por
Streamlit.

O sea: de todo el asistente, **lo único que depende de CSS es la posición de un
botón**. Si esa regla algún día deja de aplicar, el botón aparece en su lugar
normal del flujo y nada más se rompe. Con Streamlit < 1.37 el modal se degrada
a un expander.

Dentro del modal la entrada de texto es un `text_input` + botón, **no**
`st.chat_input`: ese widget tiene restricciones sobre dónde puede vivir.

## Por qué híbrido

El buscador y el explicador son más confiables que un modelo para lo que más se
pregunta ("qué es esto", "por qué da esto"): no alucinan y las reglas las
escribimos nosotros. El modelo aporta en lo que ellos no pueden — reformular una
pregunta mal planteada, cruzar dos docs, operar el sandbox en lenguaje natural.
Con las dos capas el tablero sirve desde el día uno, y habilitar la IA después
es cambiar un secreto, no reescribir código.

## Arquitectura

```
ia/
  buscador.py       # SIN IA: índice de docs/ por secciones + glosario
  explicador.py     # SIN IA: reglas deterministas sobre los resultados
  cliente.py        # IA: única puerta a la API (key, modelo, streaming, tools)
  contexto.py       # IA: docs completos, resumen de la corrida, system prompts
  herramientas.py   # IA: esquemas de tools + Ejecutor sobre session_state
ui/
  tab_asistente.py  # el tab: capa sin IA arriba, chat plegado abajo
```

### Buscador (`ia/buscador.py`)

Parte cada `.md` en secciones por encabezado y puntúa por coincidencia de
términos, con peso ×3 si el término está en el título. **No genera texto**:
muestra los fragmentos reales, así que no puede inventar. El `GLOSARIO` es lo
único escrito a mano y lo más valioso para el recién llegado: los términos de la
primera pantalla (cascada, pool, retenidos, PCS, IW, lámina objetivo, bypass,
desvío de balance, HUB, sandbox) con sinónimos para que los encuentre aunque
pregunten distinto.

No es semántico: "por qué no cierra el balance" encuentra la sección de balance
por la palabra, no por el sentido. Para eso está el glosario.

**Respeta la jerarquía documental del README.** Un buscador que trate a todos
los documentos por igual puede contestar con un TODO de `bitacora.md` resuelto
hace meses, con la misma cara de certeza que si citara `dominio.md`. Por eso:

- `PESOS` — multiplica el puntaje por documento. `dominio.md` y
  `manual_usuario.md` arriba; `mapa.md` (generado) y `bitacora.md` (histórico,
  no fuente de verdad) abajo.
- `OBSOLETOS` — los saca del índice. Son los archivos que el README declara
  eliminados (`data_dictionary.md`, `decisions.md`, `changelog.md`, `arq.md`);
  si siguen en la carpeta, el tab lo avisa en pantalla para que se borren.
- `ADVERTENCIAS` — el aviso que se muestra sobre un resultado de un documento
  que hay que leer con reservas.

Un documento nuevo entra solo, con peso 1.0. Sólo hay que tocar el archivo si
es histórico, obsoleto o especialmente autoritativo.

**También indexa `flujo_pipeline_gas.html`**, con un limpiador de etiquetas
mínimo. Sería absurdo que el documento que el README llama *el mejor punto de
entrada para alguien que viene del Excel* fuera justo el único invisible para
el buscador.

### Explicador (`ia/explicador.py`)

Una lista de reglas, cada una con su umbral y su texto. Devuelve `Hallazgo`s con
nivel (`problema`/`atencion`/`ok`/`info`), título, detalle con los números a la
vista y **en qué tab mirarlo**. Hoy cubre: balance, estado de TBX, saturación y
bypass por planta, derivaciones, volumen a sistema de transporte, HUBs sin
reparto y el panel de calidad de datos.

Los umbrales están todos juntos arriba del archivo. Agregar una regla es una
función que reciba el contexto y devuelva `Hallazgo`s, sumada a `_REGLAS`; si una
regla falla, se reporta esa y las demás siguen.

### Capa IA

- El operador opera **el mismo estado que la UI del sandbox**
  (`registro_plantas`, `intervenciones_gasoductos`, `sandbox_resultado`): lo que
  arma queda visible y editable ahí, y el botón Restablecer lo deshace.
- Las herramientas no conocen los campos internos de `PlantaConfig`: editan por
  round-trip `a_dict()`/`desde_dict()` y devuelven los errores como texto al
  modelo, que mira `ver_planta` y se corrige.
- Los ejecutores nunca levantan: un fallo de herramienta es un mensaje para el
  modelo, no una excepción para Streamlit.
- El loop del agente corta a las 12 iteraciones.

## Integración en app.py

```python
from ui.tab_asistente import panel_asistente
from ui.asistente_popup import asistente_flotante

# 1. El tab
(tab_resumen, ..., tab_sandbox, tab_asistente) = st.tabs(
    [..., "Plantas (sandbox)", "Asistente"])

with tab_asistente:
    _render_seguro("Asistente", panel_asistente, resultados_fisicos, PARAMS,
                   serie=st.session_state.get("serie"), factor_mm=FACTOR_MM)

# 2. La burbuja — al FINAL del script y FUERA de todo `with tab:`
asistente_flotante(resultados_fisicos, PARAMS,
                   serie=st.session_state.get("serie"), factor_mm=FACTOR_MM)
```

En la pantalla de bienvenida (antes del `st.stop()` que corta cuando no hay
corrida) se dibuja además el panel completo: es justo el momento en que alguien
ajeno más lo necesita, y ahí el buscador y el glosario ya funcionan.

Se le pasa `resultados_fisicos` (STD), **no** la vista 9.300: el explicador
declara sus unidades y el sandbox trabaja en STD.

Sin nada más que eso, el tab ya funciona completo en modo sin IA.

## Encender la IA (opcional)

1. `anthropic` en `requirements.txt`.
2. `.streamlit/secrets.toml` (que va en `.gitignore`, no al repo):

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ASISTENTE_MODELO = "claude-sonnet-5"   # opcional, es el default
   ```

3. Verificalo sin levantar la app:

   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   python tools/probar_asistente.py
   ```

   Hace dos preguntas iguales y confirma que la segunda lee del caché. Sirve
   para separar "la credencial está mal" de "el tab tiene un bug".

### El modelo: Sonnet 5

`claude-sonnet-5` es el default. Tres cosas de este modelo que el código ya
respeta y conviene no romper:

- **No setear `temperature`, `top_p` ni `top_k`** a valores no-default: devuelve
  400. El cliente no los toca.
- **No usar extended thinking manual**: también devuelve 400. El thinking
  adaptativo viene activado solo.
- Contexto de 1M tokens, así que la documentación entra holgada aunque crezca.

### Prompt caching

El asistente manda los docs enteros en cada pregunta. Para que eso no se pague
completo todas las veces, el `system` va en **bloques** ordenados de estable a
volátil, con el corte del caché al final de la documentación:

```
[0] <documentacion>      ← cache_control, idéntico en los tres bots
[1] instrucciones del bot
[2] <resultados>         ← cambia en cada corrida
```

El corte va ahí y no más adelante a propósito: el caché sólo pega si el prefijo
hasta el corte es idéntico entre llamadas. Si estuviera después de los
resultados, cada corrida escribiría una entrada nueva y no leería ninguna.

Con Sonnet 5: mínimo cacheable 1.024 tokens (los docs lo superan de sobra),
escritura 1,25× y **lectura 0,1×** del input base. En la práctica, la primera
pregunta paga los docs completos y las siguientes pagan una décima parte,
mientras se pregunte con menos de 5 minutos de diferencia (esa es la vida del
caché, y cada uso la renueva).

Bajo cada respuesta la UI muestra los tokens y el costo estimado. **Es la forma
de verificar que el caching anda**: la segunda pregunta seguida tiene que decir
"desde caché". Los precios están en `PRECIOS` (`ia/cliente.py`) y son sólo para
ese cartelito — la fuente de verdad es la consola de Anthropic. Si cambiás de
modelo, actualizalos o el número miente.

Antes de hacerlo con datos reales: **los bots 2 y 3 envían números de la corrida
a un tercero.** Validarlo con seguridad de la información; la política de la
empresa manda sobre este documento. Si no se aprueba, la capa sin IA queda como
está y no se pierde nada.

Costo aproximado con Sonnet 5 ($2/MTok de entrada, $10/MTok de salida): del
orden de centavos por pregunta, y bastante menos con el caché caliente. Un turno
del agente son varias llamadas, no una, así que cuesta más que una pregunta
suelta; el cartelito bajo su respuesta suma todas.

### Cambiar de proveedor

`ia/cliente.py` es la única puerta de salida: para apuntar a un endpoint
corporativo o a un modelo local (Ollama), se toca ese archivo y nada más.

## Mantenimiento

- Doc nuevo en `docs/` → el buscador lo levanta solo (botón **Reindexar** si
  estás editando en caliente).
- Término que confunde a los nuevos → sumalo al `GLOSARIO`.
- Situación que se repite en las corridas → hacela una regla del explicador.
- Herramienta nueva para el agente → esquema en `ESQUEMAS` + método homónimo en
  `Ejecutor`.
