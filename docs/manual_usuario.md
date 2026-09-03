# Manual de usuario — Tablero de Balance de Gas

Cómo **usar** el tablero, sin leer código. Qué significan los números está en
`dominio.md`; qué hacer si algo falla o hay que actualizar datos, en
`operacion.md`.

> Si preferís preguntar en vez de leer: el tab **Asistente** tiene un buscador
> sobre toda esta documentación y un explicador que interpreta la corrida
> actual. Funciona sin conexión ni credenciales. Ver `asistente.md`.

---

## 1. La idea en dos líneas

El tablero modela cuánto gas trata cada planta de la cascada
**TTY-TBX → TTY-Dew Point → MEGA**, cuánto LGN produce, cuánto le pasa a la
siguiente y cuánto queda sin tratar (bypass). Todo sale de un Excel de inputs
más los parámetros que cargás en la barra lateral.

**La regla que ordena todo:** cada planta se llena hasta agotar su capacidad
de **evacuación de LGN (tn/d)** — no su ingreso de gas —, deriva el sobrante a
la siguiente, y bypasea solo lo que ni así entra. Antes de la fecha de PM,
TTY-TBX está fuera de servicio y el pool TTY va directo a Dew Point.

---

## 2. El flujo de trabajo típico

1. **Subir el Excel** (sidebar, sección 1) — opcional: sin archivo se usa el
   default configurado. El nombre del archivo en uso se muestra abajo del
   uploader.
2. **Completar los parámetros**: período, fecha de PM, ampliaciones,
   capacidades y topes de derivación.
3. **▶️ Ejecutar pipeline** — corre el período elegido y llena todos los tabs.
4. Mirar los resultados tab por tab (§4).
5. Si querés la evolución mes a mes: definir el rango en la sección de **serie
   temporal** y correrla. Eso alimenta el tab Graphs.

### Detalles de la sidebar que conviene saber

- **Los parámetros están dentro de un formulario**: los cambios no se aplican
  hasta apretar un botón de ejecución. Enter en un campo **no ejecuta nada**
  (en Streamlit ≥ 1.39): solo confirma el valor. Es a propósito — antes, un
  Enter distraído corría el pipeline entero.
- Como consecuencia, los mensajes derivados (si TBX está en servicio, cuántos
  períodos tiene el rango) reflejan el **último submit**, no lo que estás
  tipeando.
- **Período** en formato `MM-YYYY`. Formato inválido: avisa y usa el default.
- **Ampliaciones**: filas de `Fecha + Δ Evacuación + Δ Ingreso` que se *suman*
  a las capacidades base desde ese mes inclusive. En una serie se prenden solas
  mes a mes. Filas sin fecha o con ambos Δ en cero se ignoran; una fecha mal
  escrita avisa y saltea esa ampliación, sin abortar la corrida.
- **Unidades al cargar capacidades**: evacuación en **tn/d**, ingreso en
  **MMm³/d**. Cargar `25` donde va `25000` (o al revés) no da error — da
  resultados mal. Ante un resultado raro, revisá esto primero.

---

## 3. Elegir la unidad de los volúmenes

Los volúmenes se pueden ver en **MMm³/d STD** o en **MMm³/d equivalentes de
9.300 kcal**. El selector afecta a los tabs de resultados y a Graphs; cada
vista dice en qué unidad está.

Excepción: el **sandbox** re-modela la física y trabaja siempre en
**MMm³/d STD**, independiente del selector.

---

## 4. Los tabs

### Resumen — estado de cada eslabón

KPIs por planta y la tabla de **reparto del gas**: `vol_disponible`,
`vol_maximo`, `vol_asignado`, `sobrante`, `vol_derivado`, `bypass` (MMm³/d) y
LGN (tn/d). Dos cosas para leerla bien:

- Por planta siempre vale `vol_disponible = vol_asignado + vol_derivado + bypass`.
- **No sumar columnas entre plantas**: el `vol_derivado` de una es el
  `vol_disponible` de la siguiente; sumarlas cuenta el mismo gas dos veces.

Acá también aparece el **desvío de balance**: en verde si es prácticamente
cero. Si no lo está, el resultado no es confiable y no hay que usarlo.

La **forma de la cascada** se lee en esta misma tabla: `vol_derivado` es lo que
cada planta le pasa a la siguiente y `bypass` lo que pasa de largo sin tratarse.
Si la fecha de PM cae después del período, TTY-TBX está fuera de servicio y el
pool TTY entra directo a Dew Point — se ve en que TBX no trata nada. Planta por
planta, con las entradas y salidas dibujadas, está en **Esquemas de planta**.

