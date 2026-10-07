# OpenHands local — primera experiencia con Agent Canvas

## Elección de versión

El 5 de octubre de 2026 el repositorio oficial publica Agent Canvas 1.24.0 como release estable. La antigua Local GUI aparece como proyecto deprecado en la documentación. Se utiliza la imagen oficial all-in-one de Agent Canvas, que incluye Agent Server 1.49.6 y Automation 1.15.1. El frontend sigue ejecutando el agente OpenHands; no hace falta un proveedor cloud.

Imagen Linux amd64 fijada por digest en `infra/openhands/versions.yaml`; aproximadamente 1.40 GB comprimidos. El digest identifica toda la imagen y sus componentes. Node y el runtime Python de OpenHands están dentro de la imagen. El Python del host, fijado por mise, solo se utiliza para los scripts de configuración y validación del repositorio. mise mantiene Task y Python; go-task coordina y `scripts/openhands/` implementa.

## Arranque

Desde la terminal normal del host:

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise exec -- task openhands:setup
```

La tarea comprueba Ollama y su inferencia, descarga la imagen, crea el workspace y arranca el contenedor. Puede solicitar sudo para acceder a Docker. Aplica un segundo archivo Compose al proyecto `agent-platform-local`, conservando el volumen de pesos existente. Puede recrear Ollama para conectarlo a la red interna; no ejecutarla durante otra inferencia.

Al finalizar, abrir **http://127.0.0.1:8000/canvas**. El chequeo comprueba HTML HTTP 200 y la ruta DNS/API desde OpenHands a Ollama, además del digest del modelo. No prueba todavía una conversación del agente.

## Configurar el modelo en la interfaz

En Settings / LLM Profiles, crear y activar el perfil `local-qwen3-8b`. Usar opciones avanzadas si el modelo no aparece:

| Campo | Valor |
| --- | --- |
| Modelo personalizado | `openai/qwen3:8b` |
| Base URL | `http://ollama:11434/v1` |
| API key | `local-only` (placeholder, no secreto real) |

El prefijo `openai/` selecciona el cliente compatible; los pesos siguen ejecutándose en Ollama. Dentro del contenedor `localhost` apunta a OpenHands, por eso se usa el nombre DNS `ollama`. Guardar y activar el perfil antes de crear la conversación. No seleccionar suscripciones, proveedor cloud ni introducir credenciales de GitHub en esta prueba.

El contexto inicial de 8192 tokens se usó para la prueba de inferencia; se ha ampliado a 32768 para probar OpenHands. Si el formulario permite límites de entrada/salida, evitar valores mayores que el contexto disponible y comenzar con salida de 1024 tokens. Un agente incorpora instrucciones y descripciones de herramientas; El contexto debe cubrir también las instrucciones y las herramientas del agente. Evaluar errores de contexto y calidad antes de aumentar memoria o cambiar modelo.

Desactivar el consentimiento de analytics/product telemetry en la interfaz. Agent Server tiene exporter `none` y consentimiento denegado. La imagen incluye un frontend con analytics compilado: la red interna del contenedor no controla las solicitudes que hace el navegador. No se afirma ausencia total de telemetría del navegador sin verificación adicional.

## Primera tarea pedagógica

Seleccionar el agente OpenHands y la carpeta `/projects/demo` (la ruta por defecto también está configurada ahí). Si la interfaz pregunta por ejecución o aprobación, revisar los comandos y activar confirmación manual cuando esté disponible. La política de aprobación propia de nuestra plataforma todavía no está implementada.

Enviar esta tarea:

> Trabaja únicamente en /projects/demo. Crea sum.py con una función add(a, b) y test_sum.py con unittest. Incluye pruebas de enteros positivos, negativos y cero. Ejecuta python -m unittest -v y resume los resultados. Usa solamente la biblioteca estándar, sin descargar dependencias ni acceder a Internet. No modifiques otros archivos.

Comprobar que los dos archivos aparecen en `artifacts/openhands/projects/demo/`, que los tests pasan y que la conversación termina. Una suma es una prueba de herramientas y ejecución, no una evaluación representativa de programación compleja. Guardar un resumen del resultado sin copiar prompts personales, secretos ni conversaciones completas a Git.

## Acceso, persistencia y límites

