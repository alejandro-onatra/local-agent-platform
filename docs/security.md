# Seguridad reproducible del repositorio

## Implementado: control de secretos

Gitleaks 8.30.1 está fijado en `mise.toml` y su descarga/checksum en `mise.lock`.
Las reglas oficiales incluidas en ese binario se extienden con `.gitleaks.toml`
para detectar la master key local de LiteLLM. No usamos supresiones por comentario,
`.gitleaksignore` ni baseline de hallazgos aceptados.

```bash
mise install --locked
mise exec -- task security:secrets
mise exec -- task security:test
```

La tarea revisa archivos versionados y nuevos no ignorados, contenido staged y
el historial de todas las referencias Git disponibles localmente. Rechaza clones
shallow, symlinks y rutas publicables inesperadas de credenciales, pesos y artefactos.
No revisa secretos ignorados que permanecen fuera de Git; no lee las credenciales
locales almacenadas fuera del repositorio. Tampoco abre archivos comprimidos.

El script genera una clave canaria en un directorio temporal para comprobar que
el detector realmente la encuentra y redacta. Nunca la agrega al repositorio.
Las pruebas en `tests/security/` comprueban bloqueo de secretos nuevos, staged
y borrados del historial, rechazo de symlinks y exclusión de un secreto runtime
ignorado. Solo crean repositorios temporales.

Si hay hallazgos, la tarea falla. Muestra únicamente archivo, línea, regla y commit;
los reportes numéricos y hashes quedan en `artifacts/security/`, excluido de Git.
Errores del scanner fallan el control; no se interpretan como ausencia de secretos.

Cada reporte registra commit, hash de los archivos analizados, configuración,
versión y hash del binario. Las reglas no consultan una API o un modelo. Para
repetir un resultado se necesitan exactamente esos mismos insumos. El gate local
se ejecuta explícitamente antes de publicar; todavía no está impuesto por CI o
protección de ramas. No garantiza encontrar secretos de cualquier formato.

## Siguientes controles propuestos, todavía sin instalar ni ejecutar

| Control | Herramienta y evidencia |
| --- | --- |
| Código Python | Semgrep con reglas locales versionadas, sin `--config auto`; casos positivos/negativos de cada regla |
| Dependencias Python | OSV-Scanner sobre `uv.lock`; fijar scanner y snapshot/fecha de la base de vulnerabilidades |
| Imágenes de contenedores | Trivy sobre los digests existentes; fijar scanner y base de vulnerabilidades |
| Configuración de infraestructura | Trivy config para formatos soportados; tests propios para nuestras políticas de Compose/Collector |
| Controles de aplicación | Matriz versionada OWASP ASVS 5.0.0 y pruebas de autenticación, permisos, aislamiento, redacción y auditoría |
| Publicación | Gate CI con scanners fijados y branch protection; no habilitado aún |

Un hash o una versión de scanner no fija la base de vulnerabilidades. Debemos
conservar su snapshot/digest y fecha para reproducir SCA; refrescarla deliberadamente
para conocer vulnerabilidades nuevas. El mismo principio aplica a las reglas SAST.

OWASP Top 10 orienta riesgos; ASVS contiene requisitos verificables. Cada requisito
aplicable debe tener ID/version, evidencia, test, resultado y límites. Un scanner
sin hallazgos no significa que todo OWASP pase. La autorización efectiva, la
exposición de servicios y el comportamiento de un agente requieren pruebas dinámicas.

Si aparece una credencial real: detener la publicación, revocarla/rotarla y tratar
su historial. Borrar el archivo actual no elimina el secreto de commits anteriores.

Fuentes primarias: [Gitleaks](https://github.com/gitleaks/gitleaks),
[Semgrep](https://docs.semgrep.dev/running-rules),
[OSV-Scanner: uv.lock](https://google.github.io/osv-scanner/supported-languages-and-lockfiles/),
[Trivy](https://trivy.dev/docs/latest/),
[OWASP ASVS](https://owasp.org/projects/asvs).
