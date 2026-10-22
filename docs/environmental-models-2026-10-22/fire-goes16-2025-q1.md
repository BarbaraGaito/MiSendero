# Estudio de caso GOES-16: verano de 2025

## Alcance

Para continuar el filtro de viabilidad, se procesaron las escenas originales de enero a marzo de 2025 en los mismos ocho sectores argentinos del estudio anterior. Las fechas cubren un trimestre completo e incluyen el incendio de El Bolsón, iniciado el 30 de enero de 2025 según la documentación pública del INTA. Este muestreo sirve para estudiar observaciones en zonas de trekking; no representa todo el país ni es una prueba imparcial de rendimiento predictivo.

## Resultados de cobertura

De 2.160 franjas horarias se obtuvieron 2.154 escenas Full Disk originales, con 3.899.079.496 bytes. Se muestrearon 1.858 píxeles por escena. El filtro de calidad produjo 190 filas positivas, 2.722.998 negativas y 1.278.944 excluidas. Los positivos ocurrieron en tres sectores, en 49 combinaciones de sector y día. Esas filas y fechas no son 190 incendios ni 49 incendios independientes: pueden ser observaciones repetidas del mismo fuego.

El 30 de enero hubo detecciones de alta confianza en los sectores muestreados de Refugio Frey y Bosque Tallado. La coincidencia de fecha con el incendio documentado en la zona de El Bolsón es consistente con una detección satelital útil, pero no alcanza para atribuir cada píxel al mismo incidente ni calcular la cobertura del incendio completo. El GOES identifica anomalías térmicas activas; no determina por sí solo si son incendios forestales, quemas u otras fuentes de calor.

## Demora

La fecha `date_created` de los archivos indica que la generación del producto ocurrió una mediana de 0,21 minutos después de terminar la escena, con percentil 95 de 2,33 minutos y máximo de 6,02 minutos. Esto mide generación del producto, no la hora exacta en que la aplicación habría podido consultarlo.

El `Last-Modified` del archivo archivado tuvo mediana de 0,66 minutos, pero un máximo de 34.672 minutos por cargas o modificaciones tardías. Por eso no se usa ese máximo como latencia real. NOAA describe Full Disk FDCF cada 10 minutos, pero estos artefactos históricos no prueban una latencia pública de 10 minutos ni un plazo de aviso garantizado.

## Decisión

El caso muestra que GOES puede registrar fuego de alta confianza en píxeles próximos a sectores de senderos y genera escenas frecuentes. **No se entrenó ni validó un clasificador**: 49 sector-días de positivos, concentrados en pocos lugares y una sola temporada, no ofrecen suficientes incendios independientes para afirmar precisión, sensibilidad o el máximo adelanto predictivo. Los horizontes de 30 minutos a 12 horas siguen sin poder seleccionarse de forma fiable.

Para la app, la hipótesis que merece una validación aparte es una alerta de **foco satelital observado recientemente**, que diga hora de observación, calidad y distancia, y que se abstenga cuando falten datos. No debe llamarse probabilidad de incendio futuro ni alerta confirmada. Antes de habilitarla hay que contrastar varios episodios oficiales, falsos positivos, cobertura de nubes y el sensor operativo. GOES-19 reemplazó GOES-16 como GOES-East en abril de 2025, por lo que el producto actual debe verificarse también con GOES-19.

## Archivos reproducibles

- Diseño: [fire-goes16-2025-q1-protocol.json](../../training/data/environmental/fire-goes16-2025-q1-protocol.json).
- Conteos y hashes: [fire-goes16-2025-q1-source-audit.json](fire-goes16-2025-q1-source-audit.json).
- Auditoría separada de fecha de producto y modificación del archivo: [fire-goes16-2025-q1-availability-audit.json](fire-goes16-2025-q1-availability-audit.json).
- Los NetCDF completos y las observaciones están en cachés locales ignoradas por Git; el manifiesto registra hashes SHA-256.

Fuentes del evento: [INTA, incendio de 2025 en El Bolsón](https://repositorio.inta.gob.ar/handle/20.500.12123/21842) y [Vialidad Nacional, 31 de enero de 2025](https://www.argentina.gob.ar/noticias/vialidad-nacional-dispuso-recursos-para-colaborar-en-el-incendio-de-el-bolson). Estado de satélite: [NOAA/OSPO](https://ospo.noaa.gov/operations/goes/status.html).
