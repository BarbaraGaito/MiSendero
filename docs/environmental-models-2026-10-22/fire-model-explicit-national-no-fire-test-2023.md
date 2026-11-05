# Prueba temporal en días sin incendios reportados a nivel nacional (2023)

Se cruzaron las predicciones ya congeladas del test temporal MODIS de 2023 con los cuatro partes SNMF de 2023 que declaran explícitamente que no hubo incendios reportados en el país. Los umbrales se muestran solo como diagnóstico; no se ajustaron con estos días. La unidad de conteo es ruta-día y, para cada ruta, se toma el score máximo de los píxeles disponibles, evitando contar cientos de píxeles de una misma ruta como casos independientes.

Hubo cobertura del modelo para 22 de los 32 pares posibles ruta-día: seis de ocho rutas en cada fecha. Ninguna de las 22 etiquetas objetivo MODIS fue positiva. Las cuatro fechas aportan solo dos bloques temporales separados (14/18 de julio y 20/21 de diciembre), así que la evidencia independiente es aún menor que cuatro episodios.

| Modelo congelado | Umbral diagnóstico | Alertas en ruta-día / cubiertos | Días de parte con alguna alerta |
|---|---:|---:|---:|
| Persistencia | 0,5 | 0/22 | 0/4 |
| Regresión logística | 0,5 | 5/22 | 3/4 |
| Random Forest | 0,5 | 0/22 | 0/4 |
| XGBoost | 0,5 | 4/22 | 2/4 |

Al subir el corte a 0,8, aún aparecen 4 alertas de regresión logística y 2 de XGBoost en días sin incendios declarados por el parte; Random Forest y persistencia no alertan. A 0,9, logística produce 2 alertas y XGBoost 2. Como no se incluyen días positivos en esta prueba, un modelo que no alerte nunca parecería perfecto: por eso estos recuentos no estiman precisión, no justifican elegir el umbral y no sustituyen el test completo.

El resultado sí aporta una señal adversa concreta para los avisos de logística y XGBoost: elevan el riesgo en fechas en las que el registro nacional declara cero incendios, incluso con scores altos. Puede deberse a falsos avisos, diferencias entre el blanco MODIS y los partes SNMF, o fuegos no incluidos en el registro; no permite atribuir la causa. Las fechas SNMF son negativos del registro administrativo y no certifican ausencia física de fuego. Tampoco es una evaluación de los modelos meteorológicos GFS/GOES ni del FWI.

Reproducción: [`evaluate_explicit_no_fire_model_days.py`](../../training/python/evaluate_explicit_no_fire_model_days.py). Predicciones, scores por ruta, fechas y hashes: [JSON](fire-model-explicit-national-no-fire-test-2023.json). Fuente y verificación de los partes: [auditoría nacional de días sin reporte](fire-snmf-national-no-fire-report-audit.md).

**Conclusión:** este test no mejora la precisión demostrada. Descarta interpretar los scores MODIS de logística o XGBoost como avisos fiables al corte 0,5 y muestra que hace falta una cohorte temporal más grande, con positivos independientes y estados negativos observados, antes de proponer un umbral.
