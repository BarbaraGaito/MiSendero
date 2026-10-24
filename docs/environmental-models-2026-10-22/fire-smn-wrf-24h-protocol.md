# Evaluaci?n candidata: clima WRF-SMN para fuego satelital a 27 h

Estado: experimento de investigaci?n, sin aprobaci?n para la app.

## Objetivo y alcance

Se prob? si el pron?stico meteorol?gico p?blico del SMN mejora el ordenamiento de detecciones de fuego de MODIS para las ubicaciones muestreadas de senderos argentinos. El objetivo observado es una detecci?n satelital nominal/de alta confianza en el mismo p?xel y fecha. No es el inicio de un incendio, su propagaci?n, una probabilidad calibrada ni una garant?a de seguridad para un sendero.

La corrida se emiti? a las 12 UTC del d?a anterior y se evalu? para las 15 UTC de la fecha objetivo: **27 horas de adelanto**. Las variables horarias de temperatura, humedad, viento y precipitaci?n se combinaron con Tmax/Tmin diarios pronosticados. Se us? una regresi?n log?stica ponderada por clase con regularizaci?n fija, sin b?squeda de hiperpar?metros. El umbral solo pod?a elegirse con validaci?n si alcanzaba 90 % de precisi?n observada con al menos cinco alertas por zona-d?a.

## Fuentes y procesamiento

El SMN publica en AWS el archivo WRF determinista con pron?sticos horarios NetCDF. Dos muestras comprobadas contienen temperatura y humedad a 2 m, viento a 10 m, precipitaci?n, Tmax/Tmin y una grilla de aproximadamente 4 km. Para 2022-2023 se procesaron 591 fechas disponibles y 3.191 p?xeles por fecha. Cada fuente se identific? con URL y SHA-256; los NetCDF se eliminaron tras extraer las variables muestreadas. Hubo tres fechas con 404 confirmados; una fecha que fall? por timeout se recuper? al reintentar. Los huecos quedan excluidos, nunca se convierten en d?as sin fuego.

Las etiquetas proceden del producto NASA MOD14A1.061 y conservan ?nicamente observaciones terrestres con m?scara de calidad v?lida. Se excluyeron las celdas dudosas, nubes, agua y faltantes. No se generaron etiquetas sint?ticas.

## Separaci?n

- Entrenamiento: fechas objetivo anteriores al 1/1/2023.
- Validaci?n: 1/1/2023 a 30/6/2023; se reserv? para elegir el umbral.
- Prueba temporal: 1/7/2023 a 31/12/2023; no se us? para ajustar el modelo ni el umbral.
- Se excluy? de estas particiones la zona geogr?fica reservada en el protocolo MODIS original.

Este periodo se hab?a usado antes para evaluar otro modelo de MiSendero, por lo que la prueba temporal es independiente de este ajuste pero **no es un test virgen a nivel de toda la investigaci?n**. Las cifras sirven como evidencia exploratoria, no como validaci?n final de tesis.

## Resultados

El modelo mejor? la m?trica de ranking, pero no encontr? un punto de alerta ?til:

| Unidad | AP modelo | AP de prevalencia | Resultado al score 0,5 |
|---|---:|---:|---|
| P?xel-d?a, validaci?n | 0,000166 | 0,000036 | 11/13 detecciones; 67.760 alertas falsas |
| Zona-d?a, validaci?n | 0,0323 | 0,00982 | 9/10 positivos; 422 falsas alarmas |
| P?xel-d?a, prueba temporal | 0,000532 | 0,0000902 | 23/31 detecciones; 92.321 alertas falsas |
| Zona-d?a, prueba temporal | 0,0546 | 0,0157 | 15/16 positivos; 513 falsas alarmas |

La mejor precisi?n de validaci?n con al menos cinco alertas por zona-d?a fue **5/118 = 4,24 %** (intervalo exacto del 95 %: 1,39?9,61 %). No se eligi? ning?n umbral porque el requisito de 90 % no se cumpli?. En la prueba, el score 0,5 produjo una precisi?n de zona-d?a de 2,84 % (15/528; intervalo exacto 1,60?4,64 %). El score es un puntaje de ranking, no una probabilidad: `0,5` no significa 50 %.

El modelo da una se?al de ranking superior a la prevalencia simple y al AP del XGBoost MODIS anterior, pero los avisos producen demasiadas falsas alarmas y el conjunto contiene solo 22 p?xeles-d?a positivos de entrenamiento, 13 de validaci?n y 31 de prueba. Por eso **no es una predicci?n fiable para recomendar o desaconsejar un trekking**.

## Pr?ximo experimento

El siguiente candidato con etiquetas m?s ?tiles es entrenar y evaluar una predicci?n de **?rea quemada mapeada** con los per?metros oficiales IDECOR para C?rdoba y el archivo WRF-SMN. Esa tarea es distinta de predecir una ignici?n: el resultado se limitar?a a si hubo ?rea quemada cartografiada en una celda/fecha. Se deber? definir la unidad espacial, el tratamiento de fuegos peque?os y fechas aproximadas, y reservar temporadas completas. Si el objetivo final sigue siendo alertar fuego activo cerca de senderos en toda Argentina, hacen falta m?s episodios independientes y un inventario de alertas confirmadas/no confirmadas alrededor de esos recorridos.

En paralelo, el FWI/FFDI oficial puede utilizarse como **clase de peligro meteorol?gico** a 24/48/72 h. Esa clase no debe presentarse como probabilidad de inicio de incendio. El SNMF describe su mapa como ?ndice meteorol?gico, y el SMN advierte que no incorpora combustible ni topograf?a y que sus l?mites espaciales no son exactos.

## Fuentes

- [SMN: pron?stico WRF de alta resoluci?n sobre Argentina](https://odp-aws-smn.github.io/documentation_wrf_det/)
- [SMN: estructura y plazos de los archivos NetCDF](https://odp-aws-smn.github.io/documentation_wrf_det/Estructura_de_datos/)
- [SMN: acceso an?nimo al bucket AWS](https://odp-aws-smn.github.io/documentation_wrf_det/Acceso_a_los_datos/)
- [Registro Open Data AWS: cobertura, resoluci?n, variables y licencia](https://registry.opendata.aws/smn-ar-wrf-dataset/)
- [Arga?araz et al. (2018): sistema operacional FFDI-LFMC para Argentina](https://fcefyn.unc.edu.ar/documents/1647/Arga%C3%B1araz2018_Operational_Meteo_Fire_Danger_System-1.pdf)
- [SNMF: alcance del mapa nacional de peligro +24/+48/+72 h](https://www.argentina.gob.ar/seguridad/servicio-nacional-de-manejo-del-fuego/evaluacion-de-peligro-y-alerta-temprana/mapa-de)
- [SMN: l?mites de interpretaci?n del mapa FWI](https://www.smn.gob.ar/sites/default/files/mapasdepeligro.pdf)

