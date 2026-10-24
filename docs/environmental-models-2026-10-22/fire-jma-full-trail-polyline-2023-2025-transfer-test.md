# Prueba JMA con polilineas completas (2023-2025)

Se usaron trazados completos de ocho senderos y radios de 10 y 20 km. La separacion temporal es entrenamiento 2023, validacion 2024 y test intacto 2025. El objetivo son partes SNMF, no incendios fisicos confirmados.

## Radio 10 km

| Ano | Ruta-dias conocidos | Positivos | Clusters positivos |
|---:|---:|---:|---:|
| 2023 | 952 | 5 | 4 |
| 2024 | 2218 | 9 | 8 |
| 2025 | 1657 | 33 | 7 |

| Modelo | Precision validacion (>=5 alertas) | Pasa 80% | Aciertos test / positivos | Alertas test | Precision proxy test |
|---|---:|:---:|---:|---:|---:|
| logistic_regression | 1.2% | No | 19/33 | 488 | 3.9% |
| random_forest | 1.1% | No | 16/33 | 330 | 4.8% |
| xgboost | 1.0% | No | 15/33 | 354 | 4.2% |

| Modelo | Dias-ruta sin fuego reportado (2024) | Avisos a 0.5 | Avisos a 0.9 |
|---|---:|---:|---:|
| logistic_regression | 216/216 | 1 | 0 |
| random_forest | 216/216 | 0 | 0 |
| xgboost | 216/216 | 0 | 0 |

## Radio 20 km

| Ano | Ruta-dias conocidos | Positivos | Clusters positivos |
|---:|---:|---:|---:|
| 2023 | 958 | 40 | 20 |
| 2024 | 2219 | 84 | 27 |
| 2025 | 1657 | 60 | 17 |

| Modelo | Precision validacion (>=5 alertas) | Pasa 80% | Aciertos test / positivos | Alertas test | Precision proxy test |
|---|---:|:---:|---:|---:|---:|
| logistic_regression | 40.0% | No | 0/60 | 8 | 0.0% |
| random_forest | 21.4% | No | 4/60 | 17 | 23.5% |
| xgboost | 38.5% | No | 2/60 | 20 | 10.0% |

| Modelo | Dias-ruta sin fuego reportado (2024) | Avisos a 0.5 | Avisos a 0.9 |
|---|---:|---:|---:|
| logistic_regression | 216/216 | 37 | 0 |
| random_forest | 216/216 | 1 | 0 |
| xgboost | 216/216 | 7 | 0 |

Ningun modelo alcanzo 80% de precision en validacion. En 20 km, Random Forest obtuvo 4/17 alertas correctas (23.5%) en el test de 2025 al corte elegido en 2024; en 10 km, Logistic Regression obtuvo 19/488 (3.9%). En los 216 dias-ruta de partes nacionales explicitamente sin fuego en 2024, a umbral 0.5 hubo 37 avisos con logistica, uno con Random Forest y siete con XGBoost para 20 km. A 0.9 no hubo avisos en los partes sin fuego; en el test 2025, el mayor recall a ese corte fue 7/60 ruta-dias positivos (logistica), mientras Random Forest no emitio alertas. Los radios amplios son avisos regionales, no distancia sobre el sendero. Estas metricas miden el proxy administrativo SNMF, no precision de fuego fisico.

Resultados con hashes en [JSON](fire-jma-full-trail-polyline-2023-2025-transfer-test.json); reproduccion con [`evaluate_jma_full_trail_polyline_transfer_2025.py`](../../training/python/evaluate_jma_full_trail_polyline_transfer_2025.py).
