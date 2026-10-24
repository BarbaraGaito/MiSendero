# Validación contra incendios oficiales

Se amplió la prueba de MODIS con los perímetros oficiales de área quemada de IDECOR para Córdoba, usando los rasters originales completos MOD14A1.061 que ya estaban descargados. El análisis anterior usaba solo píxeles fijos alrededor de los sectores; esta versión busca detecciones en todos los píxeles de una ventana alrededor de cada perímetro elegible, sin depender de esos puntos fijos.

## Resultado MODIS

Se evaluaron 84 perímetros con fecha registrada dentro de 40 km de alguno de los ocho centros de trekking cubiertos. Hubo observación terrestre válida cerca de 80 perímetros; en 12 se encontró al menos un píxel de fuego nominal/alta confianza dentro de 750 m del perímetro, desde la fecha registrada hasta siete días después. Los otros 68 no tuvieron coincidencia en esa ventana y cuatro no tuvieron cobertura terrestre válida. Entre los 12 casos, la primera detección fue el mismo día en cinco, al día siguiente en seis y dos días después en uno.

Esto confirma que MODIS detectó algunos incendios cartografiados y que la demora observada en estos casos fue de cero a dos días. **No es una medida de precisión del modelo ni demuestra anticipación:** las fechas oficiales no necesariamente son la hora exacta de inicio; un perímetro no es un sensor de fuego activo; los 12 polígonos pueden compartir episodios; y los cuatro casos sin observación no se contaron como ausencia de fuego. Tampoco se puede afirmar que las 68 no coincidencias sean errores del satélite.

El informe reproducible conserva el hash del informe de adquisición, los hashes de los perímetros originales, la regla espacial/temporal y las limitaciones: [resultado de comparación MODIS](modis-full-raster-official-perimeter-matches.json). El script reproducible está en [evaluate_modis_full_raster_perimeters.py](../../training/python/evaluate_modis_full_raster_perimeters.py).

## Prueba ampliada en los tiles disponibles

También corrí la misma comparación para todos los perímetros cordobeses de 2022–2023 que intersectan cualquiera de los cinco tiles MODIS descargados, sin el filtro de cercanía a senderos. De 888 perímetros con fecha, 855 tuvieron observaciones válidas en la ventana y 99 coincidieron con una detección; 756 no coincidieron bajo la regla definida y 33 no tuvieron píxeles terrestres válidos en esos días. La primera detección ocurrió el mismo día en 55 casos, al día siguiente en 34, a los dos días en tres, a los cuatro en dos, a los seis en tres y a los siete en dos.

Este segundo grupo cubre más territorio de Córdoba, pero no toda Argentina ni todo el historial de MODIS. Los conteos son por polígono: un incendio puede generar varias geometrías, y el perímetro/fecha de mapeo no equivale al inicio observado. Por eso estos resultados sirven para auditar coincidencia espacial y demora de detección; no los interpreto como precisión, recall o rendimiento predictivo. El detalle está en [comparación de cobertura de tiles](modis-full-raster-cordoba-tile-coverage.json).

## Dataset argentino para una próxima prueba

MapBiomas Fuego Colección 1 es un producto nacional de cicatrices quemadas derivado de Landsat. Aunque la ficha resumida aún dice que los mapas mensuales cubren 2013–2024, el anuncio oficial de lanzamiento declara mapas anuales y mensuales de área quemada para 1999–2025; la auditoría del bucket confirmó 27 GeoTIFF mensuales y anuales hasta 2025 y verificó el checksum del raster mensual 2025. Se usó ese raster en una comparación descriptiva con SNMF, pero **no es un registro de detecciones en tiempo real**: las cicatrices son retrospectivas y su etiqueta mensual no fija la hora de ignición ni valida anticipación. La [auditoría de fuente y método](fire-mapbiomas-national-label-source-audit-2026-10-23.md) conserva la discrepancia entre la ficha resumida y el anuncio de lanzamiento.

### Actualización 23/10/2026

Se publicó el ATBD de MapBiomas Fuego Argentina Collection 1 v1.0 y se describe la capa nacional `burned_area_polygons_v2`: 1.012.645 objetos con geometría, fechas Landsat (`date_min`, `date_med`, `date_max`) y probabilidad posterior de clasificación (`p_mean`, `p_width`). La validación espacial propia del clasificador de cicatrices informa AUC agrupado 0,891, pero el mismo ATBD aclara que sus etiquetas no son una muestra aleatoria y que su probabilidad no está calibrada a la prevalencia poblacional. La capa mejora la posibilidad de ampliar positivos históricos y comprobar desfases; no estima precisión de pronóstico a futuro. Se documentan alcance, discrepancia en años disponibles y acceso pendiente en [auditoría de etiquetas MapBiomas](fire-mapbiomas-national-label-source-audit-2026-10-23.md).

