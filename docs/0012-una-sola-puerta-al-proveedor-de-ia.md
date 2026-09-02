# 0012 — Una sola puerta al proveedor de IA

- **Estado:** Vigente
- **Fecha:** v2 · `AAAA-MM` a completar

## Contexto

La capa opcional de IA del asistente llama a un modelo externo. Ese proveedor
puede tener que cambiar: por política de la empresa, por un endpoint
corporativo, por costo, o para correr un modelo local. Es una decisión que
todavía no está tomada — está pendiente de validación con seguridad de la
información (ver `decisiones/0009`).

Si las llamadas quedan repartidas por la interfaz, cambiar de proveedor es
tocar todos los archivos que preguntan algo.

## Decisión

**Un solo módulo cliente es la única salida a la red.** Concentra la
credencial, el nombre del modelo, el streaming, las herramientas y la
contabilidad de tokens. El resto del código —los tres asistentes, el agente—
no sabe qué proveedor hay del otro lado.

Cambiar de proveedor es tocar ese archivo y nada más.

## Alternativas descartadas

- **Llamar a la API desde cada asistente.** Tres lugares donde configurar lo
  mismo, y tres para migrar.
- **Una capa de abstracción genérica multi-proveedor.** Resolver hoy un
  problema que todavía no existe, con el costo de una interfaz de mínimo común
  denominador que pierde lo específico de cada proveedor.

## Consecuencias

- La decisión de proveedor queda **reversible y localizada**, que es lo que hace
  falta mientras esté pendiente de aprobación.
- Hay dos detalles del modelo actual que el cliente respeta y que no son
  obvios: **no setear los parámetros de muestreo** ni pedir razonamiento
  extendido a mano —ambas cosas dan error— y mandar el bloque de documentación
  **antes** del corte de caché, porque si el corte queda después de los
  resultados de la corrida, cada corrida escribe una entrada nueva y ninguna se
  lee. Al cambiar de modelo, revisar las dos.
- ⚠️ La tabla de precios que alimenta el cartelito de costo vive ahí y es
  **informativa**: la fuente de verdad es la consola del proveedor. Si se cambia
  de modelo y no se actualiza, el número miente sin avisar.
