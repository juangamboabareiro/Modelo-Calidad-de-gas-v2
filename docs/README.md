# Índice de la documentación

Mapa de qué documento responde qué pregunta, y las reglas para que no se
pudra. La presentación del proyecto está en el `README.md` de la raíz.

---

## La documentación, en tres capas

Cada documento existe para **una** audiencia y responde **una** pregunta. Si no
sabés dónde escribir algo, buscá la pregunta que responde.

### Capa 1 — Entrada

| Documento | Para quién | Pregunta que responde |
|---|---|---|
| `README.md` (raíz) | cualquiera | qué es el proyecto, qué hace, cómo se corre |
| `docs/README.md` (este) | quien va a leer o escribir documentación | qué documento responde qué |
| `CLAUDE.md` | LLMs y agentes | qué tengo que saber antes de tocar nada |

### Capa 2 — Uso y operación (no hace falta leer código)

| Documento | Pregunta que responde |
|---|---|
| `docs/manual_usuario.md` | cómo uso el tablero: sidebar, tabs, sandbox, escenarios |
| `docs/operacion.md` | cómo actualizo el Excel mensual, qué hago si algo rompe, cómo deployo |
| `docs/asistente.md` | cómo funciona el tab Asistente y cómo se enciende la capa de IA |
| `docs/flujo_pipeline_gas.html` | **el explicativo del pipeline traducido a Excel.** El mejor punto de entrada para alguien que viene del modelo viejo: cada paso con su equivalente en BUSCARV, tabla dinámica o Autofiltro |

### Capa 3 — Conocimiento del sistema (para tocar el código)

| Documento | Pregunta que responde |
|---|---|
| `docs/dominio.md` | **qué significan** los números. No habla de Python |
| `docs/linaje.md` | **de dónde viene** cada dato, celda por celda, y a dónde va |
| `docs/mapa.md` | **dónde está** el código (generado, no editar a mano) |
| `docs/decisiones/` | **por qué** algo está hecho así (un ADR por decisión) |
| `docs/validaciones.md` | qué se chequea, en qué capa, y qué **no** está cubierto |
| `docs/HALLAZGOS.md` | problemas conocidos de datos y config, numerados y verificables |
| `docs/bitacora.md` | diario de trabajo de la migración. Contexto histórico, **no** fuente de verdad |

---

## Las cuatro preguntas, y su documento

Es la regla que evita que la documentación se solape:

```
¿QUÉ SIGNIFICA?  → dominio.md      (el modelo físico)
¿DE DÓNDE VIENE? → linaje.md       (el dato, desde la celda)
¿DÓNDE ESTÁ?     → mapa.md         (el código; generado)
¿POR QUÉ ASÍ?    → decisiones/     (un ADR, append-only)
```

Lo que no cae en ninguna de las cuatro es, casi siempre, **un problema**
(`HALLAZGOS.md`) o **un chequeo** (`validaciones.md`). Nada se duplica entre
documentos: se linkea.

---

## Reglas de mantenimiento

1. **Lo generable se genera.** `docs/mapa.md` nunca se edita a mano.
   `python tools/mapa_modulos.py --check` sale con código 1 si quedó viejo,
   así que va en CI.
2. **Lo demás se actualiza en el mismo commit** que el cambio que lo invalida.
   Un cambio de regla del modelo lleva además su test y su ADR.
3. **Un hallazgo se cierra, no se borra.** Cuando se resuelve, se marca
   `RESUELTO` con la fecha y el commit. El histórico es la mitad del valor.
4. **Un ADR no se edita: se supera.** Si una decisión cambia, se escribe una
   nueva que diga "reemplaza a `NNNN`" y la vieja se marca como superada.

---

## Estado de la documentación

| Documento | Estado |
|---|---|
| `dominio.md` | al día con v2 |
| `linaje.md` | al día con v2. Absorbió a `data_dictionary.md`, que se eliminó |
| `decisiones/` | ADRs 0001–0008 escritos; antes era una plantilla vacía |
| `validaciones.md` | al día con v2 |
| `HALLAZGOS.md` | 0–6 abiertos + menores. Revisar cuáles pudo haber cerrado v2 |
| `manual_usuario.md`, `operacion.md` | nuevos |
| `flujo_pipeline_gas.html` | al día con v2. **Es un snapshot autocontenido**: duplica a propósito partes de `dominio.md`, `linaje.md` y `validaciones.md`. Ante una diferencia, gana el `.md` |
| `mapa.md` | generado el 2026-08-27 — **regenerar**, es anterior a v2 |
| `bitacora.md` | ex `changelog.md`. Congelado en 19/8/26 |

**Archivos eliminados y por qué:**

- `data_dictionary.md` — plantilla sin llenar, con placeholders
  (`[Nombre_Sheet_1]`, `[ej: B3:H120]`) y dos diagramas Mermaid a medio hacer.
  Todo lo que prometía ya está en `linaje.md`, relevado sobre datos reales.
  Mantener dos documentos para lo mismo garantiza que uno mienta.
- `decisions.md` — plantilla sin llenar cuyas entradas de ejemplo hablaban de
  sheets que no existen acá. Reemplazada por `docs/decisiones/`, un archivo por
  decisión, que es lo que `CLAUDE.md` ya venía referenciando.
