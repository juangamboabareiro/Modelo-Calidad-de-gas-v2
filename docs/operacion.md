# Operación — runbook

Las tareas recurrentes y qué hacer cuando algo rompe. Cómo *usar* el tablero
está en `manual_usuario.md`; qué significa cada dato, en `dominio.md` y
`linaje.md`.

---

## 1. Correr el sistema

```bash
pip install -r requirements.txt

streamlit run app.py     # el tablero
python main.py           # el pipeline sin UI (usa config.PATH_INPUTS)
```

El Excel de inputs va en `datos/inputs.xlsx` o el path de `config.PATH_INPUTS`;
desde el tablero también se puede subir sin tocar el disco.

### Dependencias que se olvidan

Ninguna de estas tumba la aplicación si falta: la función avisa y el resto
sigue. Pero conviene tenerlas.

| Paquete | Sin él |
|---|---|
| `altair` | el tab Graphs no dibuja nada |
| `matplotlib` | no hay reporte PDF ni exportación de gráficos |
| `streamlit-flow-component` ≥ 1.5.0 | no hay canvas visual en el sandbox (el editor de abajo funciona igual) |
| `geopandas` y la geodata | el mapa dibuja sin fondo geográfico |
| `anthropic` | el asistente queda solo con su capa sin IA |

Versión de Streamlit: con **< 1.39**, Enter dentro del formulario ejecuta el
pipeline sin querer (el tablero lo avisa); con **< 1.37** el sandbox pierde los
fragments y se siente notablemente más lento.

---

## 2. Actualizar el Excel de inputs (tarea mensual)

El pipeline es tolerante con encabezados sucios —tildes, espacios, mayúsculas:
los canoniza al cargar— pero **rígido con la estructura**.

### Reglas que no se pueden romper

1. **No renombrar hojas.** Los nombres están hardcodeados en `io_/loaders.py`.
   Renombrar una rompe la carga con error claro; hay un test que lo verifica.
2. **No renombrar las plantas de `Retenidos-RTP`.** El sistema filtra por los
   strings literales `TBX`, `Dew point` y `TBX MEGA`. Renombrarlos deja esa
   planta con **retención cero, sin ningún error**. Es la trampa más silenciosa
   del sistema.
3. **No cambiar el HUB de un área a la ligera.** En v2, el HUB de
   `Plantas-Yacimientos` decide si el área inyecta directo a la planta o entra
   por el ruteo de hubs. Cambiarlo cambia por dónde entra el gas.
4. **Cuidado con `Sufijos-Planta`**: la hoja no tiene fila de encabezado real y
   la clave se corta por el *primer guion*. No agregar áreas con guion en el
   nombre ni "arreglar" el encabezado sin tocar el loader.
5. **`Premisas-Areas`**: cada fila debe sumar 1. Un área duplicada con
   cromatografías distintas: se toma la primera, igual que el VLOOKUP original
   (`decisiones/0007`), pero es un dato a corregir en origen.
6. **`Cromas-HUBs`**: la clave del hub va en una columna `HUB` o `Area`,
   indistinto. Fila a medio llenar (suma < 0,5) → se ignora y el hub cae a
   mezcla volumétrica, con aviso. Hub cargado dos veces → se toma el primero.
7. **`Detalles-HUBs`**: de acá sale el reparto de cada hub. Se usa como
   **proporción**, no como volumen absoluto, así que el balance cierra aunque
   la hoja traiga volúmenes de otro momento.
8. **No sacar la hoja de propiedades por compuesto** aunque no se reporte
   calidad de gas: el cálculo de retenidos la necesita.

### Checklist después de cargar el Excel nuevo

- [ ] `▶️ Ejecutar pipeline` corre sin error.
- [ ] **Desvío de balance** en verde.
- [ ] **Control del sandbox en cero** con el registro sin tocar.
- [ ] Revisar el **panel de diagnósticos** comparando contra el mes pasado.
      Lo que importa no es que haya avisos —siempre hay— sino que aparezca uno
      **nuevo**. En particular:
  - [ ] ¿cambió la cantidad de filas sin cromatografía?
  - [ ] ¿algún hub pasó de tener croma cargada a usar mezcla volumétrica?
  - [ ] ¿apareció un hub sin reparto que antes ruteaba?
  - [ ] ¿cambió la cantidad de áreas sin destino en la matriz?
- [ ] `pytest` (la parte de integración usa `datos/inputs.xlsx`).
- [ ] Si hubo cambios de fórmulas del lado Excel: comparar en el tab **Tablas
      totales** contra el Excel de referencia.

Un aviso nuevo que no entendés y no está en `HALLAZGOS.md` merece investigarse
y anotarse ahí, aunque no lo resuelvas. Media hora ahora, tres horas dentro de
seis meses.

### Datos auxiliares (no mensuales)

