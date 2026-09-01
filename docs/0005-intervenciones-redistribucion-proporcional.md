# 0005 — Las intervenciones sobre ductos redistribuyen, no crean gas

- **Estado:** Vigente
- **Fecha:** 2026-08

## Contexto

El sandbox permite abrir un gasoducto nuevo o sacar uno de servicio. La
pregunta es qué pasa con el volumen: ¿el ducto nuevo *agrega* gas al sistema, o
*mueve* gas que ya estaba?

## Decisión

**El volumen que inyecta cada área no cambia nunca.** Un ducto no crea ni
destruye gas: solo cambia por dónde sale. Toda intervención es una
redistribución dentro del área, proporcional a como estaban los destinos.

- **Alta.** El área inyecta `T` repartido entre destinos. Se abre un ducto con
  volumen `V ≤ T`; el resto `R = T − V` se reparte entre los destinos que ya
  estaban, en la misma proporción. Se agregan dos filas, como un ducto real:
  `Area → ducto` (yacimientos) y `ducto → Planta` (flujos directos).
- **Baja.** Para cada área que le inyectaba, su volumen se reparte entre los
  otros destinos de esa área, proporcional a como estaban.
- **Caso sin salida.** Si un área inyecta *únicamente* al ducto que se da de
  baja, sus filas quedan como están y se reportan.

## Alternativas descartadas

- **Que el ducto nuevo sume volumen.** Rompe la comparación contra la corrida
  oficial: la diferencia que se ve en las plantas ya no sería por el ducto sino
  por gas que apareció de la nada.
- **Repartir por default el gas de un área sin salida.** Sería decidir por el
  usuario algo que el modelo no sabe.

## Consecuencias

- La comparación contra la corrida oficial significa algo, que es todo el punto
  del sandbox.
- Como los ductos **todavía no tienen capacidad máxima**, una baja no genera
  bypass: mueve gas de un lado a otro. Cuando se modele la capacidad, esto
  cambia y las bajas empiezan a tener consecuencias interesantes.
- Las columnas `Vol_<compuesto>` son extensivas (dependen del volumen), así que
  se recalculan al final de toda intervención. Si no, quedan desincronizadas y
  nadie lo nota.
