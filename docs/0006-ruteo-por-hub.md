# 0006 — El gas de un área con HUB entra por el hub

- **Estado:** Vigente
- **Fecha:** v2

## Contexto

El armado original conectaba cada área directo a su planta destino: toda fila
con `Gasoducto == planta` entraba al pool con su cromatografía individual.

Físicamente solo inyectan directo las áreas **sin** hub. Las que comparten un
HUB mandan su gas primero al hub, que lo mezcla y lo deriva a las plantas.

La diferencia numérica aparece cuando un hub reparte entre varios destinos:
cada planta debe recibir la composición **del hub**, no la de cada área por
separado, y el reparto es una decisión del hub, no de cada área.

## Decisión

Un paso de ruteo que, antes de armar los pools:

1. separa las rutas área → planta en directas (sin hub) y vía hub;
2. junta el volumen que le llega a cada hub y decide su composición de salida:
   la premisa cargada en `Cromas-HUBs` si existe, y si no la **mezcla
   volumétrica** de las áreas que aportan, con aviso;
3. deriva ese volumen a las plantas según el reparto de `Detalles-HUBs`, usado
   como **proporción** y no como volumen absoluto;
4. devuelve `Total Yacimientos` sin las rutas ruteadas y una tabla nueva
   `Total HUBs (ruteo)`.

Las rutas área → gasoducto no se tocan: el hub solo intermedia la entrega a
plantas.

**Regla de seguridad:** un hub sin renglón de reparto utilizable deja a sus
áreas inyectando directo, como antes, con aviso.

## Alternativas descartadas

- **Seguir conectando área → planta.** Es el comportamiento anterior, y da mal
  apenas un hub reparte entre dos destinos.
- **Exigir `Cromas-HUBs` para todo hub.** Bloquearía la corrida por un dato que
  todavía no está cargado. La mezcla volumétrica es una aproximación razonable
  y se avisa cuándo se usa.
- **Repartir un hub sin reparto entre todas las plantas por igual.** Inventar.

## Consecuencias

- ⚠️ El ruteo **pisa** `Total Yacimientos`. Todo lo que consuma esa tabla tiene
  que ver la versión de después, o el volumen se cuenta dos veces.
- La validación de orígenes contra la matriz de inyecciones necesita traducir
  `area → hub`; sin eso descarta filas legítimas.
- El caso de control para validar la migración: un hub que manda el 100% a una
  sola planta y usa mezcla volumétrica **no cambia** el gas de entrada, porque
  la mezcla es lineal.
- La hoja `Plantas-Yacimientos` pasa a ser mucho más sensible: el HUB asignado
  ahí decide por dónde entra el gas.
