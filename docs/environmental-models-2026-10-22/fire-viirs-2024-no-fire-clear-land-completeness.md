# Cobertura de tierra despejada VIIRS en rutas (2024)

Se calcularon fracciones de tierra despejada en 216 ruta-dias de las ocho rutas y 27 fechas con reporte nacional SNMF sin incendios. Para las fechas faltantes de S-NPP se uso, por ruta-dia, el mejor de NOAA-20 y NOAA-21; no se combinaron pixeles entre sensores.

| Clear-land coverage | Route-days | VIIRS detections | JMA alerts >=0.1 | JMA alerts >=0.5 |
|---:|---:|---:|---:|---:|
| >= 90% | 122 | 0 | 8 | 1 |
| >= 95% | 94 | 0 | 8 | 1 |
| >= 100% | 79 | 0 | 6 | 1 |

En la cohorte no hubo clases VIIRS 7-9 en los sensores disponibles. Al exigir cobertura despejada de al menos 90%, quedan 122 ruta-dias; el JMA congelado dio 8 avisos con corte diagnostico 0.1 y 1 con 0.5. Al exigir 100%, quedan 79 y los conteos son 6 y 1, respectivamente.

Estos casos son no-detecciones observadas por VIIRS, no ausencias fisicas confirmadas. Los avisos discordantes no se cuentan como falsos positivos, la muestra se eligio por reportes nacionales sin incendios y los dias consecutivos se agrupan en 14 bloques. Esta cohorte no estima precision, recall ni prevalencia; sirve para medir cobertura de observacion y decidir que etiquetas pueden considerarse conocidas para el objetivo de deteccion VIIRS.

En otra cohorte seleccionada de 15 ruta-dias con reportes positivos SNMF (16 registros/evento), 15 tuvieron la celda del evento como tierra despejada en todos los sensores. Con >=90% de cobertura del buffer, hubo 13 ruta-dias y VIIRS detecto fuego en 2. La fecha reportada no fija la hora de actividad durante el paso, asi que esto es coincidencia, no sensibilidad definitiva ni falsos negativos.

Resultados reproducibles: [JSON con resultados ruta-dia y hashes](fire-viirs-2024-no-fire-clear-land-completeness.json). Fuentes: [auditoria S-NPP de las ocho rutas](fire-viirs-jma-2024-explicit-no-fire-all-routes.json), [relleno NOAA-20/21](fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json) y [cohorte positiva SNMF](fire-viirs-daily-l3-snmf-event-audit-2023-2025.json). Script: [`evaluate_viirs_2024_clear_land_completeness.py`](../../training/python/evaluate_viirs_2024_clear_land_completeness.py).
