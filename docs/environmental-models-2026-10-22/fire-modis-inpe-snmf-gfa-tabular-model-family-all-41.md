# Comparación de modelos tabulares con fuentes unificadas all-41

Se compararon 9 configuraciones. El criterio fue maximizar la precisión en validación con al menos 5 alertas. Modelo seleccionado: random_forest_leaf_30; precisión/recall de validación: 0.571/0.071; gate 90%: no aprobado.

En el test temporal 2024-2026 al umbral elegido en validación: {"threshold": 0.7085803863035262, "observations": 10300, "positives": 65, "alerts": 10, "true_positives": 0, "false_positives": 10, "false_negatives": 65, "precision": 0.0, "precision_wilson_lower_95_descriptive": 0.0, "recall": 0.0, "average_precision": 0.009158333831476871, "brier": 0.09448128767664611}.

Diagnóstico test a 0,5: {"threshold": 0.5, "observations": 10300, "positives": 65, "alerts": 808, "true_positives": 3, "false_positives": 805, "false_negatives": 62, "precision": 0.0037128712871287127, "precision_wilson_lower_95_descriptive": 0.001484788813441436, "recall": 0.046153846153846156, "average_precision": 0.009158333831476871, "brier": 0.09448128767664611}. El JSON guarda parámetros y métricas de todos los candidatos.

VGG19/YOLO son modelos de imagen y no corresponden a estas variables tabulares. El objetivo es evidencia registrada, no probabilidad exhaustiva de incendio físico.
