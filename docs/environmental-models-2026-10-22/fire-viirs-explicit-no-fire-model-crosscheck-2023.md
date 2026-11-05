# Cruce de avisos MODIS congelados con VIIRS en cuatro fechas SNMF sin incendios reportados (2023)

Se verificaron **20 granulos** VNP14A1 (Suomi-NPP; 4.32 MB) y se cruzaron con los **22 ruta-dias** cubiertos del test MODIS congelado.

| Modelo (score máximo >= 0,5) | Avisos | Avisos con VIIRS clase 7–9 en buffer de 10 km |
|---|---:|---:|
| persistence | 0 | 0 |
| logistic | 5 | 0 |
| random_forest | 0 | 0 |
| xgboost | 4 | 0 |

VIIRS encontró detecciones clase 7–9 en 0 de los 22 ruta-días cubiertos. Hubo al menos un píxel clase 5 con QA de tierra en 20/22 buffers; los otros 2 no tuvieron ni siquiera ese nivel parcial de observación clara. Entre las 6 fechas-ruta únicas con score >=0,5 de logística o XGBoost, 5 tuvieron píxeles clase 5 y ninguna tuvo una detección VIIRS.

El SNMF declaró que no había incendios reportados a nivel nacional; esa frase no prueba ausencia física. Una detección VIIRS puede ser otro tipo de anomalía térmica y un buffer sin detección no es un negativo observado completo. Aun los píxeles clase 5 solo describen las celdas observadas, no el buffer entero. El cruce es solo una comprobación independiente de los avisos congelados; no justifica llamarlos verdaderos/falsos ni calcula precisión.

El test y los umbrales no se modificaron. Fuentes y hashes: [resultado JSON](fire-viirs-explicit-no-fire-model-crosscheck-2023.json), [manifiesto de granulos](fire-viirs-daily-l3-explicit-no-fire-2023-manifest.json), [script de adquisición](../../training/python/acquire_viirs_daily_l3_national_no_fire_2023.py) y [auditor reproducible](../../training/python/audit_viirs_daily_l3_explicit_no_fire_2023.py). Clases y QA según la [guía oficial NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf).
