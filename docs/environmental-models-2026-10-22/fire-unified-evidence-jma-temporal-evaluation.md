# Prueba temporal con evidencia de fuego unificada

El objetivo es predecir evidencia de incendio registrada por al menos una fuente unificada cerca de una ruta en la fecha objetivo. Entrenamiento: 2023. Test temporal: 2024-octubre de 2026. El umbral 0,5 se fijó como diagnóstico y no se ajustó con el test.

El test contiene 254 ruta-fechas, 30 ruta-fechas positivas en 29 fechas y negativos de 28 fechas explícitas de no-fuego SNMF.

Métricas por ruta-fecha: {"observations": 254, "positive_observations": 30, "threshold": 0.5, "alerts": 73, "true_positives": 17, "false_positives": 56, "false_negatives": 13, "precision": 0.2328767123287671, "recall": 0.5666666666666667, "average_precision": 0.34740801492859136, "confusion_matrix_tn_fp_fn_tp": [168, 56, 13, 17]}.

Métricas agrupadas por fecha-evento: {"observations": 57, "positive_observations": 29, "threshold": 0.5, "alerts": 43, "true_positives": 16, "false_positives": 27, "false_negatives": 13, "precision": 0.37209302325581395, "recall": 0.5517241379310345, "average_precision": 0.49482247895784875, "confusion_matrix_tn_fp_fn_tp": [1, 27, 13, 16]}; límite inferior Wilson unilateral 95% de precisión: 0.2618185930475275.

Las métricas describen evidencia registrada, no probabilidad de fuego físico. La independencia entre fuentes es parcial y los negativos oficiales no prueban ausencia de incendios no reportados. El JSON contiene hashes, linaje, predicciones y conteos por fecha.
