# 0007 — Replicar el Excel donde hay reportes ya emitidos

- **Estado:** Vigente
- **Fecha:** 2026-07

## Contexto

Al migrar aparecen lugares donde el Excel hace algo discutible y Python podría
hacerlo "mejor". El ejemplo típico: un área cargada dos veces con
cromatografías distintas. El `VLOOKUP` original se queda con la primera.

## Decisión

Cuando hay reportes históricos ya emitidos con el Excel, **se replica el
comportamiento del Excel** y se documenta la discrepancia, en lugar de
corregirla en silencio.

Aplicado hoy a: la premisa duplicada (se toma la primera) y las fórmulas de
conversión que se copiaron tal cual.

## Alternativas descartadas

- **Corregir y seguir.** El modelo nuevo daría números distintos del histórico
  sin que nadie sepa por qué, y la migración perdería su criterio de
  aceptación: "¿da lo mismo que el Excel?".
- **Corregir con un flag.** Duplica caminos de código para un problema que en
  realidad hay que arreglar **en el dato de origen**.

## Consecuencias

- El criterio de validación de la migración se mantiene limpio: cualquier
  diferencia contra el Excel es un bug, no una mejora.
- Cada replicación deliberada tiene que quedar anotada en `linaje.md` §5 y, si
  tiene impacto, en `HALLAZGOS.md`. Un dato sucio replicado que nadie documentó
  es indistinguible de un bug.
- El día que se corrija el dato de origen, se saca la replicación y punto.
