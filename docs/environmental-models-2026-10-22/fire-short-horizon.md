# Evaluación de fuego con observaciones frecuentes

## Pregunta

¿Los datos satelitales frecuentes permiten identificar focos activos cerca de senderos argentinos y sostener una predicción con pocas horas de adelanto?

## Fuente y diseño

Se descargó el producto original NOAA GOES-16 ABI L2 Fire/Hot Spot Characterization (FDCF), público en S3, para enero de 2024. Se seleccionó la primera escena Full Disk disponible dentro de los primeros 12 minutos de cada hora UTC y se muestrearon 1.858 píxeles nativos en sectores de ocho recorridos del catálogo argentino. El protocolo fijó los horizontes de 30 minutos, 1, 2, 3, 6 y 12 horas antes de extraer las etiquetas.

Se consideraron positivos solo los píxeles de fuego/probable fuego de mayor confianza y calidad completa; los píxeles nublados, de calidad dudosa y sin observación quedaron excluidos, nunca como negativos. Se conservaron los archivos NetCDF originales, sus hashes y metadatos. No se generaron observaciones sintéticas.

## Resultado de cobertura

De 744 horarios se obtuvieron 736 escenas originales. Ocho horarios no tuvieron una escena dentro de la ventana de muestreo. En los píxeles observados quedaron:

- 7 filas positivas, todas en el mismo sector y el mismo día: Bosque Tallado, 30 de enero de 2024.
- 1.011.772 filas negativas.
- 355.709 filas excluidas por calidad u otras clases.
- Demora de publicación mediana: 0,595 minutos; máxima: 64,24 minutos. Es una aproximación conservadora a la disponibilidad, no un registro exacto de primera publicación.

Las siete filas positivas no son siete incendios independientes: pertenecen a una sola agrupación de lugar y fecha. No se cumplen los mínimos fijados previamente para entrenamiento, calibración y pruebas temporales y geográficas. Por eso no se ajustó un clasificador ni se seleccionó un horizonte: con esta muestra, cualquier precisión reportada sería engañosa.

## Conclusión

GOES ofrece observaciones mucho más frecuentes que la capa diaria MODIS y la demora medida en esta muestra fue baja. Sin embargo, este mes y estos ocho sectores no contienen suficientes eventos para aprender ni validar un pronóstico de 30 minutos a 12 horas. Tampoco se puede afirmar una probabilidad garantizada. La fuente puede servir para estudiar detecciones recientes, pero esta corrida no demuestra que la cobertura ni el nivel de falsas alarmas sean adecuados para alertas de seguridad en trekking.

La siguiente evaluación debería ampliar el período y medir más eventos independientes antes de entrenar. Como el GOES-16 ya no representa el satélite operativo actual, una implementación en vivo también requeriría revisar el sensor sucesor y repetir la validación con una fuente histórica comparable. El modelo MODIS diario existente continúa inhabilitado.

## Reproducción y artefactos

- Protocolo previo a etiquetas: [fire-hourly-protocol.json](../../training/data/environmental/fire-hourly-protocol.json).
- Auditoría de descarga y conteos: [fire-hourly-source-audit.json](fire-hourly-source-audit.json).
- Código de adquisición/extracción: `training/python/fire_hourly_sources.py`.
- Archivos NOAA originales y observaciones extraídas: caché local ignorada por Git, bajo `training/data/raw/environmental/fire-goes16/` y `training/data/environmental/private/`.

Este resultado es un filtro de viabilidad de datos, no una evaluación de desempeño de un modelo.
