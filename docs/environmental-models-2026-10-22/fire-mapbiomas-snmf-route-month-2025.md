# Cruce MapBiomas Fuego–SNMF cerca de rutas, 2025

## Adquisición reproducible

Se descargó desde Google Cloud Storage el GeoTIFF mensual de MapBiomas Fuego Collection 1 para 2025: 41.442.604 bytes, EPSG:3857, un ráster de 144.340 × 164.358 píxeles, 30 m proyectados y valor 0 como fondo/no cicatriz; los meses de quema son 1–12. El MD5 Base64 local coincide con el checksum del catálogo público y el SHA-256 calculado fue `06a4957371810f70aa52f73a58a34b2dff54785b4a9f06d8f391d16af98119cf`. El archivo completo se procesó en una carpeta temporal y se eliminó; solo quedan los resultados pequeños. El enlace es [GeoTIFF mensual 2025](https://storage.googleapis.com/mapbiomas-public/initiatives/argentina/fire/collection_01/monthly_burned/monthly_burned-argentina_burned_monthly_2025.tif) y los metadatos se pueden volver a consultar en [el catálogo público de objetos](https://storage.googleapis.com/storage/v1/b/mapbiomas-public/o/initiatives%2Fargentina%2Ffire%2Fcollection_01%2Fmonthly_burned%2Fmonthly_burned-argentina_burned_monthly_2025.tif).

El extractor reproyecta los centros del catálogo al CRS del raster y calcula radios aproximados de 5 y 10 km. Como el GeoTIFF tiene nodata 0 fuera de cicatrices, un cero significa **sin área quemada mapeada por este producto**, no una observación de vigilancia sin fuego. El cálculo de área corrige aproximadamente la escala local del Web Mercator; no es una medición catastral.


**Cobertura de la colecci?n:** la p?gina de productos todav?a resume los mapas mensuales como 2013?2024, pero el [anuncio oficial de lanzamiento de la Colecci?n Fuego](https://argentina.mapbiomas.org/2026/10/05/argentina-tiene-mas-superficie-agropecuaria-que-bosques-los-nuevos-datos-de-mapbiomas-muestran-como-cambio-el-territorio-desde-1985/) informa mapas mensuales y anuales de superficie quemada para 1999?2025. La auditor?a del bucket p?blico encontr? los 27 GeoTIFF mensuales y anuales hasta 2025, y este archivo 2025 tiene checksum verificado. La diferencia corresponde al texto resumido de la p?gina de producto; el archivo s? forma parte del lanzamiento oficial. En todos los a?os, la capa mensual sigue siendo retrospectiva y no da hora de ignici?n.

## Resultado por centro de ruta

| Ruta | Mes en el píxel central | Píxeles quemados a 10 km | Área aproximada a 10 km | Meses mapeados a 10 km |
|---|---:|---:|---:|---|
| Macuco – Salto Arrechea | — | 0 | 0 ha | — |
| Refugio Frey desde Villa Catedral | — | 520 | 26,5 ha | feb., mar., ago., oct. |
| Quebrada del Condorito – Balcón Norte | oct. | 84.652 | 5.520,3 ha | may.–dic. |
| Sendero Namuncurá | — | 0 | 0 ha | — |
| Cerro Ventana – Hueco de la Ventana | — | 1.226 | 68,5 ha | feb., mar., may., jun., dic. |
| Bosque Tallado – plataforma del Piltriquitrón | — | 5.449 | 271,6 ha | ene.–abr., jul., ago., dic. |
| Che Roga – Mburucuyá | — | 161 | 11,3 ha | ene., mar., ago. |
| La Chuña – El Rey | — | 77 | 5,7 ha | nov. |

“—” indica cero de área quemada mapeada en ese píxel, no faltante meteorológico ni día confirmado sin fuego. Los conteos/áreas describen cicatrices retrospectivas dentro de círculos alrededor de centros; no son áreas de incendio asignadas a la ruta.

## Comparación con inicios SNMF

El inventario ya extraído de partes SNMF contiene cuatro ruta-días con inicios reportados a menos de 10 km del centro y pronóstico WRF disponible. Al comparar cada ruta-día con cualquier área quemada de MapBiomas en el mismo mes dentro de 10 km del centro, hubo coincidencia en **2 de 4**: Cerro Ventana (diciembre) y Quebrada del Condorito (octubre). Es una coincidencia ruta-mes, no una identificación de los incendios por nombre.

Luego se recuperaron las coordenadas de los cinco incidentes SNMF deduplicados que forman esos cuatro ruta-días: dos en Bosque Tallado el 8/10, uno allí el 17/11, Cerro Napostá el 11/12 y un incendio en el Parque Nacional Quebrada del Condorito el 10/10. Al medir área del mismo mes desde cada coordenada reportada:

| Incidente SNMF | Distancia al centro de ruta | Píxeles del mismo mes a 250 m | a 500 m | a 1 km | a 2 km |
|---|---:|---:|---:|---:|---:|
| Cerro Radal (08/10) | 9,928 km | 0 | 0 | 0 | 0 |
| Ruta 40 Control Policial (08/10) | 4,721 km | 0 | 0 | 0 | 0 |
| Ternero Los fuegos (17/11) | 7,404 km | 0 | 0 | 0 | 0 |
| Cerro Napostá (11/12) | 9,124 km | 21 | 60 | 60 | 60 |
| Parque Nacional Quebrada del Condorito (10/10) | 5,702 km | 0 | 0 | 0 | 411 |

La señal de cicatriz del mismo mes apareció dentro de 1 km para **1 de 5** coordenadas y dentro de 2 km para **2 de 5**. Los otros tres no tienen píxeles del mes correspondiente dentro de 2 km; eso puede indicar omisión cartográfica, coordenadas/fechas administrativas aproximadas o desfase entre inicio y fecha Landsat. No prueba que esos reportes sean erróneos ni que el área estuviera libre de fuego. El caso de Condorito sí muestra por qué el centro de sector es demasiado tosco: el raster tiene una gran cicatriz del mismo mes en la zona de 10 km, pero no dentro de 1 km del punto SNMF.

Este resultado valida parcialmente la utilidad de MapBiomas como **fuente de etiquetas espaciales y mensuales**, pero su concordancia limitada impide usarla como verdad perfecta sin revisar los eventos contra polígonos, imágenes y fechas de fuente. Tampoco prueba anticipación: el raster fue construido retrospectivamente con imágenes Landsat y su etiqueta es el mes de quema, no la hora de ignición. No se puede calcular precisión de una alerta ni crear negativos usando píxeles sin cicatriz.

## Reproducción

El JSON completo, hashes, conteos por mes y verificaciones evento-coordenada están en [`fire-mapbiomas-snmf-route-month-2025.json`](fire-mapbiomas-snmf-route-month-2025.json). Se reproduce con [`evaluate_mapbiomas_fire_2025_route_coincidence.py`](../../training/python/evaluate_mapbiomas_fire_2025_route_coincidence.py); el script comprueba el MD5 del catálogo y elimina el GeoTIFF al salir.

La fuente metodológica describe los objetos y sus fechas `date_min`, `date_med`, `date_max`, pero estos datos vectoriales requieren lectura autenticada de Earth Engine; esta prueba se hizo con el GeoTIFF mensual que sí está directamente disponible en el bucket público. Ver [auditoría de la fuente de etiquetas MapBiomas](fire-mapbiomas-national-label-source-audit-2026-10-23.md) y [prueba de eventos SNMF 2025](fire-smn-wrf-snmf-2025-event-test.md).
