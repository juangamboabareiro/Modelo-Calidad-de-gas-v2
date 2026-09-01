# Dominio — Modelo de acondicionamiento de gas CN-VM

Qué modela el sistema y qué significan los números. **Este documento no habla
de Python**: debería sobrevivir a un rewrite completo del código. Si buscás
dónde está algo, ver `mapa.md`; si buscás de qué celda del Excel sale un dato,
ver `linaje.md`; si buscás por qué algo se decidió así, ver `decisiones/`.

---

## 1. Qué se modela

El balance de gas y la producción de **LGN** (líquidos de gas natural) de una
cascada de plantas de tratamiento en las cuencas Neuquina y Vaca Muerta. Para
un período mensual dado, el modelo responde:

- cuánto gas trata cada planta y cuánto LGN produce,
- cuánto gas le pasa a la planta siguiente,
- cuánto no se trata en ninguna (**bypass**),
- con qué composición entra y sale el gas de cada una.

La entrada es la inyección de cada área productiva (yacimientos, hubs y flujos
directos a gasoducto) con su cromatografía. La salida son los flujos por planta
y las tablas totales por origen.

**Lo que el modelo no hace** (importante para no pedirle lo que no puede dar):
no rutea el gas residual hacia los gasoductos de evacuación, no modela la
capacidad de esos ductos, y no calcula fuel gas. La cascada termina en
tratado / derivado / bypass y ahí se corta.

## 2. La cascada

Tres plantas hoy, con dos futuras ya previstas (TBX El Portón, VM LIQ):

```
pre-PM :  pool TTY ─────────────────► DP ─(sobra)─► MEGA ─(sobra)─► bypass
          (TBX fuera de servicio)      └─(resto)──► bypass DP

post-PM:  pool TTY ─► TBX ─(sobra)─► DP ─(sobra)─► MEGA ─(sobra)─► bypass
                       └─(resto)──► bypass TBX
```

### 2.1 La idea contraintuitiva: dos trenes, un solo gas

**TTY-TBX y TTY-Dew Point no son dos plantas en paralelo: son dos trenes sobre
el MISMO pool de gas.** Comparten la cromatografía; lo único que se reparte
entre ellos es el volumen. El pool TTY se llena primero en TBX, y lo que sobra
pasa a DP.

MEGA, en cambio, tiene un **pool propio de otra composición**.

De ahí sale la distinción más importante del modelo:

| Tramo | Tipo | Qué pasa con la cromatografía |
|---|---|---|
| TBX → DP | **traspaso** | idéntica; solo se pasa volumen |
| DP → MEGA | **derivación** | el gas entra a la mezcla de MEGA y la modifica |

Confundirlos es el error clásico: aplicar mezcla en TBX→DP es mezclar el gas
consigo mismo y corrompe la cromatografía de DP. El gas derivado de DP a MEGA
sale **sin tratar**, así que viaja con la cromatografía de *entrada* de DP, no
con la del residual. Ver `decisiones/0003`.

### 2.2 "Llenarse" = agotar la evacuación de LGN

La restricción activa de cada planta **no** es cuánto gas puede recibir, sino
cuántas **toneladas por día de LGN puede evacuar**. La capacidad de ingreso de
gas rara vez limita; entra solo como un mínimo adicional.

La matemática de un eslabón:

```
lgn_unitario = LGN del pool [tn/d] / volumen del pool        (§2.4)
vol_maximo   = capacidad_evacuacion / lgn_unitario
               (y min() con la capacidad de ingreso, si está definida)

vol_asignado = min(vol_disponible, vol_maximo)
sobrante     = vol_disponible − vol_asignado
vol_derivado = min(sobrante, tope de traspaso)
bypass       = sobrante − vol_derivado
```

**El invariante que cierra el balance, por eslabón:**

```
vol_disponible = vol_asignado + vol_derivado + bypass
```

Como el `vol_derivado` de un eslabón es el `vol_disponible` del siguiente, la
cadena entera cierra sin doble conteo. Si este invariante se rompe, el
resultado no es confiable — no hay excepción.

Consecuencia práctica que se malinterpreta seguido: **las columnas no se suman
entre plantas.** El derivado de una ya está contado como disponible de la
siguiente.

Caso borde con sentido físico: si una planta no retiene nada
(`lgn_unitario ≤ 0`), no tiene restricción de líquido y su `vol_maximo` es
infinito, o la capacidad de ingreso si está definida.

### 2.3 Reparto entre varios destinos

