# Auditoría de pronósticos GFS históricos para el próximo ensayo de fuego

**Fecha de revisión:** 2026-10-22  
**Estado:** descarga comprobada y ensayo ejecutado; candidato de predicción a 24 h no fiable.  
**Uso:** investigación únicamente; no se modificó el modelo de la aplicación.

## Hallazgo

Open-Meteo publica una API de pronósticos de corridas anteriores que conserva el adelanto. Por ejemplo, una variable terminada en `_previous_day1` corresponde a lo pronosticado 24 horas antes del horario válido; `_previous_day2` conserva 48 horas, hasta siete días. Eso permite probar un pronóstico de 24 horas sin confundirlo con clima observado después del momento de decisión. La documentación enumera GFS global y señala cobertura histórica GFS desde marzo de 2021 para temperatura a 2 m; para las demás variables, la cobertura general de la mayoría de modelos comienza en enero de 2024. Por eso el período GOES-19 2025–2026 es una primera cohorte razonable para temperatura, humedad, viento y precipitación a 24 h, sujeto a comprobar los valores faltantes de cada variable antes de entrenar.

El histórico meteorológico continuo de Open-Meteo no debe sustituir los pronósticos archivados: puede usar las primeras horas de corridas sucesivas y no representa necesariamente un único adelanto fijo. Para esta evaluación corresponde usar Previous Runs y fijar el adelanto de 24 horas antes de mirar las etiquetas de prueba. Los archivos NOAA ARL GFS también son pronósticos reales, pero sus archivos diarios son de varios gigabytes; no son una descarga práctica para probar primero un conjunto pequeño de rutas.

Fuentes revisadas:

- [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api): adelantos fijos, modelos y disponibilidad histórica.
- [Open-Meteo Historical Forecast API](https://open-meteo.com/en/docs/historical-forecast-api): catálogo de variables/modelos y distinción frente a Previous Runs.
- [Open-Meteo precios y condiciones de API](https://open-meteo.com/en/pricing): uso gratuito no comercial, límites y condiciones actuales; comprobar licencia antes de cualquier uso comercial.
- [NOAA READY GFS de 0,25°](https://www.ready.noaa.gov/READYmetdata.php): archivos por ciclo y campos meteorológicos disponibles.

## Límite de lo que resuelve

Conseguir pronósticos históricos mejora la entrada meteorológica, pero no resuelve el problema principal de etiquetas. Las detecciones GOES/MODIS representan fuego activo visto por satélite, no necesariamente ignición, y los partes SNMF disponibles no son un registro exhaustivo de días y lugares sin incendio. Perímetros quemados como IDECOR o GlobFire sirven para corroborar episodios, pero la fecha del perímetro tampoco equivale a la hora exacta de ignición. Por eso no se pueden contar automáticamente todas las alertas no coincidentes como falsas ni producir precisión fiable solo por agregar clima.

Los ensayos actuales siguen siendo insuficientes: la transferencia WRF a rutas tuvo 3 coincidencias MODIS entre 255 alertas de ruta-día en la prueba; GOES-19 dio 70,3 % de precisión y 19,1 % de recall al umbral 0,5 para el objetivo limitado de repetir la detección del mismo píxel una hora después. El umbral elegido en validación para una precisión de al menos 80 % no produjo alertas en la prueba de enero. Esas métricas no son precisión de ignición ni de aviso de seguridad.

## Ensayo recomendado si se recupera el acceso

1. Descargar, por lotes y con caché, GFS Previous Runs para las coordenadas de las rutas argentinas y las fechas cubiertas por observaciones GOES. Consultar variables horarias de temperatura, humedad relativa, viento, precipitación y, si está disponible de manera consistente, radiación o sequedad atmosférica; guardar también fecha válida, modelo, adelanto, coordenadas solicitadas/devueltas, unidades, fecha de consulta y hash de cada respuesta.
2. Comprobar cobertura y valores nulos antes de crear filas; no reemplazar faltantes por cero. Fijar el adelanto en 24 h y no mezclar observaciones posteriores con predictores disponibles en el momento del aviso.
3. Crear un baseline transparente —persistencia/climatología— y un modelo calibrable sencillo. Compararlos primero para la tarea limitada de detección de fuego activo en el siguiente día y luego, por separado, contra incidentes/perímetros oficiales deduplicados.
4. Separar temporadas completas y episodios completos: entrenamiento hasta 2024, validación 2025 y prueba intacta 2026 (si la etiqueta y la cobertura espacial alcanzan). Seleccionar cualquier umbral solo con validación. Medir precisión y recall por evento de fuego, tasa de falsas alertas por ruta-día, intervalos de confianza y cobertura de referencia; informar los incendios no cubiertos y los casos indeterminados.
5. No afirmar probabilidad de ocurrencia a partir de una etiqueta de detección satelital ni desplegar un aviso preventivo si la prueba independiente no alcanza el criterio de éxito previamente definido.

## Descarga y evaluación completadas

La primera consulta al API falló por la conexión, pero solicitudes públicas posteriores a `previous-runs-api.open-meteo.com` completaron correctamente. Para 2025-01-01 a 2026-01-31 se descargaron 9.504 horas por punto para los ocho sectores; temperatura a 2 m, humedad relativa, viento a 10 m y precipitación no tuvieron faltantes. La respuesta comprimida ocupa 480.452 bytes. También se descargó enero de 2024: aunque el período tiene 744 horas, las cuatro variables solo estuvieron disponibles en las 300 horas finales para cada sector (60,5 % de faltantes); por eso solo se usaron las fechas cubiertas, incluida la detección GOES del 30/01/2024. Esos datos apoyan entrenamiento, no validación.

Con los pronósticos GFS a adelanto fijo de 24 h se emparejaron 5.712 escaneos GOES. El modelo logístico no encontró en la validación de diciembre un corte que cumpliera precisión de 80 % con al menos cinco avisos, y la prueba de enero quedó por debajo de persistencia: 24/136 avisos de sector-día (17,6 %) frente a 16/23 (69,6 %). El recall observado fue 96 % para el modelo y 64 % para persistencia, sobre 25 sectores-día con detección satelital; sectores cercanos y días consecutivos pueden ser el mismo incendio. Estos resultados no son precisión por episodio ni predicción de ignición. El candidato no se aprueba.

El reporte detallado es [`fire-goes-gfs-24h-evaluation.md`](fire-goes-gfs-24h-evaluation.md), con métricas legibles por máquina en [`fire-goes-gfs-24h-evaluation.json`](fire-goes-gfs-24h-evaluation.json). El ensayo se reproduce con [`evaluate_goes_gfs_previous_runs.py`](../../training/python/evaluate_goes_gfs_previous_runs.py); la adquisición se reproduce con [`acquire_openmeteo_previous_runs.py`](../../training/python/acquire_openmeteo_previous_runs.py).

Este archivo actualiza la ruta de investigación; no cambia artefactos del APK, la inferencia de la app ni modelos de producción.


## Probe of pre-2023 JMA archive from this session

The current Open-Meteo documentation lists JMA GSM Previous Runs data from 2018 ([official availability](https://open-meteo.com/en/docs/previous-runs-api)). A small local acquisition probe for 2020-01-01 through 2020-01-02 at the eight Argentine route sectors failed with `WinError 10054` (connection reset); the acquisition script wrote no data. The browser search tool could read the documentation but could not open the API response URL. This is an access failure from this session, not evidence that upstream data is absent. The already archived 2023-2025 data remains the latest usable JMA training span.
