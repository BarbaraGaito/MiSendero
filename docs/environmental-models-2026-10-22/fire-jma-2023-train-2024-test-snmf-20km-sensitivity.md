# JMA GSM: sensibilidad de la prueba 2023→2024 a 20 km

Se repitió el protocolo anual JMA GSM con el radio de sensibilidad de 20 km del auditor SNMF. Este radio representa proximidad regional desde el centro del sector; no equivale a estar sobre el sendero. Las etiquetas se reconstruyeron desde los PDF/eventos y los conteos se verificaron contra las auditorías 20 km existentes.

El modelo tuvo 958 ruta-días y 36 positivos para entrenar, y 2219 ruta-días con 52 positivos en el test de 2024. Average precision: 0.0880 frente a prevalencia 0.0234; Brier: 0.1584 frente al baseline constante 0.0231.

| Corte diagnóstico | Alertas | Positivos detectados / 52 | Precisión del proxy | Recall del proxy |
|---:|---:|---:|---:|---:|
| 0.1 | 1102 | 41/52 | 3.7% | 78.8% |
| 0.2 | 981 | 39/52 | 4.0% | 75.0% |
| 0.3 | 880 | 38/52 | 4.3% | 73.1% |
| 0.5 | 601 | 35/52 | 5.8% | 67.3% |
| 0.7 | 278 | 18/52 | 6.5% | 34.6% |
| 0.8 | 133 | 12/52 | 9.0% | 23.1% |
| 0.9 | 19 | 2/52 | 10.5% | 3.8% |

En los 27 días de parte nacional sin incendios (216/216 ruta-días cubiertos), el corte 0,5 generó 35 alertas y el corte 0,9 generó 0.

Aunque el ranking supera la prevalencia, las probabilidades no están calibradas, la precisión del proxy sigue baja y el aumento del radio amplía demasiado la zona para una advertencia inmediata del sendero. No se obtiene una alerta confiable de fuego físico. Los partes SNMF son reportes administrativos ([alcance oficial](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)).

Detalle con hashes en [JSON](fire-jma-2023-train-2024-test-snmf-20km-sensitivity.json); reproducción con [`evaluate_jma_2023_to_2024_20km_sensitivity.py`](../../training/python/evaluate_jma_2023_to_2024_20km_sensitivity.py).
