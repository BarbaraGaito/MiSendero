# Cruce FIRMS VIIRS y partes SNMF, ventanas de eventos 2025

Se consultaron 28 ventanas del sensor VIIRS SNPP alrededor de 60 ruta-dias positivos SNMF a 20 km. La consulta dirigida produjo 488 filas de focos en 11 ruta-dias unicos.

Hubo coincidencia el mismo dia en 10/60 ruta-dias positivos SNMF (16.7%, descriptivo). En 11 hubo una deteccion en la ventana de mas o menos un dia.

| Confianza FIRMS | Filas | Ruta-dias con deteccion | Coincidencias exactas con SNMF positivo |
|---|---:|---:|---:|
| h | 45 | 4 | 4 |
| n | 414 | 10 | 9 |
| l | 29 | 4 | 4 |

Esta cohorte se eligio a partir de eventos SNMF, por lo que no sirve para estimar precision, falsos positivos ni rendimiento general. Un hotspot cercano el mismo dia tampoco confirma que sea el mismo incidente. No se crearon negativos: las ausencias de FIRMS siguen siendo desconocidas.

El archivo de detecciones se conserva en el directorio privado local y no se incluye en el repositorio. Sus hashes, el plan de ventanas y las fuentes SNMF quedan registrados en el [JSON](fire-firms-snmf-event-window-crosscheck-2025.json). Reproduccion del resumen: [`evaluate_firms_snmf_event_window_crosscheck_2025.py`](../../training/python/evaluate_firms_snmf_event_window_crosscheck_2025.py).