- UI publicada solo en `127.0.0.1:8000`. API de sesión y clave de cifrado se generan y conservan en el volumen `agent-platform-local_openhands-state`; no se imprimen ni se añaden al repositorio.
- Solo se monta `artifacts/openhands/projects` como `/projects`. No se monta el repositorio completo, HOME, claves SSH ni Docker socket. Esa carpeta está dentro de CloudDrive: cualquier archivo de la demo puede sincronizarse; utilizar solo datos sintéticos.
- La imagen corre como usuario no root. Se añade el grupo primario del usuario del host y se crean las dos carpetas con modo 2770. No se realiza chown recursivo ni cambios a los grupos del host. El arranque verifica permisos reales del contenedor.
- OpenHands usa exclusivamente una red Docker interna compartida con Ollama; no tiene salida directa a Internet. Ollama conserva su red de descarga y su puerto loopback. Esto no protege frente a una vulnerabilidad del servicio ni evita tráfico del navegador.
- 6 GB RAM, 4 CPU, máximo 512 procesos, sin capacidades Linux y sin elevación de privilegios. El agente puede ejecutar comandos dentro de su contenedor, modificar el workspace y acceder a su propio estado; el estado no es una auditoría inmutable.
- No se habilitan automations ni conectores en esta fase. El componente Automation está incluido en la imagen, pero no se crean trabajos recurrentes. Editor integrado desactivado para esta prueba.
- OpenHands no recibe GPU: Ollama es el servicio que la utiliza. No se reinicia automáticamente al arrancar Docker; se inicia de forma explícita.

## Operación y problemas

```bash
mise exec -- task openhands:plan
mise exec -- task openhands:status
mise exec -- task openhands:check
mise exec -- task openhands:logs
mise exec -- task openhands:down
mise exec -- task openhands:up
```

`openhands:down` detiene OpenHands y su proxy; conserva estado, workspace y Ollama. No usar `compose down -v` para operar este laboratorio.

Si se ejecuta después `llm:up` con su Compose individual, puede restaurar la configuración de redes de Ollama. Ejecutar `openhands:up` para reaplicar la conexión compartida.

Si falla la UI, revisar `openhands:logs`. No compartir claves ni cuerpos de conversaciones: los logs upstream no tienen aún nuestra capa de redacción. Si falla el acceso a `/projects/demo`, revisar el grupo y los permisos sin usar chmod 777. Si intenta descargar dependencias, la red interna debe impedirlo; mantener la tarea inicial con biblioteca estándar. Si el modelo falla al llamar herramientas o excede contexto, registrar el error: un chequeo sintético pasado no garantiza calidad del agente.

## Validación realizada y pendiente

Se resolvió el digest oficial amd64 y se consultaron código, configuración de imagen y versión de los componentes. Se valida la configuración Compose combinada, los mounts y la red, y la sintaxis de los scripts. La ejecución real requiere la terminal del host con acceso a Docker; arranque, perfil LLM y conversación siguen pendientes hasta compartir los resultados.

## Fuentes

