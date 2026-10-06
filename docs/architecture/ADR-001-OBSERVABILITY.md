# ADR 001 — Reutilizar integraciones de observabilidad

Fecha: 5 de octubre de 2026. Decisión aceptada para el laboratorio; despliegue e integración real pendientes de validar.

## Problema

Ollama y OpenHands ya ejecutan tareas sintéticas. Necesitamos ver solicitudes LLM, errores y actividad del agente en Grafana, sin duplicar instrumentación ni almacenar contenido personal. Un adaptador que interprete conversaciones upstream añadiría mantenimiento y dependería de formatos internos.

## Decisión

1. LiteLLM Proxy será la frontera compatible con OpenAI para llamadas al modelo y emitirá OTel mediante su callback existente.
2. OpenHands conservará su runtime. Su SDK tiene tracing nativo basado en Laminar/OTel; se habilitará aparte con datos sintéticos. No se configura una cuenta ni endpoint cloud Laminar.
3. El Collector Contrib usará OTLP, filelog y el receiver Prometheus nativo para tokens de caché; sanitizará antes de enviar a Tempo, Prometheus y Loki.
4. Grafana provisionará fuentes y siete dashboards (vista general y seis especializados) desde archivos versionados. Los indicadores sin fuente se identificarán como pendientes.
5. No habrá adaptador propio de conversaciones en esta fase. Solo configuración, scripts de operación y comprobaciones sintéticas.

## Alternativas

- **Grafana Alloy:** disponible para recolectar logs/OTel; válido si se unifica la pila en su ecosistema. Se elige Collector Contrib porque ya es parte del objetivo y ofrece filelog/transform. No necesitamos dos recolectores ahora.
- **Langfuse/Phoenix:** útiles para evaluación, datasets y contenido de generaciones. No se añaden junto a Grafana en esta etapa; evitar más persistencia de contenido y servicios hasta tener una necesidad de evaluación.
- **Instrumentación automática Python:** puede capturar llamadas a bibliotecas pero no reconstruye por sí sola decisiones, aprobaciones ni resultados de negocio. Revisar versión y privacidad antes de incorporarla.
- **Exporter Ollama/GPU comunitario:** puede complementar métricas de servidor/GPU; no sustituye trazas del agente. Se pospone hasta verificar compatibilidad con la RTX 4060 Ti y mantenimiento.
- **Adaptador propio:** reservarlo para una carencia concreta demostrada. Métricas propias de decisiones/calidad se emitirán desde los futuros contratos del runtime, no deduciendo éxito a partir de logs.

## Consecuencias

Hay un salto HTTP adicional y un servicio más entre agente y modelo. Debemos medir la latencia y repetir tool calls reales al cambiar la ruta. El perfil directo queda disponible para volver al laboratorio anterior.

La primera cobertura se limita a llamadas LLM y logs sanitizados. La correlación completa exige propagación de contexto comprobada. El tracing nativo puede introducir contenido en memoria antes del filtro; no cumple todavía una prohibición absoluta de capturarlo en origen. Se mantiene optativo.

El Collector que lee logs usa UID 0 con mounts limitados y de lectura, sin Docker socket. La configuración depende de IDs de contenedor y debe refrescarse tras recrearlos. La telemetría almacenada pierde texto de errores deliberadamente; el diagnóstico completo, si fuera necesario, se realiza localmente con datos sintéticos.

La auditoría durable y la autorización de herramientas siguen perteneciendo al diseño del runtime. Grafana, LiteLLM y OTel no implementan por sí solos esas políticas.

## Evolución

Validar ingestión y una conversación; definir el contrato de spans/errores del SDK concreto; instrumentar el primer workflow y sus resultados; incorporar evaluación etiquetada. En Kubernetes: sustituir filelog de Docker por logs de pods, separar credenciales/identidad, usar TLS y almacenamiento apropiado, conservar protocolos OTLP y UID de dashboards. No se afirma que el Compose actual sea una instalación enterprise.

## Autenticación del proxy — corrección tras el primer despliegue

LiteLLM 1.104.0 rechaza iniciar sin una master key fuerte. Se genera y conserva fuera de Git/CloudDrive, y los clientes la usan para autenticar solicitudes. Sin base de datos no se implementan todavía virtual keys por usuario; la master key es administrativa y solo es adecuada para este laboratorio local de confianza. La evolución multiusuario deberá separar privilegios de cliente y administración. No se relaja el control de arranque.

Se añade Blackbox Exporter oficial para sondas de nueve endpoints y la telemetría interna del Collector para colas/fallos de envío. No se escribe un adaptador de métricas del runtime. Las sondas no implican ejecución exitosa ni calidad; las alertas se evalúan localmente sin notificaciones. Ver `docs/DASHBOARDS.md`.

## Caché Ollama — ampliación del 6 de octubre de 2026

La prueba local confirmó `prompt_tokens_details.cached_tokens` en Ollama v0.35.1. El callback OTel fijado no transforma ese campo anidado a sus atributos de caché. Se elige el callback Prometheus oficial de LiteLLM, limitado a dos métricas y etiqueta de modelo, junto al receiver Prometheus existente del Collector con autenticación. No se requiere adaptador de conversaciones ni componentes alpha que acumulen números desde spans.

El Collector recibe el master key del laboratorio en su entorno exclusivamente para leer `/metrics/`; no se habilita acceso anónimo ni se publica ese puerto. Privacidad de métricas y modelo local permitido se verifican antes de exportar. La caché de prefijo sigue incluida en Input y no se agrega a Total. Esta instrumentación cubre uso nuevo a través del proxy; conserva la diferencia de alcance con los acumulados persistidos de OpenHands. Ver `docs/diagnostics/TOKENS-2026-10-06.md` para pruebas y aceptación pendiente del host.
