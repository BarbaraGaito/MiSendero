# Auditoría de evaluación real — actualizada al 15/10/2026

Los resultados de esta página corresponden al entrenamiento histórico del 15/10. La [optimización del 25/10/2026](ai-optimization-2026-10-25/README.md) conserva datos, etiquetas y particiones y publica por separado los resultados posteriores y la evidencia de selección.

Requisito confirmado: mediciones de fuentes públicas y etiquetas publicadas u observadas independientemente de los predictores. No se permiten datos sintéticos en el repositorio: el pipeline no tiene data augmentation y la evaluación contiene cero filas sintéticas en entrenamiento, validación y test.

## Fuentes incorporadas

- **Fatiga: [GeoFatigue, University of Calgary](https://doi.org/10.5683/SP3/I0KSNR), versión 3.1.** Mediciones de pulso de Empatica y respuestas modificadas Borg durante tareas al aire libre con carga. Se conservan las respuestas numéricas como clases `Borg N`, sin convertirlas en bajo/medio/alto. Archivo fisiológico verificado contra MD5 publicado `eb81f58130436189ac416210db276c79`; originales y etiquetas fijados por SHA-256. El README depositado indica CC-BY-NC-SA 4.0 y la metadata del repositorio CC-BY 4.0: se aplica el alcance de investigación y no se aprueba despliegue comercial.
- **AMS: [Narang, Zenodo](https://zenodo.org/records/11505046), v2, CC-BY 4.0.** HR/SpO2 medias nocturnas y resultado observado `MOR_AMS+`, conservado como AMS+/AMS-. Son respuestas de personas reales a hipoxia física controlada equivalente a 4200 m; no datos generados por una simulación numérica. No valida una alerta instantánea durante trekking. Se usan 24 observaciones, una por participante, y ninguna variable demográfica como predictor.
- **Tramos: [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL, más [MDE-Ar del IGN](https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/Introduccion).** Snapshots originales del 13–14/10/2026 de Bariloche, El Chaltén, El Bolsón, Ushuaia, Mendoza, Calilegua y Condorito (este último sin sac_scale en el recorte). Se conservan IDs/versiones y etiquetas sac_scale nativas de `highway=path`. Distancia y sinuosidad provienen de geometría completa, y los predictores de elevación de 11 teselas IGN originales de 30 m. Un tramo sin elevación válida se excluye. No se usa `technical_score`, el propio sac_scale ni una transformación de la etiqueta como predictor.
- **Recorridos completos: [APN](https://www.argentina.gob.ar/parquesnacionales), CC BY 4.0 según términos del portal.** 52 fichas individuales de cinco parques, con dificultad publicada y distancia/duración estimadas por el organismo. Se conservan sentidos distintos y faltantes sin suponer recorridos de regreso. No son tiempos observados de personas. Esta tarea se mantiene separada de sac_scale. [Fuentes, exclusiones y protocolo argentino](datasets-argentina-2026-10-14.md).

Borg es una respuesta subjetiva observada y sac_scale una anotación comunitaria: cumplen independencia respecto del modelo, pero no garantizan una certificación objetiva de seguridad. Las cachés antiguas de OSM no tenían IDs/versiones y fueron excluidas aun cuando contenían tags sac_scale.

## Resultados realmente obtenidos

Accuracy significa coincidencia exacta con la clase nativa. Las tareas tienen distinta cantidad de clases y no deben compararse como si fueran el mismo problema. La referencia siempre predice la clase más frecuente **en entrenamiento**.

| Modelo | Filas públicas | Grupos train/test | Filas test | Accuracy | F1 macro | Accuracy referencia |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fatigue | 666 | 28/12 | 179 | 24.02% | 0.190 | 25.14% |
| physio_risk | 24 | 16/8 | 8 | 62.50% | 0.619 | 50.00% |
| route_difficulty | 288 | 4/2 regiones | 49 | 95.92% | 0.276 | 93.88% |
| apn_route_difficulty | 52 | 4/1 parques | 13 | 76.92% | 0.542 | 23.08–61.54% por empate |

Fatiga queda por debajo de su referencia. AMS conserva un test de solo ocho personas. En OSM, 46 de 49 tramos de test son hiking; el modelo agrega un acierto sobre predecir siempre esa clase, con F1 macro bajo. En APN hay empate entre baja y media en train (15 cada una): el desempate original conserva media, que acierta 3/13; baja acertaría 8/13. Se publican ambas alternativas sin elegir por el resultado de test. La CV F1 media es 0.222 para APN y 0.106 para OSM. Clases raras, pocos parques y escasa cobertura geográfica exigen más evidencia antes de usar los modelos en campo.

La evaluación OSM previa de 231 filas y ocho registros de test obtuvo 0% de accuracy. La ampliación cambió datos, predictores y partición geográfica: no demuestra por sí sola una mejora atribuible al IGN, ni es comparable directamente con aquella evaluación. Las nuevas regiones de test quedaron declaradas antes del ajuste.

## Protocolo y evidencia

Fatiga/AMS mantienen una sola partición GroupShuffleSplit por participante con semilla 42. APN reserva Tierra del Fuego completo; OSM reserva Ushuaia y Mendoza, declarados en el catálogo antes del ajuste. Las regiones/parques, caminos conectados, nombres y relaciones no cruzan particiones. Tuning mediante GroupKFold exclusivamente dentro de entrenamiento, con cuatro configuraciones fijadas. El test no participa en selección, fit ni CV. Cada ajuste usa únicamente filas observadas.

`training/data/public/sources.lock.json` y `source_catalog.json` fijan archivos/licencias/versiones. Cada familia conserva `dataset.csv`, `provenance.json`, `test_predictions.csv`, `metrics.json` y `model.forest.json`. Las filas del modelo no contienen identificadores personales ni ubicación exacta. La correspondencia a archivos y observaciones públicas queda en el manifiesto de auditoría. Se conservan las filas de test originales y sus predicciones para recalcular los resultados.

`npm run train:ai` ejecuta el nuevo pipeline. `npm run validate:ai-data` verifica hashes, particiones, etiquetas y accuracy/F1. `npm run test:ai-data` prueba filtraciones por grupos, que la validación cruzada ajusta solo filas observadas y rechazo de fuentes modificadas. Ver `ai/datasets/README.md` para instalación, descarga y reproducción. OSM es una fuente dinámica; conservar los snapshots verificados. Una nueva descarga que cambie un hash se rechaza y requiere una nueva auditoría, sin actualizar el lock automáticamente.

## Qué se eliminó

El 15/10/2026 se eliminaron del repositorio los antiguos CSV, entrenadores y bosques de bajo/medio/alto, el módulo de augmentation, el predictor histórico de rutas (`training/route-difficulty/`) y el script del backend que escribía sus predicciones en `trails.difficulty`. Quedan en el historial de Git. La app no incluye ningún modelo aprobado: el motor móvil se abstiene (`sin_datos`).

Los nuevos bosques son artefactos de investigación con `deployment_approved: false`. El panel muestra sus resultados y el alcance de cada fuente, separados de inferencia desplegable. Sus etiquetas/ventanas no equivalen a las antiguas categorías y ninguna conversión inventada se aplica para activarlos en la app.

## Motivo del reemplazo

PAMAP2/WESAD no proporcionaban las antiguas etiquetas de fatiga: el código asignaba velocidades por actividad, suponía pulso de reposo/máximo y calculaba etiquetas por umbrales. BIDMC aportaba mediciones hospitalarias, combinadas con velocidad/desnivel aleatorios y etiquetas de riesgo derivadas de reglas. La antigua dificultad se etiquetaba con fórmulas sobre los propios predictores. Se excluyeron todas esas filas del pipeline público nuevo.
