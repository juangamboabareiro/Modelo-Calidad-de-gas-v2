# 0010 — Cada tab se renderiza aislado

- **Estado:** Vigente
- **Fecha:** 2026-08

## Contexto

En Streamlit el script se ejecuta de arriba a abajo en cada interacción. Una
excepción no controlada dentro de un tab **corta el script ahí**: los tabs
siguientes quedan en blanco, sin explicación. El usuario ve un tablero roto y
no tiene forma de saber qué falló.

Y el tablero tiene muchas superficies frágiles por naturaleza: el mapa depende
de coordenadas que pueden faltar, los gráficos de una librería opcional, el
comparador de un Excel de referencia que puede no estar, el sandbox de una
configuración que el usuario acaba de escribir a mano.

Pasó dos veces: un dato faltante en un tab dejó sin ver los cuatro de abajo.

## Decisión

Todo tab se renderiza a través de un envoltorio que atrapa la excepción, la
muestra **adentro de ese tab** con su traceback, y deja que el resto siga.

Un tab en rojo no invalida a los demás.

## Alternativas descartadas

- **Dejar que la excepción propague.** Es el comportamiento por defecto, y el
  peor: un problema chico y localizado se presenta como una falla total.
- **Atrapar y mostrar un mensaje genérico.** Sin el traceback no se puede
  reportar el problema, y el usuario queda con un "algo falló" inútil.
- **Validar todo antes de renderizar.** Habría que anticipar cada modo de falla
  de cada tab. El envoltorio los cubre todos, incluidos los que no se
  anticiparon.

## Consecuencias

- El tablero **degrada en partes** en vez de caer entero, que es lo que se
  quiere de una herramienta de trabajo: si falla el mapa, los números siguen
  ahí.
- ⚠️ **La contracara:** un tab puede estar roto sin que nadie lo note, porque el
  resto anda. Si un tab que se usa poco falla, puede quedar así semanas.
- Un error de configuración del usuario en el sandbox se ve como un error del
  sandbox, no como una caída de la aplicación. Es la diferencia entre "cargué
  algo mal" y "esto no funciona".
