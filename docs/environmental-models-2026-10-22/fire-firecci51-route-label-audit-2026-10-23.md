# Auditoría de FireCCI51 en corredores de senderismo

## Fuente y posibilidad de uso

Se probó el producto oficial ESA Fire_cci MODIS Burned Area Pixel v5.1, tile AREA_2 de Sudamérica. CEDA indica que los datos 2001–2022 son de acceso público también para usuarios no registrados. El tile descargado se distribuye por mes; tiene resolución aproximada de 250 m y aporta fecha estimada de quemado (JD), clase de cobertura y nivel de confianza (CL). En JD, `0` significa no quemado durante el mes, `-1` no observado y `-2` no combustible; únicamente los valores positivos son píxeles asignados a una fecha estimada de quema.

En esta cohorte local se descargaron siete tiles mensuales de 2022 (enero, febrero, marzo y septiembre–diciembre; 23–26 MB cada uno, comprimidos). El análisis muestreó círculos de 10 km alrededor de los ocho centros de sector de ruta. El script y sus SHA-256 están en [`audit_firecci51_route_sample.py`](../../training/python/audit_firecci51_route_sample.py) y [`firecci51-route-sample-2022-fire-season.json`](firecci51-route-sample-2022-fire-season.json).

## Resultado de cobertura

En enero, febrero y marzo hubo 304, 182 y 561 píxeles quemados respectivamente en los ocho buffers; todos se concentraron en el sector Sendero Che Roga–Mburucuyá. De esos 1.047 píxeles, 1.017 tenían CL ≥ 80. No son 1.047 incendios independientes: son celdas agrupadas en el espacio y en episodios de la misma zona. Entre septiembre y diciembre no apareció ningún píxel quemado en esos buffers; en septiembre–noviembre sí hubo píxeles `-1` no observados, que se excluyeron. El resultado cubre una sola temporada y una sola ruta con positivos; no permite afirmar generalización a los otros senderos.

## Cruce con un incidente oficial

El parte del SNMF del 9/3/2022 informa el incendio “PN MBURUCUYA”, iniciado el 22/2/2022, en las coordenadas 28° 2′ 44″ S, 58° 0′ 37″ O, y extinguido el 8/3/2022. El punto reportado está a 3,551 km del centro del sector Che Roga. Con una regla exploratoria fijada para esta auditoría —radio de 10 km y ventana desde tres días antes del inicio hasta tres días después de la extinción reportada— FireCCI encontró:

- 23/2: 242 píxeles dentro del radio, 241 con CL ≥ 80; el más cercano queda a 1,476 km del punto oficial.
- 2/3: 557 píxeles, 548 con CL ≥ 80; el más cercano queda a 48 m.
- También hay detecciones en fechas intermedias y hasta el 9/3; se incluyen en el JSON reproducible.

La coincidencia es evidencia independiente de que hubo un incendio con cicatriz cerca del recorrido y de que FireCCI mapeó el evento. Los píxeles pertenecen a un episodio, no son casos separados. El parte aporta fecha de inicio de día y fecha de extinción, no hora exacta ni perímetro de campo.

## Qué resuelve y qué falta

FireCCI51 mejora la posibilidad de evaluar una **cicatriz quemada** con fechas diarias estimadas y negativos mapeados dentro de un mes. No valida por sí sola el inicio horario, el adelanto de una alarma ni la precisión de un predictor. Es un producto MODIS y su algoritmo utiliza información de focos activos MODIS; por eso no es completamente independiente de un modelo que use MODIS, aunque ofrece una clasificación de área quemada separada. La documentación de Copernicus advierte que la resolución temporal es mensual, que la cobertura de nubes puede causar faltantes y que el desempeño depende del año y del tamaño del incendio.

El siguiente experimento posible es usar una temporada futura al ajuste, geometrías completas de los senderos y una unidad por episodio, contrastando con perimetraje/incidentes oficiales y conservando `no observado` como desconocido. Antes de afirmar precisión siguen faltando más episodios independientes cerca de rutas y ventanas negativas con cobertura válida. La evaluación actual del modelo de la app continúa siendo insuficiente; este cruce no cambia esa conclusión.

## Fuentes

- [Registro de datos CEDA: acceso público, licencia y versión 2001–2022](https://catalogue.ceda.ac.uk/uuid/58f00d8814064b79a0c49662ad3af537/)
- [Portal ESA Fire_cci](https://climate.esa.int/en/catalogue/58f00d8814064b79a0c49662ad3af537/)
- [Especificación ESA de los tiles; AREA_2 cubre Sudamérica](https://climate.esa.int/documents/2793/Fire_cci_D1.2_PSD_v7.1.pdf)
- [Parte oficial SNMF del 9/3/2022](https://www.argentina.gob.ar/sites/default/files/2021/09/reporte_diario_09-03-2022.pdf)
- [Descripción de calidad y límites temporales de Copernicus](https://cds.climate.copernicus.eu/datasets/satellite-fire-burned-area?tab=quality_assurance_tab)
