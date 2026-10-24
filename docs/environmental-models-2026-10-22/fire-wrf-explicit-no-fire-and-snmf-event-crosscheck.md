# Cruce WRF con partes nacionales sin incendios y eventos SNMF

Se cruzaron las predicciones congeladas del modelo meteorológico WRF contra los días 2023 cuyos partes SNMF dicen explícitamente que no hubo incendios reportados en el país y contra los cuatro días-sector positivos del test externo de 2025. El modelo fue entrenado antes de 2023; el umbral 0,5 es solo diagnóstico y el otro umbral es el de mayor precisión en validación con al menos cinco alertas. Ningún umbral pasó la puerta de validación de precisión del 90%.

| Umbral | Alertas en negativos nacionales cubiertos | Eventos positivos detectados |
|---|---:|---:|
| 0.500 (diagnostic_0_5) | 5/23 ruta-días | 0/4 |
| 0.725 (best_validation_precision_with_minimum_5_alerts) | 0/23 ruta-días | 0/4 |

Con el umbral 0,5 hubo alertas en días donde el parte oficial nacional no reportó incendios y el modelo no avisó ante ninguno de los cuatro eventos positivos evaluados. El umbral más alto evitó alertas en ambos grupos, incluidos todos los positivos; no constituye una mejora útil.

Las cohortes son pequeñas y seleccionadas, con negativos de 2023 y positivos de 2025. Este cruce no estima precisión de producción ni prueba ausencia física de fuego. Aun así, junto con la puerta de validación fallida y los resultados externos, descarta este modelo WRF como candidato a una alerta fiable para trekking.

Resultados con hashes en [JSON](fire-wrf-explicit-no-fire-and-snmf-event-crosscheck.json); reproducción con [`evaluate_wrf_model_explicit_no_fire_vs_snmf_2025.py`](../../training/python/evaluate_wrf_model_explicit_no_fire_vs_snmf_2025.py).
