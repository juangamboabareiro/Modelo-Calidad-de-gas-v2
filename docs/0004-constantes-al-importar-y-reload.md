# 0004 — Constantes leídas al importar, y el reload de `config`

- **Estado:** Vigente, con deuda reconocida
- **Fecha:** 2026-08

## Contexto

Las constantes de gas (presión base, temperatura base, constante de gas,
conversión) salen del Excel. Se leen **al importar** `domain/ctes_gas.py`, a
nivel de módulo, para que el resto del código las use como constantes normales
y no tenga que pasarlas por parámetro en cada llamada.

El tablero, además, permite cambiar parámetros desde la sidebar, y varios
módulos leen `config` a nivel de módulo. Un `import` ya ocurrido no ve el
cambio.

## Decisión

- Las constantes se leen al importar, aceptando el costo.
- Los cambios de la sidebar se propagan con un **reload explícito** de los
  módulos que leen `config` a nivel de módulo
  (`_actualizar_config_y_recargar` en `app.py`).
- `tools/mapa_modulos.py` **genera automáticamente la lista** de esos módulos
  leyendo el árbol con `ast`, y la publica en `mapa.md`. Es la lista que hay
  que mantener sincronizada.

## Alternativas descartadas

- **Pasar las constantes por parámetro en todo el pipeline.** Más correcto y
  mucho más ruidoso: son cuatro valores que atraviesan diez capas.
- **Un objeto de configuración inyectado.** Es la solución buena a futuro;
  hoy implica tocar todas las firmas.

## Consecuencias

- ⚠️ **Un módulo nuevo que lea `config` a nivel de módulo y no se agregue al
  reload deja de responder a la sidebar, en silencio.** Es el hueco de
  validación #1: ningún test lo cubre, porque requiere que `ejecutar_pipeline`
  salga de `app.py`.
- Si falta una columna en la hoja de constantes, el import del paquete explota.
  Es preferible a correr con un valor por defecto inventado.
- Cambiar el path de inputs después del primer import no relee nada sin
  `importlib.reload`.
