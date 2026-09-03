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
bypass por planta, derivaciones, volumen a sistema de transporte, **filas sin
PCS**, HUBs sin reparto y el panel de calidad de datos.

La regla de **filas sin PCS** merece una nota, porque es el tipo de aviso que
justifica que exista el explicador. Una fila sin PCS queda sin convertir en la
vista 9.300, conviviendo con las convertidas en la misma tabla: no da error, da
un número con cara de número en la unidad equivocada. `construir_vista_9300` lo
avisa, pero por la sidebar, donde compite con los mensajes de carga del Excel y
se pierde. La regla lo detecta desde los resultados físicos, sin depender de
que `app.py` le pase sus avisos.

Los umbrales están todos juntos arriba del archivo. Agregar una regla es una
función que reciba el contexto y devuelva `Hallazgo`s, sumada a `_REGLAS`; si una
regla falla, se reporta esa y las demás siguen.

### Qué NO se le manda al modelo

`resumen_resultados` omite a propósito dos cosas que **sí** están en
`resultados`:

- la tabla **Propiedades gas de salida** (z, densidad, PCS, IW por corriente);
- las claves `pcs` e `iw` de **`mezcla_transporte`**.

El motivo: el tablero decidió no publicar calidad de gas
(`decisiones/0008`), entre otras cosas porque esos números nunca se validaron
contra una referencia. Si viajaran en el contexto, el modelo contestaría
preguntas de calidad con ellos — con total fluidez y sin que nada avisara que
son cifras que el proyecto retiró. En su lugar va una sección corta que dice
que la calidad no es una salida y para qué se usa el PCS hoy.

Es el caso general de una regla que conviene tener presente: **lo que no le
mandás es tan parte del diseño como lo que le mandás.**

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

(tab_resumen, ..., tab_sandbox, tab_asistente) = st.tabs(
    [..., "Plantas (sandbox)", "Asistente"])

with tab_asistente:
    _render_seguro("Asistente", panel_asistente, resultados_fisicos, PARAMS,
                   serie=st.session_state.get("serie"), factor_mm=FACTOR_MM)
```

Se le pasa `resultados_fisicos` (STD), **no** la vista 9.300: el explicador
declara sus unidades y el sandbox trabaja en STD.

**El asistente existe sólo después de correr el pipeline**, porque los tabs no
se dibujan antes. La pantalla previa es `ui/bienvenida.py`: la guía de uso, el
aviso de las unidades y el del botón, y nada más.

Sin nada más que eso, el tab ya funciona completo en modo sin IA.

> **Hubo una versión con burbuja flotante** (un `st.dialog` disparado desde un
> botón fijado con CSS), disponible también antes de la corrida. Se sacó: dos
> entradas a lo mismo obligaban a mantener la posición con CSS y a duplicar
> claves de widget, para un beneficio que no compensaba. Si alguna vez se
> retoma, lo aprendido: `st.dialog` ya hereda el comportamiento de
> `st.fragment` —interactuar adentro no rerenderiza la app— pero **abrirlo** sí
> es un rerun completo, así que el disparador tiene que dibujarse arriba de
> todo para que el modal aparezca rápido. Y no envolverlo en un fragment:
> anidar diálogos en fragments tiene bugs conocidos.

## Encender la IA (opcional)

Soporta **dos proveedores**. El que se usa depende de qué key esté cargada; si
están las dos y nadie eligió, gana Anthropic (es la que no entrena con lo que
recibe, o sea el default más conservador).

```toml
# .streamlit/secrets.toml  — va en .gitignore, nunca al repo
ANTHROPIC_API_KEY = "sk-ant-..."     # si está, se usa Anthropic
GEMINI_API_KEY    = "AIza..."        # si está, se usa Gemini

