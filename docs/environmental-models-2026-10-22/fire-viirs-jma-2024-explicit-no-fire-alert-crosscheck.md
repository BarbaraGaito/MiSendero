# Cruce de alertas JMA 2024 con VIIRS en fechas SNMF sin incendios reportados

El test JMA congelado emitió 11 alertas en fechas con parte nacional explícito sin incendios, al corte diagnóstico fijo de 0.1. Se verificaron 10 granulas VIIRS para 10 alertas; una alerta de Condorito del 10/07/2024 quedó sin cobertura porque CMR no devolvió ese tile.

VIIRS encontró detecciones FireMask 7–9 en 0/10 alertas observadas. 10/10 tuvieron al menos una muestra clase 5 con QA de tierra; la cobertura restante no debe interpretarse como ausencia de fuego.

La detección térmica puede ser independiente y útil para contrastar, pero no adjudica incendios forestales. Los días sin detección no son negativos observados completos. El parte nacional tampoco demuestra ausencia física. Este cruce no estima precisión ni valida una predicción de ignición; el corte 0,1 es diagnóstico y los scores no son probabilidades calibradas.

Los datos y hashes quedan en el manifiesto reproducible; el análisis usa el test JMA y las geometrías existentes sin reentrenar ni modificar umbrales. Ver el [resultado JSON](fire-viirs-jma-2024-explicit-no-fire-alert-crosscheck.json), el [manifiesto público](fire-viirs-daily-l3-jma-2024-no-fire-alerts-manifest.json), el [script de adquisición](../../training/python/acquire_viirs_daily_l3_jma_2024_no_fire_alerts.py) y el [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_no_fire_alerts.py). Las clases siguen la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).