Cada tabla tiene su botón de descarga a CSV.

### Graphs

KPIs y series temporales. **Necesita que hayas corrido la serie**; con solo la
corrida puntual muestra un aviso. Qué hay:

- Inyección por área y por HUB, y el detalle por gasoducto.
- Ingreso a planta por área / gasoducto.
- Procesado y bypass por planta.
- **Retenidos por compuesto** en tn/d, con los cortes C2 / C3 / C4 / C5+.
- Caudal disponible vs. capacidad de ingreso, por planta.
- Tabla resumen anual por planta.

Si corriste la **serie del escenario** desde el sandbox, se muestra al lado de
la oficial para comparar.

Los entregables salen de acá:

- **📄 Reporte PDF** — las láminas del dashboard en A4, para imprimir o enviar.
- **🖼️ Exportar gráficos sueltos** — PNG o SVG por gráfico, con tamaño y DPI
  configurables. El default (25,4 × 14,3 cm) es el cuerpo de una slide 16:9;
  SVG es vectorial y editable en PowerPoint, y el DPI no le aplica.

Si algún período falló al calcular la serie, el tab los lista con su error y
grafica el resto.

### Tablas totales

Explorador de las tablas del pipeline —yacimientos, flujos directos, detalles
de HUBs y el **ruteo por HUB**— y el **comparador contra el Excel de
referencia**, para verificar la migración número contra número.

### Mapa de la red

Áreas, gasoductos y plantas sobre el territorio. El grosor de línea va con la
**raíz** del volumen: en escala lineal el flujo más grande tapa a todos los
demás. Si faltan coordenadas de algún nodo, un expander lista cuáles. Si
hiciste cambios en el sandbox, se puede dibujar esa red en lugar de la oficial,
con los tramos agregados y eliminados en colores aparte.

### Esquemas de planta

El diagrama de bloques de cada planta: entradas a la izquierda, salidas a la
derecha, LGN arriba, bypass abajo. Una planta fuera de servicio se dibuja
punteada y en gris. Cada esquema se **descarga como SVG**.

### Plantas (sandbox)

Ver §6. Es un mundo aparte: **nada de lo que hagas ahí afecta a los otros
tabs**.

### Asistente

Buscador sobre la documentación, glosario y explicador de la corrida. Ver
`asistente.md`.

### Diagnósticos

Los mensajes que el pipeline imprime al correr: filas sin cromatografía,
volúmenes que desaparecen por coeficiente 0, áreas sin destino, hubs sin
reparto o sin composición cargada. **Si un resultado no cierra, este panel es
el primer lugar donde mirar.**

> Si un tab falla, muestra su error adentro y **los demás siguen funcionando**.
> Un tab en rojo no invalida al resto.

---

## 5. El ruteo por HUB

Las áreas que tienen un HUB asignado **no inyectan directo a la planta**: su
gas entra al hub, el hub lo mezcla y lo reparte entre las plantas. Las áreas
sin hub y las rutas hacia gasoductos no se tocan.

La composición con la que el hub entrega:

- la que esté cargada para ese hub en el Excel;
- si no está, la **mezcla volumétrica** de las áreas que le aportan, con aviso
  en diagnósticos.

Un hub sin reparto utilizable deja a sus áreas inyectando directo, y lo avisa:
perder volumen en silencio sería peor.

Esto aparece en la tabla **Total HUBs (ruteo)**, con una fila por hub-planta, y
explica por qué la inyección de un área puede figurar contra un hub y no contra
la planta. **No es gas perdido**: el total que inyecta el área no cambia.

---

## 6. El sandbox de plantas y gasoductos

Una cascada configurable que corre su propio modelo sobre el mismo pool de gas.
Sirve para preguntas del tipo *"¿qué pasa si agrego un tren / abro un ducto /
cambio una capacidad?"* sin tocar la corrida oficial.

> **Antes de creerle a un escenario, mirá el control.** Con el registro sin
> tocar, el sandbox tiene que dar exactamente lo mismo que el tab de reparto.
> Si el desvío no es cero ahí, hay un bug en esa capa y ningún escenario armado
> encima vale.

### 🤖 Asistente

Un flujo guiado que arma el escenario preguntando de a una cosa —qué querés
agregar, de dónde sale el gas, con qué capacidad— y muestra el resumen **antes**
de aplicar. Al confirmar, modifica el mismo registro que editarías a mano y
dispara la corrida. Es el camino corto: armar una planta a mano son unas veinte
interacciones.

### Plantas

