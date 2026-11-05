# VIIRS diario en las ocho rutas durante partes SNMF sin incendios reportados (2024)

Se auditaron 200 de 216 ruta-días posibles, usando 125 granulas VNP14A1 descargadas y verificadas (26.12 MB). NASA CMR no devolvió un tile exacto en dos fechas; sus 16 ruta-días quedan desconocidos.

VIIRS mostró clase 7–9 en 0/200 buffers observados. 186/200 tuvieron alguna muestra clase 5 con QA de tierra, una observación parcial. Entre las alertas del modelo al umbral diagnóstico fijo de 0.1, se observaron 10 y 0 tuvieron detección VIIRS; los scores no son probabilidades calibradas.

Los partes SNMF declaran que no se reportaron incendios, pero no certifican ausencia física. La falta de detecciones VIIRS tampoco es un negativo completo. Este análisis caracteriza la cobertura de observación y la correspondencia con un umbral diagnóstico; no mide precisión, recall ni validez de pronóstico.

Ver el [JSON reproducible](fire-viirs-jma-2024-explicit-no-fire-all-routes.json), [manifiesto público de hashes](fire-viirs-daily-l3-jma-2024-no-fire-all-routes-manifest.json), [adquisidor](../../training/python/acquire_viirs_daily_l3_jma_2024_no_fire_all_routes.py) y [auditor](../../training/python/audit_viirs_daily_l3_jma_2024_no_fire_all_routes.py). Las clases y QA siguen la [guía NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).

## Complemento de las fechas sin cobertura S-NPP

El 31/05 y el 10/07 también se consultaron con NOAA-20 y NOAA-21. Ambos sensores devolvieron las cinco tiles necesarias, con dos productos diarios para cada uno de los 16 ruta-días antes faltantes. No hubo detecciones clase 7–9; 14/16 ruta-días tuvieron alguna muestra clase 5 con QA de tierra. El único aviso JMA en esas fechas quedó cubierto por ambos sensores, sin muestra clase 5 ni detección térmica en su buffer. Esto completa la disponibilidad de producto diario en las 216 ruta-fechas, pero no certifica ausencia de fuego: incluso la máscara clase 5 solo da cobertura parcial.

Ver el [análisis del complemento NOAA-20/21](fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.md) y su [JSON con resultados y hashes](fire-viirs-jma-2024-cmr-gap-fill-noaa20-21.json).
