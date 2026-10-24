# Auditoría de MapBiomas Fuego Argentina como fuente de etiquetas

**Revisado:** 23/10/2026
**Estado:** candidato nacional útil para etiquetas históricas de cicatrices; no es por sí mismo un pronóstico de incendios ni permite estimar precisión de alertas por sendero.

## Hallazgo

MapBiomas Argentina publicó su primera colección nacional de Fuego. El documento metodológico de Collection 1 describe un producto de área quemada de 30 m para Argentina, con objetos poligonales, fechas de quema derivadas de observaciones Landsat y probabilidad del clasificador de objetos. El ATBD informa **1.012.645 objetos** de 1998–2025; el conjunto raster anual/mensual cubre años calendario desde 1999. Cada polígono incluye `date_med`, `date_min`, `date_max`, `p_mean` y `p_width`; las fuentes describen acceso público a una capa vectorial de Google Earth Engine y mapas Cloud Optimised GeoTIFF.

La ficha resumida del producto todavía indica mapas mensuales para 2013–2024, mientras que el anuncio oficial de lanzamiento de la Colección Fuego declara mapas anuales y mensuales de área quemada para 1999–2025. La auditoría del bucket público enumeró 27 GeoTIFF mensuales y 27 anuales para 1999–2025; el archivo mensual 2025 descargado coincide con el MD5 del catálogo. Se toma 1999–2025 como cobertura de la colección publicada y se conserva esta discrepancia de texto de la página de producto para trazabilidad. El evento 1998 se declara disponible solo en la capa vectorial, no en los rasters.

## Qué valida el ATBD y qué no

El clasificador BART de objetos de cicatriz tiene validación cruzada espacial en cinco pliegues con bloques de 0,5°: AUC agrupado 0,891; AUC ponderado dentro del año 0,845 para los 18 años con ambas clases. A los umbrales desplegados por tamaño, informa sensibilidad 0,845 y especificidad 0,780. Es evidencia metodológica valiosa de que el producto distingue cicatrices de artefactos dentro de sus etiquetas y población de muestreo.

No se debe trasladar esa métrica a MiSendero ni describir `p_mean` como probabilidad de que ocurra un incendio futuro. El propio ATBD explica que las ~5.255 etiquetas manuales de objetos no son una muestra aleatoria, que las prevalencias por año van de 0 a 1 y que siete años no tienen etiquetas. Por ello interpreta el ranking y la incertidumbre del modelo como producto, no como probabilidad calibrada para la población. Además, el objetivo es decidir retrospectivamente si un objeto de cicatriz corresponde a fuego; la validación no evalúa anticipación meteorológica.

Las fechas son las fechas de quema inferidas por la serie de observaciones de Landsat, no marcas horarias de ignición o del primer ataque. Una cicatriz puede ser descubierta días después del inicio y el producto usa toda la serie temporal para mapear el año. Por eso no es correcto comparar una emisión meteorológica como si la fecha cartográfica garantizara que el incendio empezó ese día. Hay que estimar primero el error de fecha y ubicación contra episodios SNMF/APN con coordenadas y fecha de inicio.

## Utilidad para el experimento de MiSendero

1. Ampliar la lista de episodios positivos y la cobertura espacial en las ocho rutas argentinas y sus zonas cercanas, después de deduplicar por identificador estable de incendio y de recortar cicatrices realmente cercanas a los trazados.
2. Usar `date_min` como primera fecha cartográfica candidata, conservar `date_med`/`date_max` para sensibilidad de fechas y revisar `p_mean`/`p_width`; no convertir ninguna de ellas directamente en un score de riesgo futuro.
3. Comparar los polígonos con los episodios oficiales SNMF/APN y las detecciones satelitales disponibles. Documentar cobertura y desfase, sin etiquetar automáticamente un día sin cicatriz como día vigilado sin fuego.
4. Probar cualquier modelo temporal con pronósticos que realmente estaban disponibles en cada instante (por ejemplo GFS de adelanto fijo) y temporadas/episodios reservados. Mantener aparte la detección de cicatriz, el peligro meteorológico y la ocurrencia próxima de un incendio.

El producto nacional mejora la disponibilidad de positivos históricos y de geometrías, pero no aporta el denominador de ventanas ruta-tiempo sin incendio con vigilancia conocida. Tampoco conserva las emisiones meteorológicas operativas usadas antes de cada evento. Por tanto, por sí solo no cierra los requisitos para estimar precisión positiva fiable en alertas de trekking.

## Adquisición en esta sesión

Los GeoTIFF anuales y mensuales sí se pudieron adquirir sin Earth Engine: el bucket público `mapbiomas-public` permite listar los objetos y descargar directamente cada año. Se verificó que existen 27 archivos mensuales y 27 anuales, 1999–2025, de modo que la discrepancia con la página de producto quedó resuelta a favor del inventario publicado más reciente del bucket y del ATBD de octubre de 2026. Se descargó temporalmente `monthly_burned-argentina_burned_monthly_2025.tif` (41.442.604 bytes); el MD5 calculado coincide con los metadatos de Google Cloud Storage. El análisis y sus resultados están en [`fire-mapbiomas-snmf-route-month-2025.md`](fire-mapbiomas-snmf-route-month-2025.md) y el JSON, y el script elimina la copia temporal.

El acceso anónimo al endpoint de metadatos de Earth Engine para `burned_area_polygons_v2` sí respondió HTTP 401 por falta de OAuth. Por eso no se descargó la capa vectorial con identificadores y fechas `date_min/date_med/date_max`; solo se usó el raster mensual, que no identifica polígonos de evento. Esta restricción afecta la asociación de cicatriz a incidente, no la descarga de rasters.

La fuente abierta identifica el uso de datos como público/gratuito sujeto a atribución (CC BY 4.0). Antes de redistribuir recortes, debe conservarse la atribución, URL de acceso, versión, fecha de consulta y hashes.

## Fuentes

- [Página oficial de MapBiomas Fuego Argentina](https://argentina.mapbiomas.org/iniciativas-y-productos/fuego/)
- [ATBD de MapBiomas Argentina Fuego, Collection 1, versión 1.0, octubre 2026](https://argentina.mapbiomas.org/wp-content/uploads/sites/8/2026/10/mapbiomas-argentina-fire-atbd-col01.pdf)
- [Repositorio técnico oficial MapBiomas/argentina-fire](https://github.com/mapbiomas/argentina-fire)
- [Portal de descargas de MapBiomas Argentina](https://argentina.mapbiomas.org/descargas/mapas-de-la-coleccion/)
- [Aviso oficial de publicación de la colección nacional](https://argentina.mapbiomas.org/2026/10/05/argentina-tiene-mas-superficie-agropecuaria-que-bosques-los-nuevos-datos-de-mapbiomas-muestran-como-cambio-el-territorio-desde-1985/)
