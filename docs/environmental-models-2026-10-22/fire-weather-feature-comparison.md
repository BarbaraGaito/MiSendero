# Aporte de pronósticos JMA a la detección diaria MODIS

Comparación exploratoria con el protocolo MOD14A1 congelado: XGBoost con variables históricas del píxel frente al mismo XGBoost más temperatura, humedad, viento y precipitación pronosticados por JMA GSM para la fecha objetivo. La etiqueta conserva FireMask y QA del producto real.

El conjunto se cruzó con 5840 filas región-fecha de pronóstico archivado; quedaron 1579922 ejemplos MODIS válidos. Los cortes temporal y geográfico se heredan del protocolo original. La selección se hace solo con validación; las métricas test se informan una vez.

El candidato elegido por average precision de validación en agregación región-día es `xgboost_plus_jma_24h_forecast`. Validación píxel-día: baseline AP=0.00132527, con tiempo AP=0.00360798. Validación región-día: baseline AP=0.133044, con tiempo AP=0.240324.

Prueba temporal baseline: {"observations": 341975, "positive_observations": 31, "threshold": 0.5, "alerts": 12881, "true_positives": 1, "false_positives": 12880, "false_negatives": 30, "precision": 7.763372408974459e-05, "recall": 0.03225806451612903, "average_precision": 0.0001484904960817636, "brier": 0.02967576860312025, "confusion_matrix_tn_fp_fn_tp": [329064, 12880, 30, 1]}

Prueba temporal con JMA: {"observations": 341975, "positive_observations": 31, "threshold": 0.5, "alerts": 8079, "true_positives": 2, "false_positives": 8077, "false_negatives": 29, "precision": 0.00024755539051862855, "recall": 0.06451612903225806, "average_precision": 0.0003039312774654028, "brier": 0.02137686822271666, "confusion_matrix_tn_fp_fn_tp": [333867, 8077, 29, 2]}

Prueba geográfica baseline: {"observations": 188950, "positive_observations": 3, "threshold": 0.5, "alerts": 0, "true_positives": 0, "false_positives": 0, "false_negatives": 3, "precision": 0.0, "recall": 0.0, "average_precision": 2.3995009038120072e-05, "brier": 9.134548548912691e-05, "confusion_matrix_tn_fp_fn_tp": [188947, 0, 3, 0]}

Prueba geográfica con JMA: {"observations": 188950, "positive_observations": 3, "threshold": 0.5, "alerts": 0, "true_positives": 0, "false_positives": 0, "false_negatives": 3, "precision": 0.0, "recall": 0.0, "average_precision": 2.5296639086479273e-05, "brier": 0.00010610287412708812, "confusion_matrix_tn_fp_fn_tp": [188947, 0, 3, 0]}

Prueba temporal región-día, modelo elegido: {"observations": 1013, "positive_observations": 16, "threshold": 0.5, "alerts": 107, "true_positives": 7, "false_positives": 100, "false_negatives": 9, "precision": 0.06542056074766354, "recall": 0.4375, "average_precision": 0.07811564895001756, "brier": 0.08521267693914836, "confusion_matrix_tn_fp_fn_tp": [897, 100, 9, 7], "threshold_source": "fixed_0.5_diagnostic_no_validation_threshold"}

Prueba geográfica región-día, modelo elegido: {"observations": 683, "positive_observations": 2, "threshold": 0.5, "alerts": 0, "true_positives": 0, "false_positives": 0, "false_negatives": 2, "precision": 0.0, "recall": 0.0, "average_precision": 0.005446142070711531, "brier": 0.0029817172313345614, "confusion_matrix_tn_fp_fn_tp": [681, 0, 2, 0], "threshold_source": "fixed_0.5_diagnostic_no_validation_threshold"}

Estas son métricas de píxel-día para detección MODIS, no precisión de incendio por sendero. La base mantiene pocos positivos independientes, por lo que una mejora numérica no justificaría por sí sola alertas de seguridad. El JSON incluye hashes, particiones, reglas de selección y límites.
