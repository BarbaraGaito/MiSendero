# Evaluación de incendios por ruta y día

Se agregó una evaluación con la unidad que necesita la app: un sector de ruta por día. Si varios pixeles del mismo sector superan el umbral, cuentan como un solo aviso; el puntaje del aviso es el máximo entre los pixeles muestreados. La etiqueta positiva significa que MOD14A1 detectó fuego nominal o de alta confianza en al menos uno de esos pixeles.

## Resultado

La selección nueva probó cuatro pesos de clase y buscó en validación un umbral con al menos cinco avisos y 90% de precisión proxy. Ninguna variante alcanzó ese criterio. El resultado completo está en [`fire-route-day-threshold-evaluation.json`](fire-route-day-threshold-evaluation.json).

Como comprobación adicional, agregamos las predicciones congeladas del XGBoost original, al umbral fijo 0,5, sin ajustar el corte con los tests:

- Test temporal: 12 de 267 avisos coincidieron con una ruta-día positiva de MODIS (precisión proxy 4,5%); detectó 12 de 16 ruta-días positivos (recall proxy 75%).
- Test geográfico: no hubo avisos; quedaron sin detectar los dos ruta-días positivos disponibles.

El detalle reproducible está en [`fire-route-day-prediction-audit.json`](fire-route-day-prediction-audit.json), generado por [`audit_fire_route_day_predictions.py`](../../training/python/audit_fire_route_day_predictions.py).

## Interpretación

El XGBoost congelado no sostiene una precisión útil a nivel de ruta-día. Los 255 avisos temporales que no coincidieron con MODIS son **avisos sin etiqueta positiva**, no falsos incendios confirmados: MODIS no registra todos los fuegos. A la vez, como solo hubo 16 positivos temporales y dos geográficos, esta cohorte es demasiado pequeña para estimar con estabilidad la precisión frente a incendios reales.

Por ahora no se debe mostrar este resultado como una probabilidad de incendio ni usarlo para afirmar precisión o seguridad de una ruta. La prueba mide detección satelital MODIS en las celdas muestreadas, no predicción de ignición. Para sostener precisión de incendios reales hacen falta registros de eventos completos con hora y geometría, más períodos y rutas independientes, y negativos verificados.

`synthetic_observations = 0`; el análisis no cambia ni habilita el modelo de la app.
