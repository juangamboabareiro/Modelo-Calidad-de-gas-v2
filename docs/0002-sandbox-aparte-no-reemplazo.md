# 0002 — El sandbox corre aparte, no reemplaza al pipeline

- **Estado:** Vigente
- **Fecha:** 2026-08

## Contexto

Para poder preguntarse "¿qué pasa si sumo una planta?" hacía falta una cascada
configurable, con las plantas como dato y no hardcodeadas. Pero el pipeline
existente estaba validado contra el Excel, y cambiarlo obligaba a revalidar
todo de una sola vez.

## Decisión

Un tab aparte con su propia cascada (`registro` + `resolver_cascada`), que
corre sobre **una copia** de las tablas de entrada. El pipeline oficial no se
toca: mismos módulos, mismos números.

Y un **control**: con el registro sin tocar —las tres plantas de siempre, con
los parámetros de la sidebar— el sandbox tiene que dar exactamente lo mismo que
el tab de reparto. El tablero compara las dos tablas planta por planta y
muestra el desvío.

## Alternativas descartadas

- **Migrar el pipeline a la cascada genérica de una.** Revalidación completa
  antes de poder mostrar nada. Se puede hacer *después*, cuando los números del
  sandbox convenzan; es exactamente lo que propone HALLAZGO-6.
- **Un script aparte, fuera del tablero.** Pierde la comparación lado a lado,
  que es la mitad del valor.

## Consecuencias

- **Conviven dos implementaciones de la cascada** y nada garantiza que no
  diverjan salvo `TestEquivalenciaCascadas`. Es deuda consciente: HALLAZGO-6.
- El control es el primer número a mirar. Si da distinto de cero con el registro
  intacto, hay un bug en la capa del sandbox y **ningún escenario armado encima
  vale nada**.
- El sandbox tiene que sembrarse con las capacidades *efectivas* (con las
  ampliaciones vigentes ya aplicadas). Con las crudas, el control daría desvío
  sin haber bug.