El portal nacional de incendios forestales que encontré ofrece principalmente conteos y hectáreas agregados por provincia/año, insuficientes para asignar hora, ubicación o estado a un sendero. El registro técnico de ocurrencias del SNMF tiene los campos más adecuados (fechas, ubicación, superficie, vegetación y causas), aunque los reportes visibles son PDF y todavía requieren extracción/deduplicación para formar un conjunto de entrenamiento reproducible.

## GOES-19 y siguiente paso

El cruce previo de GOES-19 encontró cero coincidencias bajo su regla de ±1 día y hasta 10 km en 70 perímetros cercanos a los sectores. Esa prueba está limitada a ocho muestras fijas, por lo que no sirve para estimar sensibilidad de cobertura completa. El resultado se conserva en [comparación GOES-19](goes19-official-perimeter-matches.json).

Hay corroboración oficial útil para octubre de 2023: el SNMF seguía reportando los focos de La Suela/San Clemente y Las Minitas/Cabalango el 14 de octubre; CONAE procesó Landsat-9 y estimó 4.750 ha quemadas en el área de Villa Carlos Paz, Cabalango y el nacimiento del río La Suela. Es consistente con varios de los cruces MODIS, pero esos registros/cartografías cercanos pueden ser partes de un mismo episodio, así que no se cuentan como eventos de validación independientes.

Los reportes diarios del SNMF documentan focos informados por las jurisdicciones y a veces incluyen fecha de inicio y coordenadas. Aún hay que extraer y deduplicar los eventos de esos PDF antes de usarlos como conjunto nacional; no se incorporaron como etiquetas automáticamente.

Los datos sustentan seguir investigando **detección de fuego observado**. No sustentan publicar una probabilidad de riesgo, afirmar precisión generalizable ni usar estos experimentos como predicción de propagación o seguridad de senderos. El entrenamiento de GOES-19 tampoco mejoró su evaluación previa: los horizontes de 2, 3, 6 y 12 horas quedaron por debajo de persistencia, y el de 1 hora apenas la superó en AP con bajo recall. La aplicación permanece sin cambios y los modelos siguen sin aprobación para despliegue.

## Fuentes institucionales

- [IDECOR: mapeo oficial de incendios de 2025](https://www.idecor.gob.ar/incendios-forestales-y-rurales-en-2025-los-datos-oficiales-del-mapeo-provincial/)
- [SNMF: funciones y datos de ocurrencia de incendios](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego/que-es-y-como-funciona-el-servicio-nacional-de-manejo-del-fuego)
- [Reporte del SNMF del 14 de octubre de 2023](https://www.argentina.gob.ar/sites/default/files/2023/10/14_de_octubre.pdf)
- [CONAE: imágenes satelitales de los incendios en Córdoba de octubre de 2023](https://www.argentina.gob.ar/node/404358)
- [MapBiomas Argentina: metodología, productos y descarga de Fuego](https://argentina.mapbiomas.org/iniciativas-y-productos/fuego/)
- [Repositorio público de MapBiomas Argentina Fuego, estado de la Colección 1](https://github.com/mapbiomas/argentina-fire)
- [Portal nacional de datos abiertos: incendios forestales agregados](https://www.datos.gob.ar/id/dataset/ambiente-incendios-forestales)

Se amplió la auditoría de posibles etiquetas MapBiomas hacia 2023. En el inventario SNMF quedaron dos días-sector a menos de 10 km de los centros de senderos, pero el raster mensual 2023 no pudo descargarse desde esta sesión por un reinicio de la conexión HTTPS; no se reportan coincidencias de ese año. Incluso con el archivo, serían solo dos positivos de ruta y un cruce mensual retrospectivo, insuficientes para una estimación fiable. Ver [auditoría 2023](fire-mapbiomas-snmf-route-month-2023.md) y [script de cruce](../../training/python/evaluate_mapbiomas_fire_2023_snmf_coincidence.py).

La comparación conjunta del candidato GOES-19 de una hora confirma que la precisión por píxel no se traduce en evidencia de detección por evento: en enero coincidió con uno de 14 incidentes SNMF activos/controlados con cobertura, igual que persistencia, y 120 incidentes del archivo quedaron fuera de cobertura. Como esos reportes no certifican todos los períodos sin fuego, la precisión de avisos reales sigue sin poder calcularse. La [auditoría reproducible de la brecha](fire-reliability-gap-audit-2026-10-23.md) cuantifica además cuántos avisos independientes y adjudicados requeriría una meta de precisión con límite exacto unilateral de confianza del 95 %.

Para el modelo de 24 h, la agrupación de alertas por rachas consecutivas en los 232 días-sector con reportes y cobertura arrojó 4 de 22 rachas coincidentes con reportes activos cercanos; persistencia arrojó 1 de 8. El modelo acumuló 133 días-sector de aviso en esas rachas, incluida una secuencia continua de 27 días en un sector. Los conteos son un proxy de carga de alertas y coincidencia con SNMF, no precisión de incendios confirmados. Ver [resultado](fire-gfs-24h-snmf-2026-jan-alert-episodes.json) y [script reproducible](../../training/python/evaluate_fire_report_proxy_episodes.py).
