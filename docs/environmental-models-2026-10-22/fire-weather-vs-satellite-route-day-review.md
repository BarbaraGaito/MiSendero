# Comparación pareada WRF y XGBoost por ruta y día

Se compararon los modelos congelados sobre los mismos días y píxeles de la prueba temporal julio-diciembre de 2023. Se alineó la etiqueta con el día de observación MODIS: el campo `target_at` del modelo XGBoost marca el fin exclusivo de la ventana de 24 horas, así que el día de etiqueta es `target_at - 1 día`. Después se resumió cada ruta-sector y fecha con el máximo de los scores y una etiqueta positiva si algún pixel muestreado tenía detección MODIS.

La cohorte común contiene 1.013 ruta-días y 16 positivos. No hubo desacuerdos entre etiquetas en los 341.975 pixel-días emparejados.

| Modelo (corte diagnóstico 0,5) | Avisos | Coincidencias MODIS | Avisos sin etiqueta positiva MODIS | Precisión proxy | Recall proxy | AP por ruta-día |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| XGBoost, historial satelital | 267 | 12 | 255 | 4,49% | 75,0% | 0,1053 |
| WRF, solo clima | 528 | 15 | 513 | 2,84% | 93,8% | 0,0546 |

El WRF recupera tres de los cuatro ruta-días positivos que XGBoost no detectó, pero emite 261 avisos adicionales sin una etiqueta MODIS positiva. Su precisión proxy y su ranking AP son peores. Los avisos sin etiqueta no se consideran incendios falsos confirmados: MODIS puede omitir incendios. Aun con esa limitación favorable al WRF, la prueba no respalda una mejora de precisión.

En validación, el WRF tampoco encontró un corte con 90% de precisión proxy y al menos cinco avisos. Su mejor precisión con ese mínimo fue 5/118 = 4,24%, por lo que no hay umbral operativo seleccionado. El corte 0,5 de esta comparación es solo diagnóstico; ninguno de los resultados equivale a una probabilidad de incendio.

El JSON reproducible es [`fire-weather-vs-satellite-route-day-test.json`](fire-weather-vs-satellite-route-day-test.json); se generó con [`compare_fire_weather_and_satellite_route_days.py`](../../training/python/compare_fire_weather_and_satellite_route_days.py). El experimento de selección WRF original está en [`fire-smn-wrf-modis-evaluation.json`](fire-smn-wrf-modis-evaluation.json). No se habilitó ningún modelo en la app.
