# Evaluacion GFS de nuevas detecciones GOES a 24 horas

El objetivo es una deteccion GOES nueva en un sector, condicionada a que el historial satelital reciente del sector no muestre fuego al emitir el pronostico. Esto reduce la persistencia, pero no identifica la hora exacta de ignicion. El test cronologico de enero de 2026 quedo reservado.

Se excluyeron 269 observaciones sector-tiempo con fuego reciente; quedaron 23841 observaciones elegibles. La validacion tuvo 5 dias-ruta positivos y el test 25.

| Corte diagnostico fijo | Validacion: aciertos/avisos | Test: aciertos/avisos |
|---:|---:|---:|
| 0.50 | 5/130 (3.8%) | 23/146 (15.8%) |
| 0.80 | 3/33 (9.1%) | 16/62 (25.8%) |
| 0.90 | 2/3 (66.7%) | 10/14 (71.4%) |
| 0.95 | 2/2 (100.0%) | 7/11 (63.6%) |
| 0.99 | 1/1 (100.0%) | 3/5 (60.0%) |

Ningun corte de validacion alcanzo la puerta predefinida de precision >=80% con al menos cinco avisos; por eso no se selecciono umbral. A 0.5, el test obtuvo 23/146 = 15.8% de precision del proxy GOES y 23/25 dias-ruta positivos detectados. El modelo original que incluia detecciones persistentes obtuvo 24/136 = 17.6% de precision y 24/25 de recall en el mismo test; excluir fuego reciente no mejoro el resultado. Si se relaja la puerta a dos avisos, el corte 0.95 da 2/2 en validacion pero solo 7/11 = 63.6% en test; sigue por debajo de 80% y su recall cae a 28%.

En el cruce separado con incendios SNMF de enero, hubo cobertura para 4 de 91 incidentes reportados; el modelo alerto en 4/4 a 0.5. Es sensibilidad descriptiva sobre cuatro casos cubiertos, no precision ni una prueba exacta de adelanto de 24 horas.

El modelo no es fiable para alertas de senderos. Los hashes, reglas de cobertura, predicciones por dia-ruta y limitaciones estan en el [JSON](fire-goes-gfs-24h-new-detection-evaluation.json); el cruce de eventos tiene un [JSON separado](goes-gfs-24h-snmf-2026-jan-new-detection-event-audit.json). Reproducir con [`evaluate_goes_gfs_24h_new_detection.py`](../../training/python/evaluate_goes_gfs_24h_new_detection.py).
