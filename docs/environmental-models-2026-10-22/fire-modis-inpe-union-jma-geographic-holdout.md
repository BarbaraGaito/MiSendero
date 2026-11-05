# Validación geográfica y temporal del dataset unificado

Se reservaron grupos completos de rutas próximas (distancia entre trazados muestreados ≤100 km). Cada pliegue entrenó con rutas de otros grupos en 2022, seleccionó umbral en 2023 y probó rutas reservadas en 2024-2026. El corte 0,5 se muestra solo como diagnóstico.

Pliegues puntuados: 15 de 15; solo 3 grupos tuvieron evidencia positiva en el test y 0 encontraron un umbral de validación que cumpliera el gate. Métricas agregadas ruta-día: {"prevalence": 0.004271844660194175, "threshold": 0.5, "alerts": 2288, "true_positives": 8, "false_positives": 2280, "false_negatives": 36, "precision": 0.0034965034965034965, "precision_wilson_one_sided_95_lower_bound_independent_days": 0.0019712510218439436, "recall": 0.18181818181818182, "average_precision": 0.00450500968863635, "brier": 0.14657348740763854, "confusion_matrix_tn_fp_fn_tp": [7976, 2280, 36, 8], "observations": 10300, "positive_observations": 44}.

Métricas agrupadas por fecha: {"prevalence": 0.07537688442211055, "threshold": 0.5, "alerts": 377, "true_positives": 30, "false_positives": 347, "false_negatives": 0, "precision": 0.07957559681697612, "precision_wilson_one_sided_95_lower_bound_independent_days": 0.05953087689401899, "recall": 1.0, "average_precision": 0.10084545648325095, "brier": 0.5110128220193372, "confusion_matrix_tn_fp_fn_tp": [21, 347, 0, 30], "event_dates": 398, "positive_event_dates": 30}; límite inferior Wilson descriptivo: 0.05953087689401899.

Esta prueba reduce la contaminación geográfica entre rutas cercanas, pero los bloques son aproximaciones espaciales y la etiqueta no es verdad exhaustiva del fuego físico. Consultar el JSON para tamaños de pliegue, regiones, umbrales y linaje de fuentes.
