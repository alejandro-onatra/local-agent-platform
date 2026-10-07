# Docker y GPU — instalación local reproducible

## Estado

La GPU del host pasó la comprobación: RTX 4060 Ti, 16380 MiB, driver 580.178.04. Docker y NVIDIA Container Toolkit se instalaron y pasaron las comprobaciones desde la terminal del host el 4 de octubre de 2026, según la salida compartida por el usuario.

Work tiene activado `no_new_privs`, que impide elevar privilegios con sudo, y no puede controlar systemd. Por eso la instalación debe ejecutarse en una terminal normal del host. No hace falta iniciar Work como root ni cambiar el driver.

## Punto de entrada con mise

```bash
mise run env:plan
mise run env:setup  # solo cuando haga falta instalar/configurar el host
mise run env:check  # comprobación habitual del entorno ya instalado
```

Ver [bootstrap de mise y tareas](environment.md). Los scripts siguen siendo la implementación. Ejecutarlos directamente requiere activar el entorno Python/PyYAML preparado; para un checkout nuevo seguir primero environment.md.

## Revisar e instalar

```bash
cd /home/alejandro/CloudDrive/Engineering/agent-platform
mise run docker:plan
mise run docker:install
```

El script se ejecuta como Alejandro y pide la contraseña mediante sudo donde corresponde. No pegues la contraseña en el chat. Si APT propone una operación inesperada, interrumpe y revisa el resultado.

## Cambios realizados por el instalador

- Comprueba Ubuntu 26.04 `resolute`, arquitectura amd64 y consulta GPU satisfactoria.
- Se detiene ante paquetes de contenedores incompatibles; no los elimina automáticamente.
- Se detiene si encuentra contenedores activos antes de modificar el runtime/reiniciar Docker.
- Añade los repositorios oficiales estables Docker/NVIDIA y claves con `signed-by`.
- Instala las nueve versiones de `infra/host/versions.yaml`, verificadas en los índices oficiales el 4 de octubre de 2026.
- Configura NVIDIA en `/etc/docker/daemon.json`, habilita y reinicia Docker.
- Conserva las configuraciones previas, si existen, en `/var/backups/agent-platform/` con acceso restringido.
- Comprueba versiones y ejecuta hello-world y una consulta `nvidia-smi` dentro de un contenedor.
- Guarda informes locales en `artifacts/diagnostics/`, excluidos de Git.

No instala CUDA Toolkit, no reemplaza drivers, no abre puertos TCP, no monta la carpeta personal en los contenedores de prueba y no añade usuarios al grupo docker. Los procesos temporales de prueba se eliminan con `--rm`; las imágenes descargadas quedan almacenadas.

Los paquetes del sistema requieren privilegios. El grupo docker da acceso equivalente a root; por ahora las comprobaciones usan sudo cuando sea necesario, sin modificar grupos.

## Versiones y límites de reproducibilidad

Las versiones directas están fijadas en `infra/host/versions.yaml`. Las dos imágenes de prueba están fijadas por digest para Linux amd64; Ubuntu corresponde al tag 24.04 en la resolución inicial. APT valida firmas de repositorios. Los índices consultados al preparar el lock son evidencia de disponibilidad, no una validación de instalación.

Las dependencias transitivas, los paquetes base y el kernel no están congelados. El script registra lo verificado y falla si una versión fijada deja de estar disponible; no cambia automáticamente a latest. No se usan apt holds para impedir futuras actualizaciones de seguridad; los upgrades deben revisar y actualizar el lock.

## Comprobar de nuevo

```bash
mise run docker:check
```

Una consulta GPU satisfactoria dentro de Docker verifica acceso al dispositivo y al driver. La carga CUDA y la inferencia con un modelo serán pruebas posteriores.

## Si falla

- **sudo/no new privileges:** ejecutar en una terminal normal del host, fuera de Work.
- **Paquete incompatible:** revisar su uso antes de desinstalarlo; el script no borra datos de otros runtimes.
- **APT no encuentra una versión:** revisar conectividad, repositorios y lock; no sustituir el codename de Ubuntu.
- **Daemon Docker no arranca:** revisar `sudo systemctl status docker` y `sudo journalctl -u docker -n 80 --no-pager` antes de compartir un extracto sin secretos.
- **GPU no aparece en el contenedor:** confirmar primero `nvidia-smi` en el host, revisar `sudo docker info` y la configuración de NVIDIA.
- **Instalación parcial:** el script se detiene en el primer error y puede haber creado repositorios o instalado parte de los paquetes. Revisar el informe antes de repetir. Reinstalar las mismas versiones normalmente permite continuar.

Restaurar configuración requiere revisar los backups concretos y detener primero los workloads. No hay un rollback automático que elimine Docker, imágenes o volúmenes.

## Fuentes

- [Docker Engine en Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Permisos del grupo docker](https://docs.docker.com/engine/install/linux-postinstall/)

## Validación completada — 4 de octubre de 2026

Evidencia: salida del instalador compartida por el usuario; no es una ejecución del daemon desde Work.

| Componente | Resultado |
| --- | --- |
| Docker Engine cliente / servidor | 29.8.2 / 29.8.2 |
| containerd | 2.3.6 |
| Compose | 5.6.0 |
| Buildx | 0.37.1 |
| NVIDIA Container Toolkit | 1.20.1-1 instalado y runtime configurado |
| hello-world | Ejecución correcta con imagen fijada por digest |
| GPU dentro de contenedor | RTX 4060 Ti, 16380 MiB, driver 580.178.04 |
| Versiones APT fijadas | El instalador completó la comprobación de las nueve versiones |

El runtime NVIDIA está disponible y el runtime por defecto sigue siendo runc. La prueba GPU pasó con `--gpus` sin cambiar el driver del host.

Informe local de la comprobación: `artifacts/diagnostics/docker-gpu-20261004T203234Z-ME33dN.txt`.

Backup de configuración informado por el instalador: `/var/backups/agent-platform/20261004T203210Z-158073`.

Estado: instalación Docker y visibilidad GPU desde contenedores aprobadas. Falta instalar un servidor de modelos y verificar inferencia real, uso de VRAM, latencia y llamadas a herramientas antes de probar OpenHands.
