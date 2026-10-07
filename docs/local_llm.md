# Primera inferencia local — Ollama + Qwen3 8B

## Decisión y alcance

Usar Ollama 0.35.1 en Docker y `qwen3:8b` Q4_K_M como prueba inicial de inferencia y herramientas. El modelo ocupa aproximadamente 5.23 GB de descarga. Con 16 GB de VRAM y contexto inicial de 8192 tokens es una selección conservadora; su consumo real y rendimiento se medirán en el host.

Qwen3 8B es una primera referencia técnica, no una garantía de calidad para tareas largas de OpenHands. La página del modelo declara soporte de herramientas y licencia Apache 2.0. La licencia MIT del repositorio no cambia las licencias de Ollama, modelos u otros componentes.

## Preparación

Desde una terminal normal del host:

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
export PATH="$HOME/.local/bin:$PATH"
mise install
mise exec -- task llm:plan
mise exec -- task llm:setup
```

`llm:setup` valida el repositorio y Compose, arranca Ollama, espera su estado saludable, descarga el modelo, comprueba su digest y ejecuta pruebas de inferencia. Docker usa explícitamente el contexto `default`, para evitar un contexto Docker Desktop o socket configurado accidentalmente. Puede pedir sudo para acceder al Engine; el script no modifica grupos ni privilegios.

La primera ejecución descarga la imagen Ollama y unos 5.23 GB de pesos. Comprobar espacio en el almacenamiento Docker, no solo en CloudDrive. El script intenta verificarlo y avisa si no puede leer esa ruta. No elimina otros modelos ni volúmenes.

## Seguridad y persistencia

- API: `http://127.0.0.1:11434`; publicada solo en loopback, sin autenticación. Los procesos locales pueden usarla.
- Funciones cloud desactivadas mediante `OLLAMA_NO_CLOUD=1`. Esto no es una restricción de red: el servicio necesita salida para descargar pesos.
- GPU 0 reservada, un modelo cargado y una solicitud paralela, contexto inicial de 8192.
- Límites de memoria RAM de 12 GB y 8 CPU; no equivalen a limitar VRAM. Si falta memoria, revisar los logs antes de aumentar límites.
- Sin Docker socket ni carpetas personales montadas en Ollama; se eliminan capacidades y se impide elevar privilegios.
- Pesos guardados en el volumen Docker `agent-platform-local_ollama-data`, fuera del repositorio y de la sincronización CloudDrive.
- `llm:down` conserva los pesos. El servicio usa `unless-stopped`; se reanuda con Docker si no se detuvo explícitamente.
- Los logs Docker tienen rotación. No introducir información sensible mientras no se haya revisado toda la política de datos.

## Versiones fijadas

`infra/llm/versions.yaml` conserva versión y digest Linux amd64 de Ollama, digest del manifiesto del modelo y opciones de la prueba. Compose fija la imagen por digest.

El tag del modelo se descarga mediante Ollama y se compara con el digest esperado. Si el upstream modifica el tag, el proceso falla antes de inferencia; no actualiza el lock automáticamente. No garantizamos disponibilidad eterna del tag fijado. Para preservar una copia reproducible conservar los pesos y su manifiesto en el volumen o un backup revisado.

Los pesos se verifican mediante los mecanismos de descarga de Ollama; el script adicional verifica la identidad del manifiesto instalado.

## Qué comprueba llm:check

1. Versión del servidor y digest del modelo instalado.
2. Generación de una respuesta JSON correcta a una suma sintética, completada sin truncamiento.
3. Modelo cargado con `size_vram > 0` según `/api/ps`. Demuestra asignación GPU, no demuestra que todas las capas estén en GPU ni constituye una prueba de carga sostenida.
4. Una llamada sintética `add(a=2, b=3)` con argumentos correctos; no ejecuta herramientas ni acciones externas.
5. Una respuesta válida y no truncada desde `/v1/chat/completions`.
6. Tokens/segundo calculados con `eval_count / eval_duration`, que excluyen la carga inicial. El campo histórico `generation_seconds` contiene el tiempo total; se añaden `token_generation_seconds`, `model_load_seconds` y `prompt_processing_seconds` para distinguir las fases. Es una muestra corta, no un benchmark comparable.

La prueba usa solo datos sintéticos. Guarda resúmenes de estado, versión, digest, tiempos y VRAM en `artifacts/diagnostics/llm-*.json`; no guarda prompts, respuestas ni razonamiento. El informe no valida todavía compatibilidad completa o calidad de OpenHands.

## Operación y diagnóstico

```bash
mise exec -- task llm:status
mise exec -- task llm:check
mise exec -- task llm:logs
mise exec -- task llm:down
# Reanudar conservando pesos:
mise exec -- task llm:up
# Comprobar host y modelo:
mise run env:check
mise exec -- task llm:check
```

