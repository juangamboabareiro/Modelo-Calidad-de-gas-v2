# 0011 — Las cromatografías de planta van en un archivo aparte

- **Estado:** Vigente
- **Fecha:** 2026-08

## Contexto

Para armar un escenario a veces hace falta sumarle al pool de una planta una
corriente que no existe en los inputs: gas de un área nueva, una importación,
una corriente de prueba. El lugar "natural" sería agregar filas al Excel de
inputs.

Pero el Excel es el **input oficial del modelo**: se actualiza todos los meses,
lo mantiene otra persona, y es la base contra la que se valida la migración.
Meterle filas hipotéticas lo contamina.

## Decisión

Las corrientes extra se cargan por un **archivo aparte**, subido desde el
tablero: `Planta`, `Origen`, `Volumen` y una columna por compuesto. Se suman al
pool antes de calcular la mezcla, así que pesan igual que el gas que llega por
ducto.

El archivo es **opcional por diseño**: sin él, el modelo corre igual.

Tolerancias, en el mismo espíritu de avisar y seguir: si la suma molar da ~100
se asume porcentaje y se divide por 100; si no da 1, se normaliza con aviso; un
volumen no numérico o ≤ 0 descarta la fila indicando cuál.

## Alternativas descartadas

- **Agregar filas al `inputs.xlsx`.** Mezcla dato oficial con hipótesis, y la
  próxima actualización mensual las borra sin avisar.
- **Cargarlas a mano en la pantalla, compuesto por compuesto.** Son 14 valores
  por corriente. Nadie lo haría dos veces.
- **Meterlas dentro del `escenario.json`.** Tentador —serían parte de la
  pregunta— pero ese archivo se edita desde la pantalla y una cromatografía es
  un dato tabular que se arma en Excel. Se mantienen separados a propósito.

## Consecuencias

- El input oficial queda limpio: cualquier diferencia contra el Excel sigue
  siendo un bug y no "una fila que alguien agregó para probar".
- ⚠️ Un escenario completo puede requerir **dos archivos** (el `.json` y el de
  cromatografías) y nada los ata. Si compartís uno sin el otro, el escenario no
  se reproduce igual. Por eso la descarga de la simulación empaqueta todo junto
  con un LEEME.
- Hay una plantilla generable, porque el formato no se puede adivinar y un
  archivo mal armado se descarta fila por fila.
