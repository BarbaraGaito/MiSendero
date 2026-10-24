# Comparación temporal JMA: entrenamiento 2023, validación 2024 y test 2025

Se compararon tres modelos con cortes cronológicos estrictos. Los modelos se entrenaron solo con 2023; el corte se eligió solo en 2024; 2025 quedó como test final. La etiqueta es un incendio publicado por SNMF en un radio regional de 20 km desde el centro del sector, no una observación completa de fuego físico.

El entrenamiento tuvo 958 ruta-días y 36 positivos. La validación tuvo 2219 ruta-días, 52 positivos en 22 secuencias. El test de 2025 tuvo 1657 ruta-días y 60 positivos en 17 secuencias.

| Modelo | Precisión máxima validación (≥5 alertas) | Corte de validación | Pasó 80% | Precisión test 2025 en corte validado | Recall test | Alertas test |
|---|---:|---:|:---:|---:|---:|---:|
| logistic_regression | 40.0% | 0.933 | No | 0.0% | 0.0% | 8 |
| random_forest | 60.0% | 0.692 | No | 33.3% | 1.7% | 3 |
| xgboost | 60.0% | 0.884 | No | 0.0% | 0.0% | 6 |

Ningún modelo alcanzó 80% de precisión en validación. En el test final, el mejor corte validado no generalizó: logística y XGBoost detectaron 0 eventos positivos; Random Forest detectó 1 de 60 con 3 alertas y precisión del proxy de 33,3%. Ningún candidato es aceptable como alerta fiable. El corte de 2025 no se ajustó.

Solo hubo un parte nacional explícito sin incendios en 2025, por lo que esa comprobación negativa tampoco mide una tasa de falsas alarmas estable. Los partes SNMF reflejan eventos reportados por jurisdicciones ([fuente oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)). Hace falta ampliar observaciones independientes y sensor-cubiertas antes de estimar rendimiento para fuego físico.

Los conteos de etiquetas se comprueban contra las auditorías archivadas antes de entrenar. Resultados y hashes en [JSON](fire-jma-model-family-2023-2025-transfer-test.json); reproducción con [`evaluate_jma_model_family_transfer_2025.py`](../../training/python/evaluate_jma_model_family_transfer_2025.py).