| Archivo | Qué es | Si falta |
|---|---|---|
| `datos/alias_areas.csv` | equivalencias de nombres de área | hoy **no está en el repo**: áreas con dos nombres no se unen |
| `datos/geo_nodos.csv` | coordenadas de los nodos del mapa | esos nodos no se dibujan; el tab lista cuáles |
| `datos/geo/concesiones.geojson` | fondo geográfico | se genera con `scripts/preparar_geo.py` (una vez, sin red) |
| `escenarios/*.json` | escenarios prearmados | el selector queda vacío |

---

## 3. Cuando algo rompe

### "El pipeline falló" al ejecutar

Leer el mensaje: los loaders fallan explícito. Causas típicas, en orden:

1. Una hoja renombrada o faltante (§2, regla 1).
2. El período pedido no existe en las columnas de meses del Excel.
3. Falta una columna en la hoja de constantes de gas — eso explota al importar,
   antes de cualquier otra cosa.
4. Un formato de fecha inválido en la sidebar (avisa y usa el default, pero si
   el default tampoco existe en el Excel, falla).

### Los parámetros de la sidebar "no hacen nada"

Si un módulo nuevo lee `config` a nivel de módulo y no está en
`_actualizar_config_y_recargar` de `app.py`, la sidebar deja de afectarlo **en
silencio**. Es el hueco de validación #1 (`decisiones/0004`). Sospechalo cuando
cambiás una capacidad y el resultado no se mueve.

### Resultados absurdos sin ningún error

Casi siempre **unidades**: evacuación en tn/d, ingreso en MMm³/d, y el factor
1000 entre la unidad interna y MMm³/d. Cargar `25` donde va `25000` estrangula
la planta; un factor de más vuelve un tope infinito (HALLAZGO-0).

### El volumen de un área "se movió" de planta

Es el **ruteo por HUB**: si el área tiene hub, su gas figura contra el hub en
`Total HUBs (ruteo)` y no directo contra la planta. El total inyectado por el
área no cambia.

### El desvío de balance no cierra

El resultado no es confiable, punto. Antes de mirar el modelo, mirar los datos:
volúmenes negativos (HALLAZGO-2) y filas sin cromatografía son las causas
conocidas.

### El control del sandbox da distinto de cero

Hay un bug en la capa del sandbox, o el registro se sembró con capacidades
distintas de las de la corrida oficial. Ningún escenario armado encima vale
hasta resolverlo.

### Un tab en rojo

Los tabs están aislados: el que falla muestra su traceback adentro y los demás
siguen. Copiar el traceback tal cual; no hace falta reiniciar.

### La serie temporal falla en algunos meses

Graphs lista los períodos que fallaron con su error y grafica el resto. Suele
ser un dato faltante de ese mes.

### El sandbox quedó en un estado raro

**Restablecer** lo devuelve a recién abierto. Si el escenario vale algo,
**Descargar simulación** primero.

### El canvas visual no aparece

Falta `streamlit-flow-component` ≥ 1.5.0. Las versiones anteriores no traen el
objeto de estado que sincroniza el canvas con el registro. El editor de abajo
funciona igual.

### El asistente con IA no responde o cuesta de más

Ver `asistente.md`. Lo primero es correr la verificación de credencial desde
línea de comandos, que separa "la credencial está mal" de "el tab tiene un
bug". Lo segundo: la segunda pregunta seguida tiene que decir **"desde caché"**;
si no lo dice, el caching se rompió y cada pregunta paga la documentación
entera.

---

## 4. Deploy

- Deploy = push + redeploy. Todo lo que necesite binarios del lado del cliente
  se evitó a propósito: por eso el reporte PDF se dibuja server-side.
- Los secretos (credencial de IA) van en el archivo de secrets, que está en
  `.gitignore`. **Nunca al repo.**
- Al agregar una dependencia: `requirements.txt` y redeploy.

---

## 5. Mantenimiento del repo

Antes de dar un cambio por terminado:

```bash
pytest -m "not integracion"             # verde sin excepción
pytest                                  # si hay Excel a mano
python tools/mapa_modulos.py --check    # el mapa de módulos no quedó viejo
```

- `docs/mapa.md` **nunca se edita a mano**: `python tools/mapa_modulos.py
  --escribir`. El `--check` sale con código 1 si quedó viejo, así que va en CI.
- Cambio de regla del modelo → test + ADR en `docs/decisiones/`.
- Algo que contradice `dominio.md` o `linaje.md` → se corrige en el mismo
  commit.
- Los XFAIL son a propósito (HALLAZGOS 1 y 2). No borrarlos: avisan solos el
  día que el dato de origen se corrija.

### Tareas de higiene pendientes

De `HALLAZGOS.md`, las que son puro trabajo sin decisión de por medio:

- `main.py` tiene código exploratorio al final y sigue usando los modeladores
  legacy (menores 7 y 8).
- Hay módulos de planta vacíos y funciones que no importa nadie (menores 9 y 10).
- Hay outputs versionados con doble extensión (menor 13).
- `arq.md`, si todavía existe, contiene un borrador viejo con una estructura de
  carpetas que ya no es la real: confunde más de lo que ayuda (menor 11).