- [Release v1.24.0 y Quickstart oficial](https://github.com/OpenHands/OpenHands/tree/v1.24.0)
- [Dockerfile de la imagen](https://github.com/OpenHands/OpenHands/blob/v1.24.0/docker/Dockerfile)
- [Entrypoint y persistencia](https://github.com/OpenHands/OpenHands/blob/v1.24.0/docker/entrypoint.sh)
- [Agent Server: configuración](https://github.com/OpenHands/software-agent-sdk/blob/v1.49.6/openhands-agent-server/openhands/agent_server/config.py)
- [Modelos locales](https://docs.openhands.dev/openhands/usage/llms/local-llms)

## Corrección del paso por sudo — 5 de octubre de 2026

La primera ejecución del host validó Ollama (40.88 tokens/s), pero Compose falló antes de descargar OpenHands: sudo eliminó `OH_HOST_GID` y `OH_WORKSPACE` del entorno. Se corrigió el helper para conservar únicamente esas dos variables al invocar Compose mediante sudo. No se conserva el entorno completo ni se cambia sudoers. Reintentar `task openhands:up`; no hace falta repetir la descarga ni la comprobación del modelo. El arranque real sigue pendiente.

## Corrección de publicación de la UI — 5 de octubre de 2026

Los logs del host confirmaron que Agent Canvas y Automation arrancaron. Sin embargo, `compose ps` solo mostró `8000/tcp`, sin binding al host. La configuración anterior publicaba el puerto directamente desde un servicio conectado exclusivamente a la red interna; no produjo un puerto accesible en este Engine.

Se añadió `openhands-proxy`, con Nginx 1.30.5 fijado por digest. Solo el proxy publica `127.0.0.1:8000`, reenviando HTTP, WebSocket y streaming al puerto 8000 interno de Agent Canvas. OpenHands sigue conectado exclusivamente a `agent-link`. El proxy tiene red normal e interna, usuario no root, filesystem de solo lectura y sin Docker socket; no funciona como proxy de navegación genérico. Su access log está desactivado. La imagen del proxy es una descarga adicional pequeña.

Reintentar `task openhands:up`. Los checks de status/logs/down incluyen ambos servicios. No se borra el volumen de estado ni el modelo. La validación real del acceso desde el host sigue pendiente hasta ejecutar el nuevo despliegue.

Referencia: [Publicación de puertos Docker](https://docs.docker.com/engine/network/port-publishing/).

## Próximo paso — primera conversación y aceptación

La UI ya es accesible según confirmó el usuario. Sigue pendiente verificar el perfil activo y una tarea completa. Mantener subagentes y cambio automático de perfiles desactivados. Crear una conversación nueva con OpenHands, perfil `local-qwen3-8b` y workspace `/projects/demo`.

Usar la tarea de suma de esta guía; solicitar al menos tres casos unittest. No crear nosotros los archivos de solución antes: se evalúa que el agente los produzca y ejecute.

Al terminar, ejecutar en la terminal del host:

```bash
mise exec -- task openhands:demo:check
```

El check exige `sum.py` con `add(a, b)`, resultados correctos para cuatro entradas sintéticas y al menos tres tests unittest exitosos y no omitidos en `test_sum.py`. Ejecuta los archivos generados dentro del contenedor, no en el host. El checker verifica que existan archivos normales en el workspace y falla si faltan; no escribe ni corrige la solución. La validación funcional no demuestra que todos los cambios del agente hayan permanecido dentro del workspace: revisar también los eventos de la conversación.

Si el agente se detiene por error, compartir el mensaje de error y la última acción; no cambiar modelo, contexto o permisos sin identificarlo. Si termina, compartir el resumen y la salida del check. Registrar después éxito/fallo, tiempo aproximado, número de intentos y errores de herramientas. No declarar completada la fase solo porque la UI o la API responden.

## Incidente de uso de herramientas y ajuste de contexto

El usuario compartió un ciclo en el que el agente perdió la petición de terminal, eligió `think` y finalizó sin ejecutar el comando solicitado. La prueba sintética de herramientas pasó anteriormente, pero no valida un agente con todas sus instrucciones y herramientas.

La guía oficial de modelos locales de OpenHands recomienda al menos unos 22000 tokens, idealmente 32768 o más. Nuestra primera configuración de 8192 era conservadora para probar GPU, pero insuficiente como referencia para el agente completo. Se actualizó Ollama y el lock a 32768, manteniendo pesos, digest y modelo. Esto puede aumentar la VRAM; confirmar nuevamente residencia y rendimiento antes de continuar. La pérdida de contexto es una hipótesis, no una causa confirmada mediante el request real.

Desde el host:

```bash
mise exec -- task openhands:up
mise exec -- task llm:check
mise exec -- task llm:status
mise exec -- task openhands:profile:check
```

El último comando consulta los defaults persistidos de Agent Server e imprime solo campos permitidos del perfil y nombres de herramientas; no muestra claves, prompts ni conversaciones. Las conversaciones existentes pueden conservar otra configuración. Crear una conversación nueva tras corregir el perfil y confirmar que las herramientas incluyen terminal y archivos. Desactivar herramientas de navegador que no sean necesarias si la UI permite configurarlas.

Revisar límites de entrada/salida del perfil para que sean coherentes con 32768. No confundir los 128 tokens del smoke test con el límite del agente; ese valor solo está en el script de pruebas sintéticas. Para Qwen3, probar reasoning effort `none` si la configuración lo ofrece; Ollama documenta que ese valor desactiva thinking en modelos compatibles. No asumir que el indicador visual Thinking implica un fallo por sí solo.

Repetir en una conversación nueva una única petición: ejecutar `pwd` y mostrar la salida real de la herramienta terminal. Después intentar `cd /projects/demo && pwd && ls -la`. Si sigue sin llamar terminal, revisar configuración y evaluar un modelo distinto. Todavía no se realiza fine-tuning ni se descarga otro modelo.

Fuentes: [Contexto recomendado por OpenHands](https://docs.openhands.dev/openhands/usage/llms/local-llms), [reasoning_effort en Ollama](https://docs.ollama.com/api/openai-compatibility).

## Validación del contexto ampliado y corrección del diagnóstico

El usuario compartió el 5 de octubre a las 18:45 UTC: UI y conexión interna correctas, contexto cargado 32768, 100% GPU y 9,969,650,892 bytes de VRAM. Generación, herramienta sintética y API compatibles pasaron, pero la primera solicitud después de recrear Ollama dio 0.79 tokens/s: carga 32.566 s, prompt 21.998 s y generación de tokens 12.625 s. La lentitud no se atribuye solo a carga; repetir la prueba para comprobar si persiste antes de modificar más parámetros.

`openhands:profile:check` falló porque `agent_settings.tools` era null. Se corrigió el tratamiento de ese valor y se añade `tools_explicitly_configured`; null puede representar defaults heredados y no demuestra ausencia efectiva de herramientas en una conversación. La tarea consulta los defaults persistidos, no la configuración efectiva de cada sesión.

Repetir `task openhands:profile:check`, `task llm:check`, `task llm:status` y `task llm:logs`. La tarea del agente aún no está validada.

## Segunda medición con 32768 y perfil activo

El usuario compartió a las 18:48 UTC del 5 de octubre: perfil `local-qwen3-8b`, modelo `openai/qwen3:8b`, base URL interna correcta, `reasoning_effort=high`; límites de entrada/salida y temperatura null (defaults, no significa cero). Herramientas sin configuración explícita; no se conoce aún la lista efectiva de la conversación.

La repetición del smoke test dio 52.22 tokens/s, 0.265 s totales, 0.002 s de carga, 0.035 s de prompt y 0.192 s de generación; 100% GPU y contexto 32768. Los logs muestran reutilización de prompt cache, por lo que no es una comparación representativa con una solicitud fría ni un benchmark de instrucciones largas. El fallo funcional del agente todavía está pendiente de repetir.

Próximo experimento: en el perfil LLM, cambiar reasoning effort de high a none si la interfaz lo ofrece, guardar y activar. Ollama documenta none como solicitud de desactivar thinking en modelos booleanos compatibles. No afirmar que high sea la causa confirmada del fallo. Crear conversación nueva con cambio de perfiles y subagentes desactivados; solicitar una única ejecución de `pwd` con la herramienta de terminal. Si no existe la opción none, revisar la pantalla de opciones avanzadas antes de elegir otro ajuste.

## Hito validado — primera tarea completa, 5 de octubre de 2026

El usuario compartió la salida de `task openhands:demo:check`: `test_negative`, `test_positive` y `test_zero` pasaron, tres tests ejecutados sin omisiones, y la comprobación adicional de la función add fue satisfactoria. El check ejecuta los archivos presentes en `/projects/demo` dentro del contenedor. La carpeta corresponde a `artifacts/openhands/projects/demo` en el host.

Resultado: el laboratorio completó su primera tarea sintética de código y pruebas con OpenHands y Qwen3 local. La secuencia incluyó confirmación de la ruta de trabajo y verificación independiente de la solución. La ejecución fue realizada en la terminal del usuario; no se volvió a ejecutar desde Work. El cambio a contexto 32768 precedió a este resultado. No se registró aún una nueva lectura del perfil que confirme el valor efectivo de reasoning effort ni se atribuye el éxito a un único cambio.

Este hito comprueba el funcionamiento básico, no calidad sostenida, seguridad completa ni cumplimiento de todas las restricciones del prompt. Aún están pendientes observabilidad centralizada, auditoría, políticas y adaptadores de la plataforma.

Siguiente experimento propuesto: corregir un bug pequeño en un proyecto de ejemplo con tests existentes, comprobando fallo previo y éxito posterior, y registrar duración, errores de herramientas y cambios de archivos. Mantener un agente, perfil fijo y datos sintéticos para comparar con esta referencia.

La segunda prueba está descrita en [openhands_bugfix.md](openhands_bugfix.md), con tareas `openhands:bugfix:prepare`, `baseline` y `check`.

## Siguiente etapa — observabilidad con integraciones existentes

La [guía de observabilidad](observability.md) explica cómo intercalar LiteLLM entre OpenHands y Ollama, activar los tres backends y provisionar Grafana. Incluye el perfil `local-qwen3-8b-observed`, comandos de aceptación, ubicación de logs, privacidad y vuelta al perfil directo. Los [diagramas](architecture/observability_diagrams.md) muestran la ruta LLM, redes, almacenamiento y evolución.

La configuración está preparada; no se afirma desplegada. El callback LiteLLM excluye mensajes; el Collector sanitiza trazas y logs. El tracing nativo de OpenHands es optativo para datos sintéticos porque puede capturar argumentos/resultados antes del filtro. El exporter de telemetría de producto `none` es un control distinto de OTLP del SDK. No habilitarlo pensando que la captura en origen ya está completamente eliminada.
