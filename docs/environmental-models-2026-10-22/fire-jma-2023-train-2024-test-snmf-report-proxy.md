# Prueba temporal JMA GSM: entrenar en 2023 y probar en 2024

Se entrenó una regresión logística balanceada con los pronósticos JMA GSM de julio-diciembre de 2023 y se congeló para todo 2024. La etiqueta es si un parte SNMF registra un incidente cerca del sector ese día; no equivale a una medición completa de incendios físicos. No se eligió ningún umbral usando el año de prueba.

El entrenamiento tuvo 952 ruta-días y solo 5 positivos. El test tuvo 2218 ruta-días y 9 positivos en 8 secuencias ruta-temporales. La precisión promedio (average precision) fue 0.0096, frente a prevalencia 0.0041; el Brier fue 0.0311, frente al baseline constante de entrenamiento 0.0040.

| Corte diagnóstico | Alertas | Positivos detectados / 9 | Precisión del proxy | Recall del proxy |
|---:|---:|---:|---:|---:|
| 0.1 | 219 | 2/9 | 0.9% | 22.2% |
| 0.2 | 146 | 0/9 | 0.0% | 0.0% |
| 0.3 | 108 | 0/9 | 0.0% | 0.0% |
| 0.5 | 73 | 0/9 | 0.0% | 0.0% |
| 0.7 | 54 | 0/9 | 0.0% | 0.0% |
| 0.8 | 46 | 0/9 | 0.0% | 0.0% |
| 0.9 | 32 | 0/9 | 0.0% | 0.0% |

En las 27 fechas 2024 con parte que declara explícitamente cero incendios nacionales, el modelo tuvo cobertura para 216/216 ruta-días. A corte 0,5 alertó en 1 ruta-días negativos; a 0,9 no alertó en ninguno, pero tampoco obtuvo recall útil en el conjunto de prueba.

La mejora de ranking sobre la prevalencia no basta: los positivos son muy escasos, el Brier se compara con el baseline y los cortes diagnósticos producen muchos falsos avisos o casi ningún acierto. No se puede afirmar precisión fiable ni probabilidad calibrada para detectar fuego físico en trekking. El SNMF describe el reporte diario como estado de situación de incendios registrados, no como censo exhaustivo ([fuente oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)).

Resultados con hashes en [JSON](fire-jma-2023-train-2024-test-snmf-report-proxy.json); reproducción con [`evaluate_jma_2023_to_2024_snmf_fire_transfer.py`](../../training/python/evaluate_jma_2023_to_2024_snmf_fire_transfer.py).
