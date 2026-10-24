# Evaluación exploratoria GFS + GOES a 24 horas

Se recuperaron pronósticos históricos del modelo GFS con adelanto fijo de 24 h para los ocho sectores de trekking argentinos incluidos en el estudio GOES. Para 2025-01-01 a 2026-01-31, cada sector devolvió 9.504 horas sin valores faltantes en temperatura, humedad relativa, viento a 10 m y precipitación. También se obtuvo enero de 2024 para incorporar observaciones GOES-16 ya disponibles; en ese mes el archivo solo tuvo valores para las 300 horas finales, incluidos los días del único sector-día positivo (30 de enero). Las horas faltantes se excluyeron. Las descargas permanecen en la caché privada. Las coordenadas devueltas corresponden a celdas de modelo, no a una resolución propia del sendero.

Se emparejaron 5.712 pares de escaneos GOES separados por 24 h. Para que un sector-hora negativo no significara simplemente “sin observación”, se exigió cobertura de etiquetas válidas en al menos el 50 % de sus píxeles fijos, y se exigió historia GOES válida para al menos el 25 % al generar predictores. Los incendios positivos son detecciones satelitales de alta calidad, no igniciones verificadas. Se usó enero de 2024 y los períodos GOES disponibles de 2025 para entrenamiento, diciembre de 2025 para validación y enero de 2026 como prueba temporal intacta.

El modelo logístico con peso de clase no superó la persistencia del fuego observado. En la prueba de enero, el corte diagnóstico 0,5 produjo 24 aciertos en 136 avisos de sector-día (17,6 % de precisión descriptiva; 96 % de recall sobre 25 sectores-día con detección). La persistencia produjo 16 aciertos en 23 avisos (69,6 %; 64 % de recall). Los sectores y días vecinos pueden corresponder al mismo incendio, así que esos intervalos por sector-día no equivalen a precisión por episodio independiente. Además, el corte 0,5 no fue seleccionado en validación.

La validación de diciembre solo tuvo cinco sectores-día positivos y no encontró ningún umbral con precisión de al menos 80 % y cinco avisos o más. Por tanto, no se congeló un corte y el candidato se clasifica `insufficient_positive_route_sector_days`. Este ensayo no respalda una predicción fiable; tampoco permite afirmar probabilidad de incendio, anticipación de ignición ni seguridad de una ruta. La cantidad de positivos y la falta de un registro exhaustivo e independiente de negativos impiden una afirmación sólida de precisión.

El experimento se reproduce con [`evaluate_goes_gfs_previous_runs.py`](../../training/python/evaluate_goes_gfs_previous_runs.py). Los datos se adquieren con [`acquire_openmeteo_previous_runs.py`](../../training/python/acquire_openmeteo_previous_runs.py). Las fuentes, huellas y métricas completas están en [`fire-goes-gfs-24h-evaluation.json`](fire-goes-gfs-24h-evaluation.json). No se tocó inferencia de producción, APK ni despliegue.

## Regla conservadora de continuidad

Se probo una regla fijada solo con validacion: considerar alertas unicamente en sectores donde la historia satelital ya registraba fuego activo al emitir el pronostico, y filtrar esos casos con el puntaje GFS+GOES para exigir al menos 80 % de precision y cinco avisos. La validacion no encontro ningun umbral elegible. Por eso no se aplica un corte al conjunto de prueba y no se propone como mejora. Esta regla solo evaluaria continuidad de un fuego ya observado; no anticiparia una ignicion. El resultado y los datos completos estan en el JSON del experimento.

Tambien se intento recuperar pronosticos GFS previos para febrero-diciembre de 2024. Open-Meteo corto la conexion HTTPS y el script no escribio ningun archivo parcial; la serie actual no pudo ampliarse.


El test tambien se cruzo con los eventos oficiales SNMF independientes de enero de 2026. El resumen de cobertura y sus limites esta en [la auditoria de eventos](fire-goes-gfs-24h-snmf-2026-jan-event-audit.md). La evaluacion guarda los puntajes de cada ruta-sector-dia de prueba en el JSON para permitir ese cruce sin reentrenar.
