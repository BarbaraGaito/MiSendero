# Nueva corrida prospectiva del pronóstico INPE

El 23/10/2026 a las 14:18 UTC se archivó una emisión nueva de los cuatro GeoTIFF públicos T0–T3 del producto Risco de Fogo del INPE. La corrida meteorológica es del 23/10 a las 00 UTC y los mapas se crearon entre las 09:21 y 09:25 UTC. El JSON compacto conserva hashes, metadatos de emisión y validez, y resúmenes alrededor de ocho centros de senderos argentinos. Los GeoTIFF temporales se eliminaron después de extraerlos.

| Archivo | Validez UTC | Anticipo desde creación aproximada |
|---|---|---:|
| T0 | 23/10 18:00 | 8 h 35 min |
| T1 | 24/10 18:00 | 32 h 35 min |
| T2 | 25/10 18:00 | 56 h 37 min |
| T3 | 26/10 18:00 | 80 h 38 min |

Para T1, los valores puntuales del score de peligro fueron 0 en Macuco, Frey, Che Roga y Bosque Tallado; 0,80 en Condorito, 0,86 en Namuncurá, 0,21 en Cerro Ventana y 0,60 en La Chuña–El Rey. Son scores del producto, no probabilidades de ignición. Los resúmenes en radios de 5 y 10 km son buffers de los centros, no mediciones sobre cada tramo de las líneas de sendero.

Esta corrida inicia una observación prospectiva nueva: todavía no se ha cumplido la validez más tardía de T0 al momento de la captura, por lo que aún no hay resultado observado para comparar. La captura se deduplica por horizonte, emisión, validez y hash; no cuenta como cuatro episodios independientes de desempeño. El archivo original reducido y verificable es [`capture_20261023T141831Z.json`](../../training/data/environmental/inpe_fire_forecasts/capture_20261023T141831Z.json). Para evaluar el producto habrá que contrastar los días válidos con detecciones de fuego observadas y con cobertura válida, y tratar por separado los días sin observación. Un solo ciclo no permite calcular precisión fiable.

Al intentar actualizar la captura el 23/10/2026 a las 14:57 UTC, el primer GeoTIFF de la fuente oficial reseteó la conexión HTTPS. Se confirmó que las dependencias del proyecto estaban disponibles; no se descargaron datos parciales ni se creó una captura nueva. El ciclo archivado arriba permanece sin observaciones maduras posteriores a su emisión.

La captura se reprodujo con [`archive_inpe_fire_forecast_routes.py`](../../training/python/archive_inpe_fire_forecast_routes.py). No se modificó la app ni se habilitaron alertas.

Actualizacion 23/10/2026, 17:48 UTC: se volvio a intentar capturar los cuatro horizontes T0-T3. Cada archivo se solicito tres veces con pausas crecientes; el servidor cerro las cuatro conexiones TLS (WinError 10054). No se guardo una captura incompleta ni se anadieron observaciones. El ciclo de las 14:18 UTC sigue pendiente de evaluacion. Se mejoro el archivador para reintentar cada horizonte de forma independiente, limpiar descargas parciales y conservar los horizontes disponibles en futuras ejecuciones. Las pruebas simuladas de reintento y agotamiento pasaron; esta ejecucion real confirma que la fuente sigue inaccesible desde este entorno.


Corte parcial reproducible al 23/10/2026 17:54:36 UTC: para la ventana T0 valida desde el 22/10 a las 18 UTC, se revisaron las filas de los CSV disponibles en los segmentos 18:00-24:00 del 22/10 y 00:00-17:54 del 23/10. El CSV del 22/10 supero el corte de madurez; el del 23/10 aun no (Last-Modified 17:04 UTC y ultimo registro argentino a las 12:19 UTC). No hubo focos listados a menos de 10 km de los ocho centros en esas filas. Esto es una busqueda de positivos en archivos disponibles, no una mascara de cobertura satelital: cero detecciones no confirma ausencia de fuego y la ventana de 24 horas sigue sin resultado. Ver [auditoria parcial con hashes](fire-inpe-prospective-partial-audit-2026-10-23.md), [JSON](fire-inpe-prospective-partial-audit-2026-10-23.json) y [auditoria completa](fire-inpe-prospective-outcomes-2026-10-23.md).


A las 17:55 UTC se volvio a consultar T0-T3 por el canal de descarga habilitado. El archivador recibio los cuatro archivos y los deduplico: corrida, validez y SHA-256 coincidian con la captura de las 14:18 UTC. Esa emision seguia siendo la vigente justo antes de la validez de T0 a las 18:00 UTC.

A las 17:56 UTC se recalcularon los campos de madurez de los manifiestos locales del 21 y 22/10 usando la regla correcta (Last-Modified posterior a las 06 UTC del dia siguiente). Se conservaron los bytes, hashes, marcas de servidor y horas originales de captura. El auditor completo sigue con 3 ventanas pendientes por CSV inmaduro y 5 por CSV ausente; la pantalla parcial no encontro puntos cerca de los sectores.

Actualizacion 23/10/2026 18:05 UTC: se refresco el CSV diario del INPE del 23/10 y se conservo la version previa con su manifiesto en el archivo privado de capturas. La nueva version tiene Last-Modified 18:04:02 UTC, SHA-256 e5f5b2d3a0180cb612f4932323af29325b8fae694764be5feef916e49faece96, y ultimo registro argentino a las 12:19 UTC. El corte parcial actualizado revisa tres ventanas, con un segmento de CSV maduro y cero focos a menos de 10 km de los centros; el auditor de ventana completa mantiene 3 pendientes por CSV inmaduro y 5 por archivos ausentes. La hora maxima de registros no representa cobertura satelital; no se crean etiquetas negativas.
