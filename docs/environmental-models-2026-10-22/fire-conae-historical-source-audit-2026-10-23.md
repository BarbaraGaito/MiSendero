# Auditoría de la fuente histórica de focos de calor de CONAE

Fecha de revisión: 2026-10-23.

## Hallazgo

El catálogo oficial de [Consultas Interactivas: Incendios](https://catalogos5.conae.gov.ar/catalogofocos/) conserva series históricas de focos MODIS y VIIRS y permite filtrar por fecha, área, provincia, departamento, satélite e indicador de confianza. Su manual indica que la salida detallada contiene coordenadas WGS84, fecha y hora de cada foco, satélite/instrumento, potencia radiativa y, para VIIRS, confianza; la consulta admite hasta 400.000 registros.

La interfaz es de acceso público para consulta, pero el manual especifica que la **descarga** del CSV/SHP requiere iniciar sesión con una cuenta registrada en CONAE. No se descargaron ni se inventaron registros en esta revisión. El servicio WFS publicado en el catálogo geográfico ofrece capas GOES/MODIS/VIIRS recientes (últimos 10 minutos o últimas 24 horas); no equivale por sí mismo a una API de archivo histórico. La consulta directa al endpoint WFS desde esta sesión agotó el tiempo de espera.

## Valor para el proyecto

Es una fuente nacional y geolocalizada, adecuada para ampliar una cohorte independiente de detecciones positivas y comprobar coincidencias espacio-temporales con los modelos. La fecha/hora y los atributos del sensor permiten filtrar y agrupar las detecciones en episodios; los píxeles repetidos de un incendio no deben contarse como casos independientes.

Los focos de calor son detecciones satelitales de anomalías térmicas, no un censo perfecto de incendios. Una detección ausente no constituye una etiqueta negativa: puede faltar observación por la órbita, nubes, humo, resolución o cobertura. Por eso CONAE puede mejorar la corroboración de positivos, pero no permite afirmar precisión por sí sola ni justificar una probabilidad de incendio.

El producto mensual de áreas quemadas MODIS aporta una segunda corroboración retrospectiva. Su resolución temporal mensual y el hecho de que comparta la familia de sensores MODIS impiden tratarlo como verificación de hora exacta de ignición o como negativo exhaustivo.

Se encontró además una capa abierta del [Ministerio de Producción y Ambiente de Tierra del Fuego](https://prodyambiente.tierradelfuego.gob.ar/informacion-geoespacial-archivos-descargables/), con polígonos de bosque nativo afectado por incendios. Sus metadatos registran grandes eventos de 1978, 2008, 2012, 2013, 2019 y 2022, además de polígonos sin fecha determinada, compilados con Landsat, SPOT, imágenes, sobrevuelos y relevamiento de campo. Es una referencia independiente de perímetros para validación espacial en esa provincia; no ofrece por sí sola horas de ignición ni ventanas sin incendio. El archivo vectorial publicado no pudo recuperarse desde el conector web en esta revisión, aunque la página y sus metadatos sí están accesibles.

## Evaluación y siguiente paso

**Resultado:** candidato útil para evaluación, no suficiente para habilitar el modelo. Los experimentos actuales con GOES/GFS, WRF y reportes SNMF siguen sin estimar precisión de incendio real con incertidumbre aceptable. Cambiar pesos o umbrales con estas mismas cohortes tampoco resolvería la falta de negativos observados.

Cuando se disponga de la descarga, el experimento defendible es extraer detecciones CONAE de varias temporadas y corredores argentinos, deduplicar por episodio, separar una temporada final no usada para ajustar y emparejar cada alerta con el pronóstico histórico que ya estaba disponible antes de la detección. Las detecciones deben adjudicarse con reportes/perímetros oficiales independientes; los períodos sin detección deben quedar como desconocidos salvo que exista cobertura válida y una fuente de observación negativa explícita.

La descarga requiere registro CONAE. No se usaron credenciales, no se creó una cuenta y no se contactó a terceros.

## Fuentes oficiales

- [Catálogo interactivo de incendios CONAE](https://catalogos5.conae.gov.ar/catalogofocos/)
- [Manual de usuario del catálogo (PDF)](https://catalogos5.conae.gov.ar/catalogofocos/Docs/035_CONAE_AQUA_TERRA_NOAA20_MODIS_VIIRS_FC_VISOR_ManualUsuarios_e02.pdf)
- [Catálogo de geoservicios WMS/WFS de CONAE](https://catalogos.conae.gov.ar/catalogo/catalogoGeoServiciosOGC.html)
- [Actualizaciones del catálogo CONAE](https://catalogos.conae.gov.ar/catalogo/actualizaciones.html)
