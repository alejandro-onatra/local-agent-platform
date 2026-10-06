# Segunda prueba: reparar un bug con tests existentes

## Objetivo

Evaluar que OpenHands use resultados de tests para diagnosticar y corregir un bug. El modelo no cambia. Mantener un agente, perfil local fijo y subagentes desactivados. Este ejercicio usa importes monetarios sintéticos como problema de programación; no es un sistema financiero ni calcula transacciones reales.

Los fixtures originales están en `exercises/bugfix/`. La tarea de preparación copia dos archivos a `artifacts/openhands/projects/bugfix`, que el agente ve como `/projects/bugfix`. No se modifica la demo anterior ni se concede acceso al repositorio completo.

## Preparar y comprobar fallo previo

Desde el host, con OpenHands arrancado:

```bash
mise exec -- task openhands:bugfix:prepare
```

El resultado esperado incluye tres tests fallidos y dos correctos. La tarea devuelve éxito únicamente si esos tres fallos concretos aparecen, sin errores de importación ni tests omitidos. Es una baseline deliberadamente defectuosa. No entregar la reparación al agente antes de observar la baseline.

La preparación se niega a sobrescribir una carpeta existente. Si quedó creada pero el contenedor no estaba disponible, arrancar OpenHands y ejecutar `task openhands:bugfix:baseline`. No borrar ni reiniciar el ejercicio una vez reparado.

## Tarea para OpenHands

Crear una conversación nueva con el perfil local activo. Pegar:

> Trabaja únicamente en /projects/bugfix. Ejecuta pwd y los tests con python -m unittest -v. Hay un bug en discounts.py: discounted_total(subtotal, discount_percent) debe aplicar un descuento porcentual entre 0 y 100, devolver Decimal redondeado a dos decimales con ROUND_HALF_UP y rechazar entradas inválidas. Usa los fallos para diagnosticar el problema y modifica únicamente discounts.py. No cambies test_discounts.py ni omitas tests. Ejecuta de nuevo los tests y resume causa, cambio y resultados antes/después. No descargues dependencias ni accedas a Internet. Indica explícitamente /projects/bugfix como directorio en las acciones de terminal.

La interfaz puede elegir otra carpeta inicial; la primera acción debe confirmar la ruta real de terminal y pasar explícitamente al workspace indicado. No aceptar únicamente una explicación sin eventos de herramientas.

## Comprobar reparación

Al terminar:

```bash
mise exec -- task openhands:bugfix:check
```

La aceptación compara byte a byte los tests del workspace con los originales del repositorio, ejecuta los cinco casos y verifica adicionalmente descuento fraccionario, cero, redondeo y tipo Decimal. Todo el código del ejercicio se ejecuta dentro del contenedor, no en el host. El checker no corrige la solución.

El resultado esperado es cinco tests originales exitosos y cuatro comprobaciones adicionales exitosas. Esto reduce el riesgo de aceptar una reparación que solo encaje con los ejemplos dados. No demuestra seguridad completa ni que el agente no haya escrito otros archivos: revisar también sus eventos y cambios.

## Registro

Compartir baseline, aceptación y resumen final del agente. Registrar tiempo aproximado, intentos y errores de herramientas si están disponibles. El ejercicio está preparado; la ejecución real con OpenHands queda pendiente. Las pruebas locales del fixture confirman el fallo inicial y que una reparación de referencia en una copia temporal cumple la aceptación; esa reparación no se entrega al workspace del usuario.

## Resultado compartido — 5 de octubre de 2026

El usuario ejecutó `task openhands:bugfix:check`: los cinco tests originales pasaron, sin modificaciones según la comparación previa del script, y las cuatro comprobaciones adicionales de tipo Decimal, descuento y redondeo también pasaron. Esto valida la reparación funcional presente en el workspace. No se volvió a ejecutar desde Work.

Durante la tarea, el agente envió una llamada `file_editor` con `command=str_replace` sin el parámetro obligatorio `path`, e incluyó `file_text`. La validación de la herramienta rechazó la llamada. Se proporcionó al usuario un prompt de recuperación que indicaba la ruta y los campos correctos; posteriormente compartió la aceptación satisfactoria. No afirmar recuperación autónoma: hubo intervención humana y no se revisó el historial completo de herramientas.

La baseline de los fixtures se verificó localmente antes de entregarlos (tres fallos esperados y dos aciertos). No se recibió la salida de baseline ejecutada en el host; por ello el registro de antes/después en el host no está completo. Tampoco se midieron tiempo total o número de intentos.

Conclusión del experimento: OpenHands y Qwen3 local pueden resolver este bug sintético con guía. El uso consistente de esquemas de herramientas sigue siendo una limitación observada. Próximo paso: registrar ejecuciones, errores de herramientas e intervenciones para evaluar la autonomía y preparar observabilidad.
