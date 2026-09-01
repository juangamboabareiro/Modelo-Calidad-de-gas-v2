# 0009 — El asistente en dos capas, la de abajo sin IA

- **Estado:** Vigente
- **Fecha:** v2

## Contexto

El tablero lo va a usar gente ajena al proyecto, que pregunta sobre todo dos
cosas: "qué es esto" y "por qué da esto". Un chat con un modelo resuelve las
dos, pero introduce una dependencia (credencial, red, costo) y un riesgo
(alucinar sobre números que después alguien usa para decidir).

## Decisión

Cada asistente en **dos capas**:

- **Abajo, sin IA y siempre disponible:** un buscador sobre `docs/` que muestra
  fragmentos reales (no genera texto, así que no puede inventar), un glosario
  escrito a mano, y un explicador determinista de la corrida — reglas con sus
  umbrales, que devuelven hallazgos con los números a la vista y en qué tab
  mirarlos.
- **Arriba, opcional:** chat y agente, que se encienden solos si hay
  credencial. Aportan lo que la capa de abajo no puede: reformular una pregunta
  mal planteada, cruzar dos documentos, operar el sandbox en lenguaje natural.

## Alternativas descartadas

- **Solo IA.** El tablero no serviría sin credencial, y las preguntas más
  frecuentes se responderían de la forma menos confiable.
- **Solo determinista.** No cubre la pregunta mal planteada, que es la típica
  del recién llegado.

## Consecuencias

- El tablero sirve desde el día uno; habilitar la IA después es cambiar un
  secreto, no reescribir código.
- ⚠️ **Las capas de IA envían números de la corrida a un tercero.** Hay que
  validarlo con seguridad de la información antes de usarlo con datos reales.
  Si no se aprueba, la capa de abajo queda como está y no se pierde nada.
- El agente opera el **mismo estado que la UI**, así que lo que arma queda
  visible, editable y deshacible. No hay un segundo camino de ejecución.
- Mantener dos capas cuesta: una regla nueva del explicador y un término nuevo
  del glosario son trabajo manual. Es el precio de no alucinar.
