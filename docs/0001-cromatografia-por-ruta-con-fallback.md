# 0001 — Cromatografía por `(Area, Gasoducto)` con fallback `Area + Sufijo`

- **Estado:** Vigente, con una etapa inactiva
- **Fecha:** 2026-07

## Contexto

Cada fila de inyección necesita una composición molar para poder calcular
cuánto LGN retiene la planta. El merge natural es por `Area`, y así arrancó.

El problema apareció con **Fortín de Piedra**, que tiene dos mediciones
distintas: una para el gas que va por planta (CO Paralelo, NEUII, GPM) y otra
para el que no (VMS, YPF-RDM, MEGA). Con un merge por `Area` se elegía una al
azar, y elegir mal le sacaba **34,7% del C3+** al pool de MEGA alimentado por
áreas. Sin ningún error: el número salía, y salía mal.

## Decisión

Búsqueda en dos etapas:

1. **Por ruta** `(Area, Gasoducto)` — para premisas específicas de un destino.
2. **Fallback** por clave `Area + Sufijo`, donde el sufijo (`Otra` / `Planta` /
   `TBX`) desambigua las áreas con más de una cromatografía.

## Alternativas descartadas

- **Merge por `Area` a secas.** Es el bug descripto arriba.
- **Duplicar el área con nombres distintos en las hojas** (`Fortín de
  Piedra (planta)`). Ensucia el catálogo de áreas, rompe los cruces con el
  resto de las hojas y no escala a un área con tres mediciones.
- **Elegir la composición más conservadora.** Inventar un dato que nadie midió.

## Consecuencias

- Hay dos rutas de código y hay que saber cuál matcheó: el pipeline lo reporta
  (`N por ruta, M por clave, K sin resolver`).
- Hoy **la primera etapa no matchea ni una fila** porque la columna de destino
  de las premisas está vacía: todo cae al fallback. Es rama muerta hasta que se
  llene esa columna (HALLAZGO-5).
- La clave concatenada se corta por el primer guion, lo que se rompe si un área
  llega a tener guion en el nombre. `validar_sufijos` lo chequea.

## Decisión pendiente

Si la columna de destino de las premisas no se va a llenar nunca, la primera
etapa se puede borrar y esto queda en una sola búsqueda por `Area + Sufijo`.
Eso **reemplazaría** este ADR, y hay que escribir el que lo reemplace: la
desambiguación por sufijo seguiría siendo necesaria igual, así que el problema
de Fortín de Piedra no vuelve.

Mientras no se decida, la etapa por ruta queda como rama muerta que ningún test
de datos reales puede cubrir.
