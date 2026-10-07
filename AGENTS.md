# Instrucciones de colaboración

- Comunicar en español. El usuario exige ver siempre los cambios que se hacen.
- Antes de editar, indicar los archivos afectados, el cambio previsto y su propósito.
- Al terminar, mostrar los archivos cambiados con enlaces y un diff real o fragmentos concretos del código; explicar el efecto y cómo se verificó.
- Distinguir código preparado, validación aislada, configuración aplicada y aceptación real. No presentar como desplegado lo que solo está en disco.
- Si no existe un baseline Git, decirlo y no inventar un diff histórico. No crear commits o publicar cambios solo para fabricar ese baseline.
- No imprimir secretos, valores de credenciales ni contenido de conversaciones en explicaciones, diffs o reportes.
- Mantener mise para herramientas/entorno, Task para llamadas breves y scripts organizados por área para implementación. Mantener documentación de arquitectura y operación en docs/.

- Instalación y validación del ambiente se declaran en mise.toml; Taskfile.yml contiene operación/despliegue de servicios y tests de código. No duplicar tareas de ambiente en Task.
- Dependencias Python en pyproject.toml y uv.lock, gestionadas con uv fijado por mise. No poner requirements Python en infra/ ni mantener archivos duplicados de dependencias.
- Mantener descripciones y comentarios útiles en TOML; lógica extensa en scripts/ por área.
- Nombres de documentos bajo docs/ en minúsculas; actualizar enlaces y referencias al renombrar. Mantener README.md, LICENSE y AGENTS.md convencionales en la raíz.