- **sudo bloqueado en Work:** ejecutar desde la terminal normal del host.
- **Puerto 11434 ocupado:** revisar el servicio existente; no se detiene automáticamente ni se cambia el puerto silenciosamente.
- **Digest distinto:** revisar el cambio upstream y actualizar configuración explícitamente; no ignorar el control.
- **Sin VRAM o error CUDA:** comprobar host y Docker/GPU y revisar logs del servicio. No reinstalar el driver sin diagnóstico.
- **Respuesta/llamada inválida:** infraestructura y calidad son controles separados; registrar el fallo y evaluar modelo/opciones antes de OpenHands.
- **Timeout:** revisar memoria y modelo cargado; cada solicitud de inferencia tiene un timeout de 600 segundos y no se reintenta automáticamente.

## Estado de validación

Se verificaron disponibilidad de la imagen y del manifiesto del modelo, sintaxis shell, configuración Compose y consistencia con el lock. Los tests de validadores usan fixtures y comprueban fallos reales como drift, CPU-only, truncamiento y llamadas incorrectas.

El usuario ejecutó `task llm:setup` desde el host y compartió un resultado satisfactorio el 5 de octubre de 2026: versión y digest correctos, generación JSON, residencia GPU, llamada sintética y API compatible verificadas. El informe tiene timestamp UTC del 4 de octubre a las 22:16, equivalente al 5 de octubre a las 00:16 en Europe/Berlin.

Se observaron 0.78 tokens/s, 10 tokens generados, 68.809 segundos totales y 6,295,440,588 bytes de VRAM asignados (aproximadamente 5.86 GiB). La prueba funcional pasó; el rendimiento requiere diagnóstico. La velocidad usa solo `eval_duration`, por lo que no se puede atribuir únicamente a la carga inicial. No se comprobó aún el porcentaje de capas en GPU.

Antes de OpenHands, repetir la prueba y consultar el reparto CPU/GPU inmediatamente después, mientras el modelo sigue cargado:

```bash
mise exec -- task llm:check
mise exec -- task llm:status
mise exec -- task llm:logs
```

Compartir esos resultados para revisar tiempos, `PROCESSOR` y backend CUDA. No cambiar driver, modelo o límites sin evidencia. El informe original queda en `artifacts/diagnostics/llm-y546ryve.json` en el host; este estado está basado en la salida compartida por el usuario.

## Segunda validación — 5 de octubre de 2026

El usuario compartió una nueva ejecución del host, a las 07:49 UTC (09:49 Europe/Berlin), con todos los controles satisfactorios:

| Medida | Resultado |
| --- | --- |
| Generación según API | 38.07 tokens/s; 10 tokens |
| Tiempo total de la primera solicitud | 3.565 s |
| Carga del modelo | 3.153 s |
| Procesamiento del prompt | 0.148 s |
| Generación de tokens | 0.263 s |
| VRAM asignada | 6,295,440,588 bytes, aproximadamente 5.86 GiB |
| Reparto mostrado por `ollama ps` | 100% GPU |
| Contexto cargado | 8192 tokens |
| Llamada sintética y API compatible | Verificadas |

El contenedor aparece saludable. Los logs muestran solicitudes HTTP 200 y velocidades internas de generación de aproximadamente 34–45 tokens/s en las tres solicitudes. La tasa interna del runner y la tasa calculada con los contadores de la API usan convenciones de conteo distintas; no se exige igualdad entre ambas.

La lentitud de 0.78 tokens/s de la primera ejecución no se reprodujo. Estos logs no explican su causa; no se atribuye de forma concluyente a carga inicial, driver o CPU. No se requieren cambios del driver o de los límites con la evidencia actual.

Informe original en el host: `artifacts/diagnostics/llm-eofbwzvb.json`. Este registro se basa en la salida compartida, no en una ejecución desde Work. Son pruebas cortas y sintéticas; aún no demuestran rendimiento sostenido, calidad de tareas complejas o compatibilidad completa con OpenHands.

La infraestructura de inferencia está lista para la siguiente fase: integrar OpenHands y ejecutar una tarea pedagógica pequeña en un workspace dedicado. Mantener el modelo y el contexto actuales como referencia inicial y evaluar por separado las necesidades de contexto y calidad del agente.

## Fuentes

- [Ollama en Docker](https://docs.ollama.com/docker)
- [Qwen3 8B: tamaño, capacidades y licencia](https://ollama.com/library/qwen3:8b)
- [API generate](https://docs.ollama.com/api/generate)
- [API chat](https://docs.ollama.com/api/chat)
- [Modelos cargados y VRAM](https://docs.ollama.com/api/ps)
- [Ollama local-only y configuración](https://docs.ollama.com/faq)

## Cambio de contexto para el agente

Tras el primer fallo de uso de herramientas en OpenHands se amplió el contexto del servidor de 8192 a 32768 tokens, conservando la identidad del modelo. Las medidas anteriores corresponden a 8192 y no deben tratarse como benchmark del nuevo contexto. La aplicación del cambio requiere reiniciar mediante `task openhands:up`; el nuevo consumo y el comportamiento del agente están pendientes de verificar.
