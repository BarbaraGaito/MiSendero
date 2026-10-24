# GOES G19: evaluaci?n por horizonte a nivel de sendero

Se evaluaron los clasificadores GOES G19 ya entrenados para 1, 2, 3, 6 y 12 horas, agregando sus scores desde p?xeles a la unidad ruta-sector-hora. La validaci?n sigue siendo diciembre de 2025 y enero de 2026 queda como test reservado. No se volvi? a entrenar ning?n modelo.

| Horizonte | Horas ruta-sector validaci?n | Positivos validaci?n | Selecci?n en validaci?n | Avisos test (0,5 diagn?stico) | TP test | Precisi?n proxy test | Recall proxy test | Episodios de aviso test |
|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | 3439 | 14 | ninguno; mejor 8/11 = 72.7% | 32 | 27 | 84.4% | 22.5% | 8 (7 con detecci?n GOES) |
| 2 | 3300 | 12 | ninguno; mejor 12/3300 = 0.4% | 0 | 0 | n/a | 0.0% | 0 (0 con detecci?n GOES) |
| 3 | 3224 | 13 | ninguno; mejor 2/5 = 40.0% | 0 | 0 | n/a | 0.0% | 0 (0 con detecci?n GOES) |
| 6 | 3088 | 12 | ninguno; mejor 12/3088 = 0.4% | 0 | 0 | n/a | 0.0% | 0 (0 con detecci?n GOES) |
| 12 | 2897 | 7 | ninguno; mejor 7/2897 = 0.2% | 0 | 0 | n/a | 0.0% | 0 (0 con detecci?n GOES) |

La puerta de selecci?n exige precisi?n proxy de 80% y al menos cinco avisos de ruta-hora en validaci?n. Los resultados de test con corte 0,5 son diagn?sticos y no representan un corte operativo seleccionado. En 1 h, el mejor corte elegible en validaci?n obtuvo 8/11 = 72,7%, por debajo del criterio; en los dem?s horizontes tampoco se seleccion? un corte.

Estos resultados eval?an detecciones GOES nominales/altas, no incendios f?sicos confirmados ni la hora de ignici?n. Los intervalos por aviso pueden ser demasiado estrechos por la dependencia temporal; los conteos de episodios reducen, pero no eliminan, esa dependencia. El cruce SNMF independiente tampoco ofrece suficientes eventos cubiertos para estimar precisi?n f?sica. Por eso esta prueba puede comparar horizontes de detecci?n satelital, pero no autoriza alertas de seguridad.

Detalle por horizonte, criterios de cobertura, hashes y limitaciones: [JSON](fire-goes19-short-lead-route-sector-evaluation.json). Modelos congelados: [informe de entrenamiento](fire-goes19-2025q4-2026jan-training-report.json). Reproducci?n: [`evaluate_goes_hourly_route_sector_horizons.py`](../../training/python/evaluate_goes_hourly_route_sector_horizons.py).
