# Auditoría de fuente: pronósticos GFS históricos

## Hallazgo

Existe una fuente alternativa para ampliar las corridas meteorológicas archivadas: NOAA distribuye el Global Forecast System (GFS) en su programa de datos abiertos, con espejos en AWS, Google Cloud y Azure. El catálogo de Google Earth Engine documenta una colección GFS de 0,25° desde 2015, actualizada cada seis horas, con propiedades separadas para la hora de creación de la corrida (`creation_time`) y la hora válida (`forecast_time`). La grilla tiene aproximadamente 27,8 km. La colección incluye temperatura, humedad relativa, viento y precipitación; el índice Haines aparece desde el 15/01/2025. NOAA declara sus datos en dominio público.

La fecha de emisión y la hora válida permiten seleccionar un hindcast sin fuga temporal, por ejemplo una corrida emitida antes de un incendio y evaluada a +24 h. El GFS es más grueso que el WRF-SMN de ~4 km y puede representar mal contrastes locales de montaña y vegetación. Haines es un indicador de inestabilidad atmosférica; no debe tratarse como probabilidad de ignición. Que el archivo exista tampoco prueba que el pronóstico anticipe incendios cerca de senderos.

## Acceso comprobado en esta sesión

La información pública y la existencia de espejos se verificaron en la documentación de NOAA y Google. La adquisición local, en cambio, no pudo recuperar datos: las solicitudes a Open-Meteo Previous Runs, al bucket público WRF-SMN y una solicitud HTTP Range de 100 bytes al espejo GFS de Google terminaron con `WinError 10054` (conexión restablecida). No se guardaron datos parciales. La solicitud a Google usó el objeto público `gfs.20251010/12/atmos/gfs.t12z.pgrb2.0p25.f027`, correspondiente a una corrida de 27 horas.

Por ahora solo permanecen disponibles las 591 fechas WRF-SMN ya descargadas entre abril de 2022 y diciembre de 2023, más los archivos GFS Open-Meteo obtenidos anteriormente para enero de 2024 y enero de 2025–enero de 2026. No se incorporó ninguna fila nueva para octubre de 2025 y no se reentrenó ningún modelo.

## Qué falta para evaluar este candidato

1. Descargar de una fuente NOAA las corridas GFS históricas de ocho centros de senderos, con fecha de emisión, fecha válida y variables completas; fijar por adelantado un lead-time operacional, por ejemplo +24 h.
2. Verificar la extracción de los mensajes GRIB y sus horas. Si se usa la colección Earth Engine, confirmar si la consulta/exportación puede hacerse con las credenciales disponibles; su ficha pública no equivale a acceso local anónimo a sus API.
3. Construir la etiqueta de evento desde partes SNMF y cartografía oficial, agrupando repeticiones en episodios y dejando indeterminadas las fechas sin registro. Los partes diarios descargados no cubren todos los días ni aportan negativos exhaustivos, por lo que el modelo no puede obtener una precisión válida solo a partir de silencios del archivo.
4. Reservar temporadas y episodios completos para la prueba, ajustar el umbral solo en validación e informar precisión por evento con intervalo de confianza, sensibilidad, cobertura de fuentes y calibración. Comparar también con frecuencia histórica y persistencia.

Hasta superar estos pasos, el GFS sirve como fuente meteorológica candidata, no como modelo de incendios validado. La limitación actual es doble: conectividad de adquisición desde esta sesión y falta de un registro independiente y suficientemente completo de eventos/no-eventos cerca de las rutas.

## Fuentes primarias

- [NOAA NODD: catálogo de datasets y espejos de GFS](https://www.noaa.gov/nodd/datasets).
- [NOAA NCEI: Global Forecast System, acceso y archivos históricos](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast).
- [Google Earth Engine Data Catalog: NOAA/GFS0P25, tiempos de emisión/validez, variables, resolución y uso](https://developers.google.com/earth-engine/datasets/catalog/NOAA_GFS0P25).
