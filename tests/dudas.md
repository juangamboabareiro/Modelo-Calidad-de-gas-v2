# Dudas abiertas de dominio

Preguntas que el **código no puede responder solo**: hay que confirmarlas con
alguien que conozca la operación. No son bugs (todavía): son puntos donde el
modelo tomó una decisión implícita y no está claro si es la correcta.

Se distinguen de `HALLAZGOS.md`, que documenta problemas ya diagnosticados, y
de `decisiones/`, que registra decisiones ya tomadas. Cuando una duda de acá se
resuelve, **se saca de este archivo** y se convierte en una entrada de
`decisiones/` (si cambió una regla) o en una corrección de `dominio.md` (si sólo
se documentó lo que ya pasaba).

---

## DUDA-1 · Un área que pierde su única salida, ¿deja de inyectar?

**Estado:** abierta
**Detectada por:** `tests/test_gasoductos_conservacion.py::test_baja_sin_salida_deja_las_filas_como_estan`
**Afecta:** `pipeline/gasoductos/intervenciones.py::_baja`

### La situación

Se da de baja un gasoducto por mantenimiento. Para cada área que le inyectaba,
su volumen se reparte entre los otros destinos de esa área. Pero si un área
inyectaba **únicamente** a ese ducto, no hay a dónde mover el gas.

Ejemplo mínimo:

| Area | Gasoducto | Volumen |
|---|---|---|
| Chivo | VMN | 600 |
| Chivo | MEGA | 400 |
| Aislada | MEGA | 100 |

Se da de baja MEGA. Chivo tiene otra salida: sus 400 se mudan a VMN, que pasa a
1000. **Aislada no tiene ninguna.**

### Qué hace hoy el código

La fila de Aislada se borra. El total inyectado baja de 1100 a 1000: esos 100
MMm³/d desaparecen del balance.

El mecanismo es sutil. El bucle tiene una rama explícita para este caso que
preserva la fila con un `continue`, pero cuatro líneas después el filtro que
limpia las aristas del ducto la borra igual:

```python
yac = yac[~_mascara_clave(yac[COL_DESTINO], nombre)].copy()
```

Ese filtro identifica las filas **por gasoducto**, cuando lo que quiere
identificar son las filas **que quedaron en cero**. Para las áreas con otra
salida los dos criterios coinciden (su fila se vació antes). Para las huérfanas
no coinciden, y borra una fila llena creyendo que borra una vacía. O sea: el
`continue` no protege nada.

### Por qué no está claro cuál es el comportamiento correcto

El proyecto afirma tres cosas incompatibles sobre este caso:

| Fuente | Qué dice |
|---|---|
| Docstring de `intervenciones.py` | *"esas filas se dejan como estan y se reportan en el informe"* |
| Invariante declarado del módulo | `sum(Volumen_inyectado del area)` **no cambia nunca** |
| Aviso que emite el informe | *"ese gas queda sin ruta y NO se redistribuye... El total inyectado baja en esa cantidad"* |

Sólo el aviso describe lo que el código realmente hace.

### La pregunta para operaciones

**Cuando un ducto sale de servicio y un área no tiene otra salida, ¿el
yacimiento deja de inyectar?**

- **Si SÍ deja de inyectar** (se cierra el pozo porque no hay dónde entregar):
  el código está bien. Hay que corregir el docstring y el invariante del
  módulo, que hoy prometen otra cosa, y ajustar el test para que verifique que
  la fila desaparece **y** que el informe lo reporta.

- **Si SIGUE inyectando** (el gas se produce y queda varado): el código pierde
  gas en silencio. Hay que preservar las filas huérfanas y decidir aparte qué
  es ese gas en el balance — ¿bypass, gas encerrado, una categoría nueva?

### Por qué importa

El tab sandbox compara sus resultados contra la corrida oficial y muestra el
delta por planta. Si el total inyectado cambia por esta vía, la diferencia que
se ve **ya no es atribuible al ducto**: es gas que apareció o se perdió. Esa es
exactamente la razón por la que el módulo declara el invariante.

### Pendiente de averiguar

- ¿Existe hoy, en los datos reales, alguna área que inyecte a un **único**
  gasoducto? Si no existe ninguna, esto es un bug latente que sólo aparecería
  con un escenario nuevo — igual hay que resolverlo, pero no invalida nada de
  lo ya analizado con el tablero.

### Si la respuesta es "sigue inyectando"

El arreglo es excluir las áreas huérfanas del filtro:

```python
areas_huerfanas = {a for a, _ in huerfanas}
a_borrar = (_mascara_clave(yac[COL_DESTINO], nombre)
            & ~yac[COL_AREA].isin(areas_huerfanas))
yac = yac[~a_borrar].copy()
```

Deja la arista huérfana visible en el mapa, lo cual además es informativo:
muestra dónde quedó gas sin ruta.

---

## Cómo agregar una duda acá

1. **Que sea de dominio, no de código.** Si se puede resolver leyendo el
   código, es un hallazgo, no una duda.
2. **Escribí el caso mínimo** que la expone, con números.
3. **Listá las opciones** y qué implica cada una. Una duda sin opciones es un
   comentario.
4. **Dejá el test.** Si un test la detectó, que quede — marcado `xfail` con un
   `reason` que apunte acá si molesta en verde. El día que se resuelve, el test
   ya está escrito.
