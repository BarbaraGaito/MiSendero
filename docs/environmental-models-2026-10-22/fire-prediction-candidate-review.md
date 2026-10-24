# Revisión de candidatos para una predicción fiable de incendios

Actualizado: 2026-10-22. Este documento separa tres tareas que no deben llamarse igual: estimar condiciones meteorológicas de peligro, estimar la probabilidad de que ocurra un incendio y detectar un fuego ya activo.

## Hallazgo principal

El índice FWI oficial de Córdoba no es una probabilidad de inicio de incendio. La guía de IDECOR dice expresamente que el FWI «no se relaciona con la probabilidad de ocurrencia» y que indica cuán peligroso podría ser un incendio si llega a producirse. El mapa operativo usa WRF, tiene resolución de 4 km y horizonte de 24 horas. Es un candidato defendible para comunicar **peligro meteorológico** en Córdoba, pero no para mostrar «probabilidad de incendio» ni para afirmar una precisión de ocurrencia sin una evaluación adicional.

La publicación de CONGREMET 2025 compara niveles del FWI operativo con focos de calor satelitales entre diciembre de 2022 y diciembre de 2024. Informa que, en general, la mayoría de los focos coincide con FWI Muy Alto o Extremo en verano, invierno y primavera, y que el índice subestima focos extremos en otoño. El resumen disponible no publica una matriz de confusión, precisión, sensibilidad, calibración ni resultados con días y celdas sin focos como negativos. Por tanto, respalda una asociación exploratoria, no una cifra de precisión transferible a la app.

## Evidencia local ya reunida

- MOD14A1/XGBoost: en la prueba temporal, 1 verdadero positivo frente a 30 incendios no detectados y 12.880 alertas sin coincidencia de etiqueta MODIS. El AP fue 0,000148 frente a prevalencia 0,000223. No es fiable.
- Auditoría espacial con dos eventos oficiales SNMF: 0 de 2 detectados dentro de 10 km al umbral fijado. La muestra es retrospectiva y demasiado pequeña para estimar precisión.
- GOES-19: el horizonte de una hora obtuvo precisión por fila de píxel de 70,27 % y recall de 19,12 % al umbral 0,5, pero apenas superó la persistencia en AP (0,3749 frente a 0,3706), con solo 136 positivos de prueba. Los datos son detecciones del mismo satélite y no equivalen a ignición, propagación ni seguridad de un sendero. Los horizontes de 2, 3, 6 y 12 horas no superaron la persistencia.
- En el cruce de GOES-19 con perímetros IDECOR, hubo 70 registros oficiales dentro de las huellas de muestreo fijadas (hasta 80 km de los centros de ruta) durante las fechas coincidentes y 218 observaciones GOES positivas; no se encontró coincidencia espacial-temporal bajo los radios probados de 2,5, 5 y 10 km y la ventana de ±1 día. Esto no basta para atribuir cada caso a un fallo del sensor —el perímetro puede tener una fecha de detección distinta de la actividad puntual y GOES observa con otra resolución—, pero tampoco corrobora la detección para trekking. El resultado está en `goes19-official-perimeter-matches.json`.
- IDECOR contiene 443, 446, 586, 675 y 165 perímetros publicados para 2022, 2023, 2024, 2025 y enero-junio de 2026. El centro de Quebrada del Condorito tiene 6 perímetros cartografiados a menos de 10 km en todo ese período; son registros de perímetros, no necesariamente seis incendios independientes. Esta cantidad no da una cohorte suficiente para demostrar precisión por sendero.

## Candidato con mejor sustento operativo

### Nueva vía verificable: pronóstico histórico WRF-SMN

La documentación oficial del SMN confirma que el pronóstico WRF está publicado en un bucket público de AWS desde abril de 2022, con NetCDF horarios de temperatura y humedad a 2 m, precipitación y viento a 10 m; el producto determinista tiene resolución aproximada de 4 km y llega hasta 72 h. La descarga está documentada sin credenciales. Este archivo permite formar un hindcast con pronósticos emitidos antes de la fecha válida, algo metodológicamente mejor que calcular el peligro usando clima observado después del hecho.

