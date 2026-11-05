# Relleno con VIIRS NOAA-20/21 de los dos huecos de S-NPP (2024)

Se descargaron y verificaron 20 granulas (20 archivos; 3.97 MB) de VJ114A1/NOAA-20 y VJ214A1/NOAA-21 para las cinco tiles de las fechas 31/05 y 10/07. Las 16 combinaciones ruta-fecha faltantes en S-NPP ahora tienen observaciones de ambos sensores.

En esas 16 ruta-fechas, NOAA-20 tuvo 0 detecciones clase 7–9 y NOAA-21 tuvo 0. En el conjunto combinado, 14/16 tuvieron al menos una muestra clase 5 con QA de tierra. Esto es observación parcial, no garantía de ausencia física.

La única alerta JMA de corte 0,1 en esos días queda cubierta por las dos pasadas diarias; ninguna registró una detección 7–9 a menos de 10 km. El corte no es una probabilidad calibrada, la etiqueta SNMF es administrativa y los sensores VIIRS no son verdad de campo. No se estima precisión ni recall.

Ver los [resultados reproducibles](fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json), [manifiesto público](fire-viirs-daily-l3-jma-2024-cmr-gap-fill-noaa20-21-manifest.json), [adquisidor](../../training/python/acquire_viirs_daily_l3_jma_2024_cmr_gaps.py) y [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_cmr_gaps.py). La guía metodológica está en la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).
