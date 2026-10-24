# Detecciones abiertas del INPE cerca de rutas argentinas (2018–2025)

Se descargaron los archivos anuales `focos_ams_ref_YYYY.zip` publicados por el [Programa Queimadas del INPE](https://data.inpe.br/queimadas/portal/pages/secao_downloads/dados-abertos/), para Sudamérica entre 2018 y 2025. Los ocho ZIP se validaron con la comprobación CRC; sus hashes SHA-256 y el detalle de cada detección cercana están en el [JSON reproducible](fire-inpe-reference-detections-route-coverage-2018-2025.json). Los archivos originales quedan en el directorio privado ignorado por Git, no en la APK.

La búsqueda cubrió ocho centros de sectores de senderos argentinos y contó puntos del país Argentina a 5, 10, 20 y 50 km. En los ocho años aparecen 243 detecciones en el radio de 10 km, agrupadas en 80 días-sector; a 20 km hay 900 detecciones en 288 días-sector. Al radio estricto de 5 km quedan 81 detecciones en 23 días-sector. Estos días son positivos observados por satélite, no incendios necesariamente independientes: varios puntos pueden corresponder al mismo fuego y la serie no identifica por sí sola incendios forestales frente a quemas controladas o agrícolas.

| Radio desde el centro de sector | Registros de detección | Días-sector distintos |
|---:|---:|---:|
| 5 km | 81 | 23 |
| 10 km | 243 | 80 |
| 20 km | 900 | 288 |
| 50 km | 6.295 | 1.620 |

Como control de procedencia, se cruzaron los inicios SNMF con coordenadas a 10 km de esos mismos centros para 2023–2025. Hubo 14 días-sector de inicio reportado; dos tuvieron una detección INPE el mismo día y a 10 km (Cerro Ventana, 03/02/2024; Quebrada del Condorito, 10/10/2025). Es una coincidencia descriptiva, no una tasa de detección: una falta de foco satelital no demuestra que el incendio reportado sea falso, pues intervienen la hora de pasada, nubosidad, tamaño y ubicación del foco.

Esta fuente amplía los **positivos observados** y permite contrastar episodios de forma más independiente de los PDFs administrativos del SNMF. No resuelve el principal límite para estimar precisión: no ofrece días sin fuego confirmados ni una máscara completa de observabilidad para cada ruta y hora. El INPE también explica que la detección puntual puede faltar y que un foco no representa necesariamente un incendio único; sus detalles están en la [FAQ oficial](https://data.inpe.br/queimadas/pages/secao_informacoes/faq/index.html). Por eso los días sin registros se conservaron como desconocidos, nunca como negativos.

Tampoco hay un archivo histórico público encontrado para las emisiones T0–T3 que el capturador prospectivo está empezando a guardar. Los mapas del [Anuario de Risco de Fogo](https://data.inpe.br/queimadas/pages/secao_relatorio/anuario-risco-de-fogo/index.html) son útiles como índice histórico observado, pero el método incorpora focos previos; no deben tratarse como el pronóstico que estaba disponible antes de cada detección. La prueba de anticipación seguirá dependiendo de capturas prospectivas emparejadas con detecciones posteriores y con cobertura observacional válida.

La descarga acotada se reproduce con [`acquire_inpe_reference_detections.py`](../../training/python/acquire_inpe_reference_detections.py); el cruce espacial, con [`audit_inpe_reference_detections_routes.py`](../../training/python/audit_inpe_reference_detections_routes.py). No se entrenó ni habilitó un modelo con esta auditoría y no se afirma que la predicción actual sea fiable.