El siguiente candidato no será otro clasificador de focos activos: será un índice de **peligro meteorológico** a 24 h calculado a partir de la corrida histórica WRF-SMN, usando una formulación publicada para Argentina y etiquetas de perímetros/incidentes oficiales. Primero debe probarse en Córdoba, donde IDECOR aporta perímetros con geometría y fecha. No se afirmará probabilidad de ignición ni precisión fiable hasta resolver las alertas sin evento confirmado, separar incendios completos y alcanzar el criterio fijado en [`fire-reliable-precision-plan.md`](fire-reliable-precision-plan.md). El protocolo reproducible y sus limitaciones están en [`fire-smn-wrf-24h-protocol.md`](fire-smn-wrf-24h-protocol.md).

La cohorte WRF local cubre abril de 2022 a diciembre de 2023 y permitió entrenar un modelo meteorológico y evaluarlo temporalmente contra detecciones MODIS. En la comparación pareada por ruta-día, WRF obtuvo 15/16 coincidencias positivas, pero emitió 528 avisos frente a 267 del XGBoost anterior; su precisión proxy fue menor (2,84% frente a 4,49%) y no hubo umbral que alcanzara 90% con cinco avisos en validación. En una comprobación externa posterior, el modelo WRF no alertó en ninguno de cuatro inicios SNMF de 2025 cubiertos, al corte diagnóstico 0,5. Los archivos 2025 se obtuvieron por HTTP porque TLS falló localmente; esa prueba es exploratoria y debe repetirse por HTTPS antes de citarla como evidencia final. Ver [comparación por ruta-día](fire-weather-vs-satellite-route-day-review.md), [prueba WRF/SNMF 2025](fire-smn-wrf-snmf-2025-event-test.md) y [sensibilidad SNMF 2023](fire-smn-wrf-snmf-2023-radius-sensitivity.md). No se habilita este modelo en la app.

Para Córdoba, evaluar el FWI/FFMC/ISI diario del OHMC como índice de peligro a 24 horas, con el área quemada IDECOR como referencia de eventos y los focos VIIRS/MODIS como detecciones auxiliares. A escala nacional, el SNMF enlaza el mapa del SMN con clases de peligro para +24, +48 y +72 horas, calculadas con estaciones y GFS. El SNMF aclara que esas clases orientan sobre condiciones para inicio y control; siguen siendo **peligro meteorológico**, no probabilidades calibradas de ocurrencia.

Antes de estimar precisión hay que obtener una serie histórica de pronósticos con fecha de emisión y fecha válida; una captura del mapa actual o el FWI calculado a partir del tiempo observado no reemplaza el pronóstico que habría estado disponible ese día. El enlace operativo del SMN respondió 403 desde esta sesión y no se localizó un archivo público de mapas diarios históricos. Por eso aún no se pudo ejecutar una evaluación nueva del pronóstico oficial.

La evaluación debe dividirse cronológicamente y por evento, contar cada incendio una sola vez, definir con antelación una escala espacial acorde con los 4 km del mapa y revisar tanto los eventos como las alertas. Debe publicar la matriz de confusión, sensibilidad, precisión, tasa de falsas alarmas, intervalo de confianza y calibración si se emiten probabilidades. Si no se obtiene el histórico de pronósticos, solo corresponde evaluar o mostrar el FWI vigente como peligro meteorológico, sin atribuirle probabilidad de incendio.

