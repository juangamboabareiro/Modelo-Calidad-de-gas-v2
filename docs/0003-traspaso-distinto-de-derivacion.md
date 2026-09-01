# 0003 — Traspaso y derivación son cosas distintas

- **Estado:** Vigente
- **Fecha:** 2026-08

## Contexto

TBX le pasa gas a Dew Point, y Dew Point le pasa gas a MEGA. En el código las
dos son "una planta le manda el sobrante a otra", y unificarlas dejaría una
sola función de transferencia, más corta.

Físicamente **no son lo mismo**. TBX y DP son dos trenes sobre el mismo pool:
comparten la cromatografía y lo único que se reparte es el volumen. MEGA tiene
un pool propio de otra composición.

## Decisión

Dos operaciones separadas:

| Tramo | Tipo | Cromatografía |
|---|---|---|
| TBX → DP | **traspaso** | idéntica; solo se pasa volumen |
| DP → MEGA | **derivación** | el gas entra a la mezcla de MEGA y la modifica |

El gas derivado de DP a MEGA sale **sin tratar**, así que viaja con la
cromatografía de *entrada* de DP, no con la del residual.

## Alternativas descartadas

- **Una sola operación con mezcla.** Aplicar mezcla en TBX→DP es mezclar el gas
  consigo mismo. Numéricamente casi no se nota (mezclar A con A da A, salvo por
  el ruido), lo que lo vuelve peor: el error es invisible hasta que las
  composiciones se separan.
- **Una sola operación sin mezcla.** Rompe MEGA, que sí recibe gas de otra
  composición.

## Consecuencias

- Hay que saber de qué tipo es cada conexión al crear una planta nueva. Dos
  plantas con el mismo `nombre_pool` son trenes (traspaso); con pool distinto,
  derivación.
- Es la regla que permite sumar un tercer tren sobre TTY sin tocar nada más.