ASISTENTE_PROVEEDOR = "gemini"       # opcional: forzar uno
ASISTENTE_MODELO    = "..."          # opcional: pisar el modelo
ASISTENTE_BOTS      = "docs"         # opcional: qué bots tienen IA
GEMINI_TIER_PAGO    = true           # declarar que la key no es gratuita
```

En **Streamlit Community Cloud** no se pueden setear variables de entorno: todo
esto va en Manage app → Settings → Secrets.

Y agregá al `requirements.txt` **sólo la SDK que vas a usar** — en 1 GB de RAM
cada dependencia cuenta:

| Proveedor | Paquete |
|---|---|
| Anthropic | `anthropic` |
| Gemini | `google-genai` ⚠️ **no** `google-generativeai`, que está archivada |

Verificalo sin levantar la app:

```bash
python tools/probar_asistente.py            # SDK, credencial, caché, costo
python tools/probar_asistente.py --modelos  # qué modelos tiene TU key
```

### El interruptor por bot (`ASISTENTE_BOTS`)

Los tres bots no mandan lo mismo:

| Bot | Qué envía |
|---|---|
| `docs` | la documentación del proyecto |
| `resultados` | la documentación **más los números de la corrida** |
| `agente` | lo mismo, y además opera el sandbox |

Esa diferencia importa según el proveedor, así que el **default cambia**:

- **Anthropic**, o **Gemini con `GEMINI_TIER_PAGO = true`** → los tres.
- **Gemini en tier gratuito** → sólo `docs`.

El motivo es de política de datos, no técnico: en el tier gratuito de Gemini
**lo que enviás puede usarse para entrenar sus modelos y ser revisado por
personas**, y Google pide explícitamente no mandar información confidencial a
los servicios no pagos. Capacidades y volúmenes de plantas entran en esa
categoría. La UI lo dice en pantalla cuando un bot está apagado por este
motivo, con la línea exacta para habilitarlo si se decide que está bien.

Ojo con el nombre: lo que apaga `ASISTENTE_BOTS` es **el chat de IA** de ese
bot, no sus funciones. Con `resultados` apagado el explicador sigue leyendo la
corrida y marcando plantas saturadas; con `agente` apagado el sandbox se opera
igual desde su tab. Lo único que falta es poder pedírselo escribiendo.

Ejemplos de configuración:

```toml
ASISTENTE_BOTS = "agente"                      # sólo el operador del sandbox
ASISTENTE_BOTS = "docs,resultados"             # sin agente
ASISTENTE_BOTS = "docs,resultados,agente"      # los tres (o "todos")
```

Nada de esto reemplaza la validación con seguridad de la información: **la
política de la empresa manda sobre este documento.**

### Gemini: lo que hay que saber

- **Tier gratuito: sólo Flash y Flash-Lite** desde el 1/4/2026. Un modelo Pro
  por default daría 404 o 429 con una key gratuita.
- **Límites de ~10 requests por minuto.** Un turno del agente son varias
  llamadas seguidas, así que su tope de iteraciones es **6** contra las 12 de
  Anthropic: con 12 se choca el rate limit a mitad de camino y el usuario ve un
  error en vez de una respuesta.

  Esto hace que **el agente sea el peor caso para el tier gratuito**: es el bot
  que más llamadas hace por turno. Si es el que más te importa, o le pedís de a
  un cambio por vez, o conviene habilitar billing. Los errores de rate limit se
  traducen a un mensaje que lo explica (`explicar_error` en `ia/cliente.py`), y
  el pedido queda en la conversación para reintentarlo tal cual en un minuto.
- **Los nombres de modelo rotan rapidísimo, así que el default es un ALIAS.**
  `gemini-flash-latest` apunta siempre al Flash estable del momento. Poner una
  versión concreta no aguanta: 3.8 Flash salió tres semanas después de 3.7, y
  las 2.x se van apagando con fecha (2.0 en junio de 2026, 2.5 en octubre). El
  default anterior era `gemini-2.5-flash` y empezó a dar 404.

  La contra del alias es que el modelo cambia abajo sin avisar, así que una
  respuesta puede mejorar o empeorar de un día para el otro. Para este uso es
  un precio razonable a cambio de no romperse cada mes; si alguna vez hace
  falta reproducibilidad, se fija una versión con `ASISTENTE_MODELO`.

  `--modelos` lista lo que tu key tiene habilitado, que es la respuesta
  autoritativa cuando algo no anda.

- **`gemini-flash-lite-latest` puede convenir para el agente.** Es más barato
  y, lo que importa más en el tier gratuito, tiene **más requests por minuto**,
  así que aguanta mejor los varios turnos que hace el agente del sandbox. A
  cambio de menos capacidad de razonamiento — si empieza a inventar nombres de
  planta en vez de mirar `ver_registro`, volvé a Flash.
- **Caching implícito** en los modelos Flash, sin nada que declarar. El
  contador de caché puede quedar en cero y no es un error.
- **Sin precios cargados**: en el tier gratuito no hay costo y para el pago los
  valores cambian seguido, así que la UI muestra tokens y no inventa un número
  en dólares.

### El modelo de Anthropic: Sonnet 5

`claude-sonnet-5` es el default. Tres cosas que el código ya respeta y conviene
no romper:

- **No setear `temperature`, `top_p` ni `top_k`** a valores no-default:
  devuelve 400.
- **No usar extended thinking manual**: también devuelve 400. El adaptativo
  viene activado solo.
- Contexto de 1M tokens: la documentación entra holgada aunque crezca.

### Prompt caching (sólo Anthropic)

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

Con Sonnet 5: mínimo cacheable 1.024 tokens, escritura 1,25× y **lectura 0,1×**
del input base, con 5 minutos de vida que cada uso renueva.

Gemini no tiene bloques de sistema, así que su adaptador **aplana los bloques**
en `system_instruction` y el punto de corte se descarta: era información que
sólo la API de Anthropic usaba.

Bajo cada respuesta la UI muestra los tokens y, cuando se conoce, el costo. Con
Anthropic **es la forma de verificar que el caching anda**: la segunda pregunta
seguida tiene que decir "desde caché".

### Arquitectura de la capa de IA

```
ia/proveedores.py   los dos adaptadores (Anthropic, Gemini)
ia/cliente.py       elige proveedor, normaliza uso, resuelve ASISTENTE_BOTS
```

Nadie fuera de `ia/` sabe con qué proveedor está hablando.

**El loop del agente vive en el adaptador, no en la UI.** Es lo más distinto
entre las dos APIs: Anthropic usa bloques `tool_use` / `tool_result` en el
historial, Gemini usa `function_call` / `function_response` dentro de `parts`.
La UI pasa dos callbacks —cómo ejecutar una herramienta y cómo mostrarla— y no
se entera del resto.

Los esquemas de herramienta se traducen solos (`input_schema` → `parameters`),
con una excepción que costó encontrar: **una herramienta sin parámetros tiene
que ir sin `parameters`**, porque un objeto con `properties` vacío hace que
Gemini rechace la declaración. Son `ver_registro`, `resolver_cascada` y
`comparar_con_oficial`.

### Errores de la API

Dos piezas, y la distinción entre ellas es lo importante:

**`con_reintentos` (`ia/proveedores.py`)** reintenta lo que es **transitorio**,
con backoff de 2, 4 y 8 segundos. Los dos casos reales con el tier gratuito de
Gemini:

- **503 / "overloaded" / "high demand"** — el modelo está saturado del lado de
  Google. Al tier gratuito le cortan capacidad primero cuando hay picos, así
  que aparece seguido y **no es un problema de configuración**.
- **429** — rate limit propio.

Los dos se arreglan esperando, así que reintentar es la respuesta correcta:
mostrarle el error al usuario para que apriete de nuevo es hacerle hacer a mano
lo que el código puede hacer solo.

Lo que **no** se reintenta: 401/403 (credencial), 404 (modelo inexistente), 400
(pedido mal armado). No mejoran esperando, y reintentarlos sólo demora el
mensaje útil.

Dos detalles del alcance:

- En el **stream**, el reintento envuelve la *apertura*, no el consumo: si el
  modelo ya empezó a escribir y se corta, reintentar duplicaría el texto que el
  usuario vio. Un 503 aparece casi siempre al abrir.
- En el **agente**, cada iteración reintenta por su cuenta: un 503 en el paso 4
  no tiene por qué tirar abajo los tres anteriores, que ya modificaron el
  sandbox.

**`explicar_error` (`ia/cliente.py`)** traduce lo que sí llega al usuario:
saturación, rate limit, modelo inexistente, credencial rechazada, respuesta
bloqueada por filtros. Sin eso la UI mostraba el `repr` de una excepción de la
SDK, que no le dice nada a nadie.

Un orden que importa ahí: **el 503 se chequea antes que el 429**, porque cuando
el modelo está saturado Google a veces devuelve los dos códigos en el mismo
mensaje y la causa real es la sobrecarga. Decirle "llegaste a tu límite" a
alguien que no llegó lo manda a buscar el problema donde no está.

### Cambiar de proveedor otra vez

Agregar un tercero (un endpoint corporativo, Ollama) es una clase más en
`ia/proveedores.py` con esos cuatro métodos, y su nombre en `PROVEEDORES`.
Ningún otro archivo se toca.

## Mantenimiento

- Doc nuevo en `docs/` → el buscador lo levanta solo (botón **Reindexar** si
  estás editando en caliente).
- Término que confunde a los nuevos → sumalo al `GLOSARIO`.
- Situación que se repite en las corridas → hacela una regla del explicador.
- Herramienta nueva para el agente → esquema en `ESQUEMAS` + método homónimo en
  `Ejecutor`.