- En el archivo 2025, al cruzar GlobFire con GOES-16 (enero-marzo), la unica ocurrencia elegible dentro de 10 km de un sector de ruta tuvo coincidencia: un pixel de alta calidad a 341 m del perimetro el dia inicial del evento. [Una fuente tecnica del INTA](https://www.argentina.gob.ar/sites/default/files/2025/07/revista_83.pdf) documenta el incendio de El Bolson iniciado el 30/01/2025 y activo durante semanas; esto corrobora que hubo un incendio real, pero sigue siendo una deteccion durante el evento, no una prediccion anticipada ni una estimacion de precision. Resultado: `goes16-globfire-matches.json`.
- Se descargaron las capas anuales GWIS GlobFire 2022-2024 y se cruzo la prueba temporal reservada julio-diciembre de 2023 del XGBoost MODIS (12.881 alertas de pixel-dia con score >=0,5). Con una regla exploratoria de eventos a menos de 40 km de los centros de sectores, 33 perimetros cayeron en esa cohorte; 3 tuvieron al menos una alerta a <=10 km durante las fechas con margen de +/-3 dias. Dos coincidencias fueron perimetros cercanos en Che Roga que comparten fecha/pixeles de alerta, por lo que podrian pertenecer a un unico episodio; no se cuentan como eventos independientes. Las coincidencias ocurren en la cola de las ventanas de incendio y no acreditan aviso anticipado. El cruce no permite llamar falsos a los avisos no corroborados ni estimar precision. Resultado: `modis-globfire-matches.json`.

## Candidato para ampliar el entrenamiento

GWIS publica archivos GeoPackage por anio `globfire_YYYY.gpkg.gz`. La version vigente cubre 2002-2025 y deriva de MCD64A1 Collection 6.1; no es compatible con la antigua serie 2002-2024. Los eventos tienen perimetro final y fechas estimadas con incertidumbre de varios dias; el algoritmo puede fusionar/dividir incendios y omite quemas menores a unos 86 ha. La evolucion consolidada fue discontinuada. Las capas 2022-2025 descargadas permiten auditar coincidencias, pero no son verdad de terreno independiente ni dan por si solas etiquetas diarias de ignicion.

## Próximos pasos de investigación

1. Descargar el subconjunto necesario del archivo p?blico WRF-SMN y formar una serie de meteorolog?a pronosticada con fecha de emisi?n y fecha v?lida; derivar y verificar un ?ndice publicado antes de mirar el test.
2. Reconciliar la geometría y la fecha de detección de los perímetros IDECOR con focos activos independientes en los años coincidentes.
3. Preparar el protocolo prospectivo de 24 h: guardar cada emisión diaria disponible para rutas argentinas, calcular las métricas sin reajustar umbrales en la cohorte de prueba y acumular temporadas completas.
4. Mantener deshabilitados los modelos actuales hasta superar el criterio de fiabilidad acordado con el objetivo de seguridad y respaldado por suficientes incendios independientes.

## Fuentes

- [IDECOR: guía de aplicación y alcance del FWI y sus componentes](https://obs-idecor-mapas-docs.obs.sa-argentina-1.myhuaweicloud.com/m442/Indice_FWI_y_componentes.pdf).
- [IDECOR: mapa diario del índice FWI](https://www.idecor.gob.ar/mapas/indice-meteorologico-de-peligro-de-incendios-fwi-diario/).
- [Maturano et al. (2025): evaluación del FWI calculado con WRF para Córdoba](https://cenamet.org.ar/congremet/wp-content/uploads/2025/11/A4_T096.pdf).
- [IDECOR: cartografía oficial de áreas quemadas](https://www.idecor.gob.ar/mapas-de-areas-quemadas/).
- [SNMF: mapa nacional de peligro y enlace al pronóstico SMN de 24/48/72 h](https://www.argentina.gob.ar/seguridad/servicio-nacional-de-manejo-del-fuego/evaluacion-de-peligro-y-alerta-temprana/mapa-de).
- [SMN: límites de interpretación de los mapas de peligro](https://www.smn.gob.ar/sites/default/files/mapasdepeligro.pdf).
- [NASA FIRMS: productos y acceso al archivo de focos activos](https://firms.modaps.eosdis.nasa.gov/content/active_fire/).
- [GWIS: catálogo y descarga de perímetros GlobFire 2002-2024](https://gwis.jrc.ec.europa.eu/apps/country.profile/downloads).
- [JRC: metodología y limitaciones temporales de los perímetros GlobFire](https://gwis.jrc.ec.europa.eu/about-gwis/technical-background/statistics).

No se sintetizaron observaciones ni se habilitó un artefacto de producción en esta revisión.

## Comprobación independiente de dos eventos de febrero de 2024

El parte diario oficial SNMF del 5/2/2024 registra Arroyo Creton, Río Negro, como activo con inicio ese día, y el Parque Provincial Ernesto Tornquist, Buenos Aires, con inicio el 3/2, 300 ha y extinción el 5/2. El Gobierno de Río Negro sitúa Brazo Tristeza entre las 2 y las 4 de la madrugada del 5/2. El cruce GOES-16/GlobFire detectó un píxel a 0,806 km del perímetro de Brazo Tristeza a las 18:00 UTC del mismo día; no halló detección con la regla fijada para Tornquist. La primera detección ocurrió después del inicio oficial: sirve como auditoría de detección de fuego activo, no predicción anticipada.

Esta corroboración independiente eleva la confianza en que las etiquetas corresponden a incendios reales, pero solo son dos eventos retrospectivos y no permiten afirmar precisión. Ver [auditoría de eventos oficiales](fire-goes16-2024-feb-official-event-validation.md) y [registro reproducible](fire-goes16-2024-feb-official-event-validation.json). La API Open-Meteo rechazó temporalmente la adquisición del pronóstico archivado de febrero de 2024 por una interrupción HTTPS; no se escribieron datos parciales ni se imputaron valores. La evaluación de GFS a 24 h permanece sin umbral seleccionado hasta recuperar y evaluar una cohorte más amplia.

Además, se contrastó el modelo WRF-SMN meteorológico a 27 h, entrenado con MODIS y congelado antes de su prueba de julio-diciembre de 2023, con incendios SNMF dentro de 10 km. Hubo dos días sector-ruta positivos; solo uno tuvo cobertura del modelo y ese caso recibió una alerta apenas por encima del score diagnóstico 0,5. El otro no se computa como error porque el sector quedó fuera de cobertura. Es evidencia independiente muy pequeña: no permite estimar precisión y confirma que la cobertura espacial también limita el uso del modelo. Ver [auditoría WRF-SMN/SNMF](fire-smn-wrf-snmf-route-event-audit.md).


## Fuente historica GFS

NOAA distribuye GFS historico tambien mediante un espejo en Google Cloud. Su catalogo contiene temperatura, humedad, viento, precipitacion y las horas de emision y validez desde 2015. El indice Haines esta disponible desde enero de 2025, pero no es una probabilidad de incendio. Las solicitudes de prueba a Google Cloud, WRF-SMN y Open-Meteo fueron interrumpidas por la conexion de esta sesion; no se adquirieron filas nuevas. Ver [auditoria de fuente GFS](fire-gfs-historical-forecast-source-audit.md).


## Cobertura de partes SNMF de 2025 cerca de las rutas

El inventario local confirma 207 partes para 2025 y 158 fechas sin PDF en los caminos consultados; seis PDFs no produjeron filas en la extraccion y quedan sin etiqueta hasta revisar el original. Se encontraron ocho registros de incidentes a menos de 10 km, agrupados en cuatro dias sector-ruta; a 20 km, 24 registros se agrupan en 15 dias. Esta muestra aporta positivos oficiales pero no negativos exhaustivos ni una base para estimar precision. Ver [inventario reproducible SNMF-ruta](fire-snmf-route-event-coverage-2025.md) y su JSON.

## Nueva prueba de umbral condicionado a fuego activo

Se anadio a la evaluacion GFS+GOES una politica conservadora que solo puede alertar si GOES ya muestra fuego en el sector al momento de emitir el pronostico. El corte se busca en validacion con un minimo de cinco avisos y precision observada de 80 %. Tampoco esta politica encontro un umbral que cumpla el criterio; no se evaluo un corte elegido a partir del test ni se habilito para la app. Esto confirma que la persistencia detecta continuidad mejor que el modelo general, pero la combinacion no acredita una alerta anticipada fiable. La conexion de Open-Meteo volvio a interrumpirse al solicitar mas historia de GFS para 2024, asi que no se amplio la muestra.


## Cruce independiente con incidentes SNMF de enero de 2026

El test GFS+GOES a 24 h se cruzo con partes oficiales SNMF que no participaron en el ajuste. Cuatro incidentes activos/controlados tuvieron cobertura a 10 km de un centro de sector: el score diagnostico 0.5 alerto en los cuatro (sensibilidad descriptiva 4/4; IC exacto 95 %: 39.8-100 %) y persistencia no alerto en ninguno. Es una senal prometedora de sensibilidad en los casos cubiertos, pero 87 de 91 incidentes no tuvieron una comparacion cubierta bajo la regla espacial; no hay negativos exhaustivos, el umbral no fue elegido en validacion y las fechas SNMF no dan hora de ignicion. No permite calcular precision ni demostrar anticipacion de 24 h. Detalle y nombres de eventos en [la auditoria independiente](fire-goes-gfs-24h-snmf-2026-jan-event-audit.md) y su [registro](goes-gfs-24h-snmf-2026-jan-event-audit.json).


## Umbral seleccionado en partes de diciembre y probado en enero

Se hizo una validacion temporal externa de coincidencia con partes SNMF: diciembre de 2025 eligio el umbral, enero de 2026 quedo para prueba. En diciembre, tras excluir dos dias con incidentes sin coordenadas y aplicar cobertura del modelo, quedaron 209 ruta-dias y solo tres positivos. El mejor corte que daba al menos cinco alertas obtuvo 3/80 = 3.75 % de precision proxy; no alcanzo el criterio del 90 %, por lo que no se selecciono umbral. En enero, el corte diagnostico 0.5 dio 27/133 = 20.3 % de coincidencia con partes (106 alertas sin incendio activo listado), con 29 positivos de parte y recall proxy de 93.1 %. La ausencia de registro no prueba ausencia fisica del fuego; estas metricas no son precision real. El resultado confirma que subir el corte no arregla por si solo el modelo. Ver [informe de umbral SNMF](fire-goes-gfs-snmf-proxy-threshold-evaluation.md) y [JSON reproducible](fire-goes-gfs-snmf-proxy-threshold-evaluation.json).


## Validacion ampliada con SNMF de octubre-diciembre de 2025

Se reentreno hasta septiembre y se reservaron octubre-diciembre (15 route-dias positivos proxy) para elegir el corte, con enero de 2026 como test posterior. Siete reportes del periodo no estaban disponibles, dos quedaron sin filas extraidas y ocho fechas tuvieron incidentes sin coordenadas; se excluyeron. Ningun umbral alcanzo el 90 % de coincidencia con el parte y cinco alertas. El mejor umbral con al menos cinco alertas coincidi? con 15/454 ruta-dias positivos (3.3 %). En enero, al corte diagnostico 0.5 no seleccionado, hubo 25/102 coincidencias (24.5 %) y 77 alertas sin incidente activo listado. En una comprobacion separada, los cuatro episodios SNMF cerca de rutas con cobertura fueron alertados, pero ese resultado no mide falsos positivos ni hora de anticipacion. El test de enero ya habia sido revisado en una exploracion previa; esta repeticion no se presenta como test virgen. Informe: [validacion Q4](fire-goes-gfs-snmf-q4-validation-report.md).


## Auditoria de fuentes para eventos completos y negativos

Se comprobaron las fuentes nacionales: la pagina del SNMF confirma una base historica de ocurrencia con inicio, finalizacion y ubicacion, pero no se encontro un extracto tabular nacional; los PDFs mensuales 2025 examinados publican conteos provinciales agregados y algunos son parciales. APN confirma la base de Partes Finales para areas protegidas, pero no se localizo un endpoint de descarga publica. IDECOR ofrece poligonos oficiales 2022-2025 solo para Cordoba y CONAE ofrece exportacion satelital CSV/SHP con inicio de sesion. Ninguna fuente actualmente accesible da negativos exhaustivos por sendero. La evidencia y los campos exactos que faltan estan en [auditoria de fuentes nacionales](fire-national-event-data-source-audit.md).
