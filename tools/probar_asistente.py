"""
Verifica la capa de IA del asistente SIN levantar Streamlit.
============================================================

Sirve para separar dos problemas que desde la app se ven igual ("el chat no
anda"): que la credencial/el modelo esten mal, o que el tab tenga un bug.

    # Linux / macOS
    export GEMINI_API_KEY=AIza...          # o ANTHROPIC_API_KEY=sk-ant-...
    python tools/probar_asistente.py
    python tools/probar_asistente.py --modelos   # que modelos tiene la key

    # Windows PowerShell
    $env:GEMINI_API_KEY = "AIza..."
    python tools\\probar_asistente.py

Se puede llamar desde cualquier carpeta: el script se para solo en la raiz del
repo antes de hacer nada. Importa, porque tanto `docs/` como el
`.streamlit/secrets.toml` que lee Streamlit se resuelven RELATIVOS al
directorio actual, y corriendolo desde `tools/` no encontraria ninguno de los
dos.

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

import os
import sys
import time
from pathlib import Path

# El script se para en la raiz del repo pase lo que pase: los imports (`ia.*`),
# la carpeta `docs/` y el `secrets.toml` que lee Streamlit dependen todos de
# donde estemos parados, y el error mas comun es correrlo desde `tools/`.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

from ia.cliente import (  # noqa: E402
    hay_credencial, modelo_configurado, proveedor, etiqueta_proveedor,
    bots_habilitados, motivo_bot_apagado, stream_texto, resumen_uso,
    costo_estimado, es_gemini_gratis,
)
from ia.proveedores import Gemini  # noqa: E402
from ia.contexto import cargar_docs, bloques_system  # noqa: E402

PREGUNTA = "En una sola frase: ¿qué es la cascada del pool de gas?"


def listar_modelos() -> int:
    """`--modelos`: los que ESTA key tiene habilitados.

    Los nombres de modelo de Gemini rotan rápido, así que preguntarle a la API
    es más confiable que cualquier default escrito en el código.
    """
    p = proveedor()
    if p is None:
        print("✗ No hay credencial.")
        return 1
    if p is not Gemini:
        print(f"{p.etiqueta}: el listado sólo está implementado para Gemini. "
              f"El modelo por defecto es `{p.modelo_default}`.")
        return 0
    try:
        modelos = Gemini.listar_modelos()
    except Exception as e:  # noqa: BLE001
        print(f"✗ No se pudieron listar: {type(e).__name__}: {e}")
        return 1
    print(f"Modelos disponibles para esta key ({len(modelos)}):")
    for m in modelos:
        marca = "  <- en uso" if m == modelo_configurado() else ""
        print(f"  {m}{marca}")
    print("\nPara fijar uno: ASISTENTE_MODELO = \"...\" en los secretos.")
    return 0


def main() -> int:
    if "--modelos" in sys.argv:
        return listar_modelos()

    print("== Asistente: verificación de la capa IA ==")
    print(f"Raíz del proyecto: {RAIZ}\n")

    p = proveedor()
    if p is not None:
        try:
            __import__(p.paquete.replace("-", "_") if p.paquete != "google-genai"
                       else "google.genai")
        except ImportError:
            print(f"✗ Falta la SDK de {p.etiqueta}: "
                  f"`pip install {p.paquete}` (y agregala a requirements.txt).")
            if p.paquete == "google-genai":
                print("  OJO: NO es `google-generativeai`, que está archivada.")
            return 1
        print(f"✓ SDK de {p.etiqueta} instalada (`{p.paquete}`)")

    if not hay_credencial():
        secrets = RAIZ / ".streamlit" / "secrets.toml"
        print("✗ No hay credencial (ni ANTHROPIC_API_KEY ni GEMINI_API_KEY).")
        print("  Opción 1 — sólo para esta terminal:")
        print('    PowerShell:  $env:GEMINI_API_KEY = "AIza..."')
        print("    bash:        export GEMINI_API_KEY=AIza...")
        print(f"  Opción 2 — permanente, y es la que usa la app: {secrets}")
        print('    GEMINI_API_KEY = "AIza..."')
        print(f"    (existe: {'sí' if secrets.exists() else 'NO'})"
              "  ← acordate de que .streamlit/ vaya al .gitignore")
        return 1
    modelo = modelo_configurado()
    print(f"✓ {etiqueta_proveedor()} · modelo `{modelo}`")

    if es_gemini_gratis():
        print("  ⚠ Tier gratuito: lo que enviés puede usarse para entrenar y "
              "ser revisado por personas. No mandes datos confidenciales.")

    habilitados = bots_habilitados()
    print(f"✓ Bots con IA: {', '.join(habilitados) or '(ninguno)'}")
    for bot in ("docs", "resultados", "agente"):
        if bot not in habilitados:
            print(f"  · {bot}: apagado — "
                  f"{motivo_bot_apagado(bot).splitlines()[0][:90]}")

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

    if "docs" not in habilitados:
        print("\nEl bot de documentación está apagado: no hay nada que probar. "
              "Habilitalo con ASISTENTE_BOTS.")
        return 1

    system = bloques_system("docs", docs)
    mensajes = [{"role": "user", "content": PREGUNTA}]
    usos = []

    for intento in (1, 2):
        etiqueta = "1ª llamada (escribe caché)" if intento == 1 else \
                   "2ª llamada (debería leer caché)"
        print(f"\n-- {etiqueta} --")
        t0 = time.time()
        uso: dict = {}
        try:
            texto = "".join(stream_texto(system, mensajes, max_tokens=300,
                                         registro_uso=uso)).strip()
        except Exception as e:  # noqa: BLE001
            print(f"✗ Falló la llamada: {type(e).__name__}: {e}")
            if "429" in str(e) or "quota" in str(e).lower():
                print("  Parece rate limit. El tier gratuito de Gemini permite "
                      "pocas llamadas por minuto: esperá un rato y reintentá.")
            if "404" in str(e) or "not found" in str(e).lower():
                print("  El modelo no existe o tu key no lo tiene habilitado. "
                      "Corré con --modelos para ver los disponibles.")
            return 1
        segundos = time.time() - t0
        usos.append(uso)
        print(f"   {segundos:.1f}s · {resumen_uso(uso, modelo)}")
        print(f"   → {texto[:220]}")

        # El cache tarda un instante en quedar disponible tras la 1ª respuesta.
        if intento == 1:
            time.sleep(2)

    leido = usos[1].get("cache_leido", 0)
    if proveedor() is Gemini:
        print("\nNota: Gemini hace caching implícito en los modelos Flash, sin "
              "nada que declarar. Si el contador de caché queda en cero no es "
              "un error.")
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
