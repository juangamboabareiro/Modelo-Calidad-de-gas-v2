"""
Verifica la capa de IA del asistente SIN levantar Streamlit.
============================================================

Sirve para separar dos problemas que desde la app se ven igual ("el chat no
anda"): que la credencial/el modelo esten mal, o que el tab tenga un bug.

    export ANTHROPIC_API_KEY=sk-ant-...
    python tools/probar_asistente.py

Que hace, en orden:

  1. Chequea que este la SDK y la credencial.
  2. Carga los docs y reporta cuanto ocupan.
  3. Hace DOS preguntas iguales al bot de documentacion. La primera escribe el
     cache, la segunda tiene que leerlo: si la segunda no muestra tokens
     "desde cache", el caching no esta funcionando y cada pregunta va a costar
     10x de mas.
  4. Imprime el costo estimado de las dos llamadas.

No toca el sandbox ni el estado de la app: son llamadas sueltas a la API.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Para poder correrlo como `python tools/probar_asistente.py` desde la raiz.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia.cliente import (  # noqa: E402
    hay_credencial, modelo_configurado, completar, leer_uso, resumen_uso,
    costo_estimado, PRECIOS,
)
from ia.contexto import cargar_docs, bloques_system  # noqa: E402

PREGUNTA = "En una sola frase: ¿qué es la cascada del pool de gas?"


def main() -> int:
    print("== Asistente: verificación de la capa IA ==\n")

    try:
        import anthropic  # noqa: F401
    except ImportError:
        print("✗ Falta la SDK. `pip install anthropic` (y agregala a "
              "requirements.txt).")
        return 1
    print("✓ SDK `anthropic` instalada")

    if not hay_credencial():
        print("✗ No hay ANTHROPIC_API_KEY (ni en el entorno ni en secrets.toml).")
        return 1
    modelo = modelo_configurado()
    print(f"✓ Credencial encontrada · modelo `{modelo}`")
    if modelo not in PRECIOS:
        print(f"  ⚠ No tengo precios cargados para `{modelo}`: el costo "
              "estimado de la UI va a salir vacío (ver PRECIOS en ia/cliente.py).")

    docs, avisos = cargar_docs()
    for aviso in avisos:
        print(f"  ⚠ {aviso}")
    if not docs:
        print("✗ No se cargó documentación: revisá que exista `docs/` con .md.")
        return 1
    # Regla gruesa: ~4 caracteres por token. Alcanza para saber si estamos
    # arriba del mínimo cacheable (1.024 tokens en Sonnet 5).
    aprox = len(docs) // 4
    print(f"✓ Documentación: {len(docs):,} caracteres (~{aprox:,} tokens)")
    if aprox < 1024:
        print("  ⚠ Por debajo del mínimo cacheable: el caching no se va a "
              "activar. No es un error, pero cada pregunta cuesta el input "
              "completo.")

    system = bloques_system("docs", docs)
    mensajes = [{"role": "user", "content": PREGUNTA}]
    usos = []

    for intento in (1, 2):
        etiqueta = "1ª llamada (escribe caché)" if intento == 1 else \
                   "2ª llamada (debería leer caché)"
        print(f"\n-- {etiqueta} --")
        t0 = time.time()
        try:
            respuesta = completar(system, mensajes, max_tokens=300)
        except Exception as e:  # noqa: BLE001
            print(f"✗ Falló la llamada: {type(e).__name__}: {e}")
            return 1
        segundos = time.time() - t0

        uso = leer_uso(getattr(respuesta, "usage", None))
        usos.append(uso)
        texto = "\n".join(b.text for b in respuesta.content
                          if getattr(b, "type", "") == "text").strip()
        print(f"   {segundos:.1f}s · {resumen_uso(uso, modelo)}")
        print(f"   → {texto[:220]}")

        # El cache tarda un instante en quedar disponible tras la 1ª respuesta.
        if intento == 1:
            time.sleep(2)

    leido = usos[1].get("cache_leido", 0)
    if leido:
        print(f"\n✓ Caching activo: la 2ª llamada leyó {leido:,} tokens del "
              "caché en vez de reprocesarlos.")
    else:
        print("\n⚠ La 2ª llamada NO leyó del caché. Posibles causas: la "
              "documentación no llega al mínimo del modelo, pasaron más de 5 "
              "minutos entre llamadas, o el bloque de docs cambió entre una y "
              "otra.")

    total = sum(costo_estimado(u, modelo) or 0 for u in usos)
    print(f"\nCosto estimado de esta prueba: ~US$ {total:.4f}")
    print("Listo. Si todo dio ✓, el tab Asistente va a funcionar igual.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