El **canvas visual**: arrastrás para mover, conectás de un nodo a otro, click
derecho para borrar, click en una planta para editarla abajo. Las líneas al
bypass son informativas; las proporciones y topes finos se ajustan en la tabla
de conexiones. Si falta el componente de canvas, se avisa y el editor de abajo
funciona igual.

Debajo: crear plantas nuevas a partir de un preset, editar la **retención por
compuesto** y las **conexiones de salida** — a qué destino va el sobrante, en
qué proporción y con qué tope.

Al crear una planta hay una pregunta que decide todo: el **nombre de pool**. Si
lo dejás igual al nombre, la planta es un destino nuevo con su propio gas; si
ponés el de otra planta, son **dos trenes sobre el mismo gas** (el caso
TBX / Dew Point).

Sobre el reparto del sobrante: si las proporciones suman menos de 1, esa
fracción es bypass a propósito y no se redistribuye; una rama que se satura por
tope sí libera volumen que se reofrece a las demás. Las tres plantas base no se
pueden eliminar.

### Gasoductos

Altas (un ducto nuevo de un área a una planta, con volumen y cromatografía) y
bajas (sacar uno de servicio). Las bajas se aplican antes que las altas.

**El invariante:** el volumen que inyecta cada área no cambia nunca — un ducto
no crea ni destruye gas, solo cambia por dónde sale. Si un área inyecta
*únicamente* al ducto que se da de baja, sus filas se dejan como están y se
reportan: no se inventa un destino.

### Escenarios

Un escenario = **plantas + gasoductos en un solo `.json`**: es una pregunta
completa, no se parte en dos archivos. Se puede cargar uno prearmado o subir
uno propio.

Al cargar, las plantas se **mezclan por nombre** sobre lo que ya tenés (un
escenario con una sola planta no borra las demás); las intervenciones de ductos
se **reemplazan enteras**, porque son una lista ordenada y no hay forma de
identificar "la misma" intervención entre dos escenarios.

### Correr

- **Resolver cascada** — el período puntual. La salida muestra el reparto, el
  **impacto contra la corrida oficial** (cuánto ganó o perdió cada planta en
  gas y en LGN) y los esquemas.
- **Calcular serie del escenario** — corre el escenario mes a mes con el rango
  de la sidebar y lo deja en Graphs junto a la serie oficial. Son N corridas
  completas: tarda lo mismo que la serie oficial.

### Cromatografías de planta (archivo aparte)

Corrientes extra que se suman al pool de una planta **sin tocar
`inputs.xlsx`**: columnas `Planta`, `Origen`, `Volumen` (MMm³/d) y una por
compuesto. Hay una plantilla generable para no adivinar el formato. Si la suma
molar da ~100 se asume porcentaje; si no da 1, se normaliza con aviso.

### Guardar el trabajo

- **Descargar** (en Escenarios) baja el `escenario.json` para recargarlo
  después.
- **⬇️ Descargar simulación** baja un ZIP con el escenario **y** los CSVs de
  resultados, con un LEEME adentro que explica cada archivo.
- **Restablecer** borra todo el sandbox, con confirmación en dos pasos. Antes
  de confirmar, si el escenario vale algo: descargalo.

> Las capacidades dentro de `escenario.json` están en unidades internas del
> modelo. **No lo edites a mano**: cargalo y cambiá los valores en pantalla.

---

## 7. Errores y avisos frecuentes

| Veo… | Qué es | Qué hago |
|---|---|---|
| "Configurá las plantas y dale a Resolver cascada" | El sandbox no corrió todavía | Apretar **Resolver cascada** |
| Graphs pide recalcular la serie | Hay corrida puntual pero no serie | Correr la serie desde la sidebar |
| El desvío de balance no está en verde | El resultado no cierra | No usar esos números; ver Diagnósticos |
| El control del sandbox da distinto de cero sin tocar nada | Bug en la capa del sandbox | No creerle a ningún escenario hasta resolverlo |
| "El pipeline falló: …" en la sidebar | Problema del Excel o de los parámetros | Leer el error; casos típicos en `operacion.md` §3 |
| Un tab en rojo con traceback | Falló solo ese tab | Los demás siguen; copiar el traceback y reportarlo |
| Avisos de filas sin cromatografía / sin destino / hub sin reparto | Datos conocidos del Excel | Ver `HALLAZGOS.md` antes de alarmarse |
| El volumen de un área "se movió" de planta | Ruteo por HUB (§5) | No es gas perdido |
| Resultado sospechosamente chico o gigante | Casi siempre unidades (tn/d vs MMm³/d) | Revisar §2, último punto |
