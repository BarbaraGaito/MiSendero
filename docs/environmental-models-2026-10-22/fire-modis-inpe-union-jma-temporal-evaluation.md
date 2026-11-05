# Evaluación temporal MODIS + INPE

Entrenamiento 2022, selección del umbral en 2023 y test temporal 2024-2026. Ningún umbral de validación alcanzó el criterio de 90% de precisión con al menos cinco alertas; 0,5 es solo un diagnóstico fijo.

Dataset unificado reproducible (archivo privado local): `training/data/environmental/private/argentina-route-fire-evidence-jma-unified-2022-2026.csv.gz`; SHA-256 `b9473bde6222d6d4dc964d0b72392231193bf4b8f17905ecad07fcdff50535ae`. Manifiesto: `training/data/environmental/private/argentina-route-fire-evidence-jma-unified-2022-2026-manifest.json`.

Métricas por ruta-día: {"route_days": 10300, "positive_route_days": 44, "prevalence": 0.004271844660194175, "threshold": 0.5, "alerts": 2111, "true_positives": 6, "false_positives": 2105, "false_negatives": 38, "precision": 0.0028422548555187117, "precision_wilson_one_sided_95_lower_bound_independent_days": 0.00147045776625998, "recall": 0.13636363636363635, "average_precision": 0.004513474520866216, "brier": 0.1395194967226668, "confusion_matrix_tn_fp_fn_tp": [8151, 2105, 38, 6]}.

Métricas agrupadas por fecha: {"prevalence": 0.07537688442211055, "threshold": 0.5, "alerts": 366, "true_positives": 30, "false_positives": 336, "false_negatives": 0, "precision": 0.08196721311475409, "precision_wilson_one_sided_95_lower_bound_independent_days": 0.06133703633916178, "recall": 1.0, "average_precision": 0.2225188301875238, "brier": 0.5314556959575872, "confusion_matrix_tn_fp_fn_tp": [32, 336, 0, 30], "event_dates": 398, "positive_event_dates": 30}; límite inferior Wilson unilateral 95% descriptivo de precisión: 0.06133703633916178.

INPE AMS referencia Aqua/MODIS; por eso su coincidencia con MOD14A1 no cuenta como confirmación independiente. Son detecciones satelitales, no verdad exhaustiva de incendios físicos. No se generó dataset sintético ni artefacto para la app.
