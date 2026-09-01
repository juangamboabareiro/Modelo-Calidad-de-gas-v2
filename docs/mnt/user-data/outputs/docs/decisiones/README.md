# Decisiones de arquitectura (ADRs)

Un archivo por decisión de diseño **no obvia**. El objetivo es que dentro de
seis meses nadie —incluido vos— tenga que re-derivar por qué algo se hizo así,
ni "arreglar" a mano algo que estaba bien puesto.

## Formato

```
NNNN-titulo-en-kebab-case.md

# NNNN — Título
- Estado, fecha
- Contexto: qué problema había
- Decisión: qué se hizo
- Alternativas descartadas: y por qué
- Consecuencias: lo bueno y lo que hay que bancarse
```

## Reglas

1. **Append-only.** Un ADR no se edita para cambiar la decisión: se escribe uno
   nuevo que diga "reemplaza a NNNN", y el viejo se marca `Superada por NNNN`.
   Corregir una errata sí, obviamente.
2. **Se escribe cuando se decide**, no después. Un ADR reconstruido a posteriori
   pierde justo lo que vale: las alternativas que en su momento parecían
   razonables.
3. **Si no hubo alternativa, no es un ADR.** Documentar "usamos pandas" no le
   sirve a nadie. Documentar "no unificamos traspaso y derivación aunque el
   código quedaría más corto" sí.

## Índice

| # | Decisión | Estado |
|---|---|---|
| [0001](0001-cromatografia-por-ruta-con-fallback.md) | Cromatografía por `(Area, Gasoducto)` con fallback `Area+Sufijo` | Vigente |
| [0002](0002-sandbox-aparte-no-reemplazo.md) | El sandbox corre aparte, no reemplaza al pipeline | Vigente |
| [0003](0003-traspaso-distinto-de-derivacion.md) | Traspaso y derivación son cosas distintas | Vigente |
| [0004](0004-constantes-al-importar-y-reload.md) | Constantes leídas al importar, y el reload de `config` | Vigente, con deuda |
| [0005](0005-intervenciones-redistribucion-proporcional.md) | Las intervenciones sobre ductos redistribuyen, no crean gas | Vigente |
| [0006](0006-ruteo-por-hub.md) | El gas de un área con HUB entra por el hub | Vigente |
| [0007](0007-replicar-el-excel-donde-hay-historico.md) | Replicar el Excel donde hay reportes ya emitidos | Vigente |
| [0008](0008-sacar-calidad-de-gas.md) | Sacar calidad de gas de los productos del tablero | **A confirmar** |
| [0009](0009-asistente-hibrido-dos-capas.md) | El asistente en dos capas, la de abajo sin IA | Vigente |