Una planta puede derivar su sobrante a **N destinos con proporciones**, cada
rama con un tope físico opcional. Dos tipos de bypass que no se tratan igual:

- **Estructural** — si las proporciones suman menos de 1, esa fracción nunca se
  ofrece a nadie. Es una decisión del operador ("de lo que sobre, mandá el
  30%"): el resto es bypass por definición y **no se redistribuye**.
- **Por tope** — una rama saturada libera volumen que **sí se reofrece** a las
  ramas con lugar, en proporción entre ellas. Es lo que haría un splitter real;
  sin redistribución, agregar una rama con tope chico empeoraría el resultado
  global.

Proporciones que suman más de 1 se renormalizan hacia abajo: no se puede
derivar más sobrante del que hay. Una rama al 0% no recibe nada aunque sobre
gas: se puso en 0 a propósito.

### 2.4 Los retenidos son lineales

A composición y coeficientes de retención fijos, el LGN retenido es
**proporcional al volumen tratado**. Por eso:

- se modela el pool completo una sola vez,
- `lgn_unitario` = LGN del pool / volumen del pool,
- y todo lo demás (retenidos de la planta, tabla por origen) se escala
  pro-rata a `vol_asignado / vol_pool`, sin re-modelar.

Es exacto, no una aproximación.

### 2.5 Parada de mantenimiento (PM)

`FECHA_PM_TTY_TBX` marca el ingreso en servicio del tren TBX. Antes de esa
fecha TBX está **fuera de servicio**: no trata nada, no produce LGN, y sus
topes de traspaso **se ignoran** (el tren no existe, el gas pasa de largo), así
que el pool TTY entero cae en DP.

### 2.6 Ampliaciones

Una ampliación es un **Δ de capacidad con fecha de vigencia**: se suma a la
capacidad base (evacuación en tn/d, ingreso en MMm³/d) desde ese mes inclusive.
Se pueden cargar varias. En una serie temporal se activan solas mes a mes, así
que la curva refleja el plan de expansión sin correr un escenario por etapa.

## 3. El pool de una planta

El gas de una planta son todas las filas cuyo destino (`Gasoducto`) es su
`nombre_pool`, sumando **tres fuentes**:

1. **Vía gasoducto** — flujos directos que declaran ese destino.
2. **Inyección directa** — áreas sin hub que inyectan directo a la planta (caso
   MEGA y TBX El Portón; TTY no las tiene porque VMN y VMS son gasoductos).
3. **Vía HUB** — el gas de las áreas con hub, ya mezclado y repartido por el
   hub (§3.1).

más, cuando corresponde, las **derivaciones** de otras plantas y las
cromatografías cargadas a mano en un escenario. Cada fila lleva la traza de su
origen (`flujos_directos` / `yacimientos` / `hubs` / `derivacion`).

Dos plantas con el mismo `nombre_pool` son dos trenes sobre el mismo gas — es
la relación TBX / Dew Point, y lo que permite sumar un tercer tren sin tocar
nada.

### 3.1 Ruteo por HUB

**Un área con HUB asignado no inyecta directo a la planta.** Su gas entra al
hub, el hub lo mezcla y lo reparte entre las plantas. Las áreas sin hub y las
rutas hacia gasoductos no se tocan: el hub solo intermedia la entrega a
plantas.

La composición con la que el hub entrega, en orden de preferencia:

1. la **premisa cargada** para ese hub (input explícito);
2. si no está, la **mezcla volumétrica** de las áreas que le aportan, con
   aviso.

El reparto entre plantas sale de los renglones-hub del detalle de HUBs y se usa
como **proporción, no como volumen absoluto**: así el balance cierra en cada
período aunque la hoja traiga volúmenes cargados en otro momento.

**Por qué importa.** Si un hub reparte entre varios destinos, cada planta debe
recibir la composición *del hub*, no la de cada área por separado, y el reparto
es una decisión del hub, no de cada área. El caso de control es un hub que
manda el 100% a una sola planta y cuya composición es la mezcla volumétrica:
ahí el gas de entrada no cambia, porque la mezcla es lineal. Ver
`decisiones/0006`.

**Regla de seguridad.** Un hub sin renglón de reparto utilizable deja a sus
áreas inyectando directo, como antes, con aviso. Mantener el comportamiento
viejo para un hub puntual es preferible a perder su volumen en silencio.

## 4. Cromatografía

### 4.1 De dónde sale

Cada fila `(Area, Gasoducto)` necesita una composición molar. La búsqueda es en
dos etapas:

1. **Por ruta** `(Area, Gasoducto)` — para premisas específicas de un destino.
2. **Fallback** `Area + Sufijo` — el sufijo desambigua áreas con dos
   cromatografías.

El caso testigo del sufijo es **Fortín de Piedra**: una medición para el gas
que va por planta (CO Paralelo, NEUII, GPM → sufijo `Planta`) y otra para el
que no (VMS, YPF-RDM, MEGA → sufijo `Otra`). Sin la desambiguación, elegir una
al azar le sacaba **34,7% del C3+** al pool de MEGA alimentado por áreas.
Sufijos válidos hoy: `Otra`, `Planta`, `TBX`. Ver `decisiones/0001`.

Una fila con volumen y **sin** cromatografía es un error silencioso grave:
aporta gas y cero LGN, o sea que baja el `lgn_unitario` del pool e infla el
`vol_maximo` de la planta sin que nada salte.

### 4.2 Fracciones molares

14 compuestos, y cada composición suma 1:

```
C1 │ C2 │ C3 │ iC4 nC4 │ iC5 nC5 nC6 nC7 nC8 nC9 nC10 │ N2 CO2
metano etano propano  butanos          gasolina         inertes
```

El **gas residual** (lo que sale de la planta) suma *menos* de 1: es lo que
queda después de retener LGN. Un residual que sume más que la entrada es
físicamente imposible.

Cuando hace falta una propiedad física del residual, la composición se
**renormaliza a 1** antes de calcularla: los moles retenidos ya no están en esa
corriente. Las fracciones que se muestran salen del vector original, sin
renormalizar — son dos usos distintos del mismo dato y conviene no mezclarlos.

### 4.3 La hoja de propiedades por compuesto

El modelo **no calcula calidad de gas**: no hay poder calorífico ni índice de
Wobbe entre sus salidas. Ver `decisiones/0008`.

Pero la tabla de propiedades por compuesto **sigue siendo un input
obligatorio**, porque el cálculo de retenidos usa el peso molecular y el factor
de compresibilidad para pasar de fracción molar a toneladas por día. Sacar esa
hoja del Excel rompe el modelo aunque no se reporte ninguna calidad.

Junto con ella se usan las constantes operativas: presión base, temperatura
base, constante de gas y conversión (vienen del Excel), más la densidad del
aire, 1.225 kg/m³.

> **Una regla que conviene no perder.** Si alguna vez hace falta una propiedad
> de una corriente **mezclada**, se calcula sobre la composición ya mezclada, no
> promediando la propiedad de las corrientes. Vale para cualquier magnitud que
> no sea lineal en la mezcla — el índice de Wobbe era el caso testigo, con la
> raíz de la densidad en el denominador.

## 5. Unidades — fuente frecuente de bugs

Tres escalas conviven y **ninguna conversión salta sola si está mal**:

| Magnitud | Unidad | Nota |
|---|---|---|
| Volúmenes (`Volumen_inyectado`, pools, topes) | unidad de los inputs (≈10³ m³ std/d) | interna |
| Capacidades de ingreso | la misma, ya multiplicadas por `FACTOR_MMm3_A_UNIDAD_VOLUMEN` (=1000) | en pantalla se muestran en MMm³/d |
| Capacidades de evacuación, retenidos, LGN | **tn/d** — sin factor | |
| `lgn_unitario` | tn/d por unidad de volumen | el puente entre las dos |

Regla práctica: antes de escribir una fórmula, chequear en qué escala está cada
operando. El error típico (cargar `25` pensando en MMm³/d donde va `25000`)
estrangula la planta **sin dar ningún error** — o al revés, un factor de más
vuelve un tope infinito (ya pasó: HALLAZGO-0).

> El factor 1000 está marcado como *a confirmar* en el propio config
> (HALLAZGO-4).

Aparte de las tres escalas internas, en pantalla conviven dos formas de mostrar
un volumen: **estándar** y **equivalente a 9.300 kcal/m³**. Es solo
presentación —el modelo trabaja siempre en estándar— pero un número comparado
contra otro en distinta base no significa nada.

## 6. Inyección: de la serie temporal al período

Aguas arriba de la cascada:

1. La inyección viene en **base 9300 kcal/m³** como serie mensual; se pasa a
   condiciones estándar dividiendo por el coeficiente mensual de cada área.
2. Se promedia por año y se cruza con el mapeo área → HUB.
3. La matriz origen × destino reparte la inyección de cada área entre
   gasoductos/plantas, con coeficientes por `(Area, Gasoducto)` y mes.
4. Se elige el **período considerado** y se arman las tablas totales:
   yacimientos (inyección primaria), flujos directos y detalles de HUBs.
5. Se aplica el **ruteo por HUB** (§3.1), que mueve parte del volumen de
   yacimientos a una tabla de hub → planta.

Meses: 1-4 y 11-12 son *verano*, 5-9 *invierno*. El 10 no está clasificado
(pendiente de decisión).

## 7. Escenarios: qué se puede preguntar y qué significa la respuesta

El sandbox responde preguntas contrafácticas sobre la misma inyección. Las
reglas del dominio que aplican:

**Intervenciones sobre gasoductos.** Un ducto no crea ni destruye gas: solo
cambia por dónde sale. Por eso **el volumen que inyecta cada área no cambia
nunca** — toda alta o baja es una redistribución dentro del área, proporcional
a como estaban los destinos. Ese invariante es lo que hace que la comparación
contra la corrida oficial signifique algo: si cambiara el total inyectado, la
diferencia en las plantas ya no sería por el ducto sino por gas que apareció.

Caso sin salida: si un área inyecta *únicamente* al ducto que se da de baja, no
hay a dónde mover su gas. No se inventa un destino: esas filas quedan como
están y se reportan.

Hoy los ductos **no tienen capacidad máxima**, así que una baja no genera
bypass: mueve gas de un lado a otro. Cuando se modele la capacidad, esto
cambia, y ahí las bajas empiezan a tener consecuencias interesantes.

**Plantas nuevas.** Una planta nueva se define por de dónde saca el gas: pool
propio alimentado por un ducto nuevo, otro tren sobre el pool de una planta
existente (mismo gas, cromatografía idéntica), receptora del sobrante de otra
(mezcla), o una corriente propia cargada a mano.

## 8. Preguntas abiertas del dominio

Cosas que el modelo todavía no resuelve (detalle en `HALLAZGOS.md`):

- **Cromatografía de orígenes que no son áreas.** `tty`, `mega`, `bdp`, `vmliq`
  aparecen como origen de flujos directos, pero su composición no puede salir
  de la hoja de premisas: sería el gas residual de esa planta, lo que crea una
  dependencia circular con la cascada. (HALLAZGO-1)
- **Volúmenes negativos.** 17 filas; los grandes (`gpm → GPM: −29.483`)
  sugieren gas que *sale* del nodo modelado con signo, no un error de carga.
  Hay que decidir la semántica. (HALLAZGO-2)
- **Restricción de capacidad de gasoductos** y lógica de evacuación del gas
  residual: anotado como TODO desde el inicio de la migración.
- **TBX El Portón y VM LIQ**: destinos reales con retenidos ya cargados, sin
  planta modelada.
- **Mes 10** sin estación asignada (§6).

## 9. Glosario

| Término | Significado |
|---|---|
| **LGN** | Líquidos de gas natural: etano, propano, butanos, gasolina |
| **TTY** | Complejo Tratayén (pool compartido por TBX y DP) |
| **TBX** | Tren turboexpander |
| **DP / Dew Point** | Tren de punto de rocío |
| **MEGA** | Planta con pool propio de otra composición |
| **PM** | Parada de mantenimiento; su fecha marca el ingreso en servicio de TBX |
| **Ampliación** | Δ de capacidad con fecha de vigencia, que se suma a la base |
| **Pool** | Gas disponible para un tren, con una cromatografía dada |
| **Traspaso** | Pasar volumen entre trenes del mismo pool (sin mezcla) |
| **Derivación** | Pasar gas a un pool de otra composición (con mezcla) |
| **Bypass** | Gas que no se trata en ninguna planta |
| **Bypass estructural** | El que se produce porque las proporciones suman < 1 |
| **Evacuación** | Capacidad de sacar el LGN producido (tn/d). La restricción activa |
| **Cromatografía** | Composición molar del gas por compuesto |
| **RTP** | Retenido en planta: fracción de cada compuesto que queda como líquido |
| **Sufijo** | Discriminante (`Otra`/`Planta`/`TBX`) para áreas con dos cromatografías |
| **HUB** | Punto de agregación de áreas, que mezcla y reparte hacia plantas |
| **Ruteo por HUB** | Que el gas de un área con hub entre por el hub y no directo |
| **9300** | Base calorífica de referencia (kcal/m³) de la inyección cruda |
| **Escenario** | Plantas + intervenciones sobre ductos, guardado como una unidad |
| **Control del sandbox** | Que el sandbox sin tocar dé igual que la corrida oficial |
