# 0008 — Sacar la calidad de gas del modelo

- **Estado:** Vigente
- **Fecha:** v2
- **Afecta a:** `dominio.md` §4.3 · `linaje.md` §3 · `validaciones.md` capas 5 y 6 ·
  `asistente.md` · el explicador · el documento informativo

## Contexto

Hasta v1 el modelo calculaba, para cada corriente, cuatro propiedades derivadas
de la composición: factor de compresibilidad, densidad relativa, poder
calorífico superior e índice de Wobbe. El tablero las reportaba como **calidad
de gas**: PCS e IW de la mezcla inyectada a transporte, entrada y salida por
planta, con líneas de máximo configurables, más las láminas correspondientes
del reporte.

Nunca hubo una referencia contra la cual validar esos números: `validaciones.md`
lo listaba como hueco — se verificaba que las columnas existieran y que los
valores fueran plausibles, no que fueran correctos.

Además, la lectura que le daría sentido —comparar la calidad del gas contra los
límites del sistema de transporte al que se inyecta— depende de una capa que el
modelo **no tiene**: el ruteo del gas residual hacia los gasoductos de
evacuación y la capacidad de esos ductos.

## Decisión

**La calidad de gas sale del modelo.** No se calculan ni se reportan poder
calorífico, índice de Wobbe, densidad relativa ni compresibilidad como salida
del pipeline.

Lo que **no** cambia:

- La **cromatografía sigue siendo central**: es lo que determina la retención de
  cada planta, el LGN producido y la composición del gas residual.
- La hoja de **propiedades por compuesto sigue siendo un input obligatorio**: el
  cálculo de retenidos usa peso molecular y factor de compresibilidad. Sacarla
  del Excel rompe el modelo.

## Alternativas descartadas

- **Dejar el cálculo y sacar sólo los gráficos.** Deja código y columnas que
  nadie mira, que igual hay que mantener cuando cambia una constante, y que la
  próxima persona va a asumir que están validados porque están.
- **Validar los números contra una referencia y quedárselos.** Es trabajo real
  (haría falta un caso conocido del Excel, compuesto por compuesto) para una
  salida que hoy nadie usa para decidir. Si algún día se modela la evacuación,
  se vuelve a discutir.

## Consecuencias

- El modelo responde una pregunta más chica y mejor delimitada: **cuánto gas
  trata cada planta y cuánto LGN produce.** Nada de lo que reporta queda sin
  validar por falta de referencia.
- Desaparece el hueco de validación "propiedades sin referencia".
- **Se pierde** la comparación contra máximos de PCS/IW, que era la única lectura
  de calidad que el tablero ofrecía. Si vuelve a hacer falta, va junto con el
  ruteo a los ductos de evacuación, no sola.
- Hay una regla que sobrevive a la baja y conviene no perder: si alguna vez se
  calcula una propiedad de una corriente mezclada, se hace **sobre la
  composición ya mezclada**, no promediando la propiedad de las corrientes. El
  índice de Wobbe era el caso testigo.

## Limpieza pendiente en el código

- [ ] La función que calcula las propiedades y sus llamadas sobre las tres
      tablas totales
- [ ] Las columnas de propiedades de las tablas totales y de la tabla de
      corrientes de salida
- [ ] Los campos de calidad de la serie temporal (entrada/salida por planta y
      los de la mezcla a transporte)
- [ ] Los paneles de calidad del tab de gráficos y las láminas del reporte PDF
- [ ] La regla del explicador y su lista de nombres candidatos para los máximos
- [ ] Los términos `PCS` e `IW` del glosario del asistente

Los documentos ya están actualizados.
