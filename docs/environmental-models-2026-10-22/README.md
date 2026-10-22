# Modelos ambientales: implementación y evidencia del 22/10/2026

Se conservan los cuatro clasificadores existentes, incluida la abstención de fatiga y AMS. Se agregó infraestructura común para nieve, nivel de río y detecciones de fuego. **Hay experimentos reales de nivel hidrométrico y de detección satelital de fuego; no hay tres modelos nuevos aprobados ni predicciones numéricas habilitadas para senderos.** No se publicaron cambios, no se migró una base remota y no se modificó el PDF de la tesis.

Actualización de alcance: la serie 32926 de Concepción del Uruguay queda excluida del proyecto activo y de las conclusiones para la tesis por pedido del usuario. La ciudad está en Entre Ríos, Argentina; la exclusión es de alcance, no de país. Los resultados anteriores quedan únicamente en `archive/` para trazabilidad y no sostienen las conclusiones actuales. Se obtuvo acceso público alternativo a las máscaras diarias MOD14A1 y QA para fuego; ver [fire.md](fire.md).

## Factibilidad comprobada

| Módulo | Evidencia obtenida | Entrenamiento y evaluación | Integración y límite actual |
|---|---|---|---|
| Nieve, próximo día | CMR: colección MOD10A1 v61 y tres metadatos de gránulo por cada una de tres regiones del catálogo | Detenido: no se descargaron píxeles científicos ni bandas QA; falta autenticación Earthdata | Contrato, API, almacenamiento y presentación de ausencia de estimación; sin probabilidades |
| Nivel de río, 3/6 h | 37.533 mediciones de dos series INA activas; unidades, coordenadas, fechas y hashes conservados | Cuatro experimentos; persistencia, lineal, RF y XGBoost; prueba cronológica y auditoría | No hay mejora del modelo seleccionado sobre persistencia en estas estaciones. Cero asociaciones aprobadas con senderos |
| Detección satelital de fuego, 24 h | MOD14A1 diario y QA descargados desde Planetary Computer; límites IGN/Georef; originales y hashes conservados | Pipeline causal, baselines, logística, RF y XGBoost; protocolo y resultados en los informes de fuego | La habilitación depende de pruebas temporales, geográficas y calibración; no implica alerta de incendios |

Los archivos [access-audit.json](access-audit.json), [river-results.json](river-results.json), [results-audit.json](results-audit.json) y [river-data-summary.json](river-data-summary.json) contienen la evidencia legible por máquina. Los originales grandes, modelos binarios, predicciones fila por fila y snapshots derivados quedan en carpetas ignoradas por Git. Los fixtures de software están separados en `testing/fixtures/environmental.cjs` y en los tests; nunca se usan para entrenar ni para informar métricas predictivas.

## Auditoría de la arquitectura existente

Se revisaron `ai/inferenceEngine.ts`, el entrenamiento `training/python/train_public.py`, los contratos de `backend/src/ai`, las rutas Express, migraciones PostgreSQL, `services/api.ts`, `services/offlineMaps.ts`, `services/syncQueue.ts`, la coordinación de sincronización y las pantallas de detalle, preparación y mapa activo. Se consultó la documentación de evaluación existente en `docs/`; las sugerencias de tesis nuevas están separadas en [thesis-suggestions.md](thesis-suggestions.md).

Se reutilizaron Expo Router, React Native, Express, PostgreSQL y SQLite. No se agregó framework, servicio cloud o dependencia nativa. XGBoost se agregó únicamente al entorno Python de investigación, con versión 3.4.1; no se ejecuta en el teléfono ni en una petición HTTP. Las estimaciones numéricas se calculan previamente en Python y se transportan como snapshots: no existe un segundo evaluador del árbol en JavaScript que pueda producir resultados diferentes.

## Nivel hidrométrico: fuente y preparación

La fuente seleccionada es la [API pública del INA](https://www.argentina.gob.ar/node/228063), que distingue observaciones y simulaciones. Se consultó el inventario real `https://alerta.ina.gob.ar/a5/obs/puntual/series?var_id=2&format=geojson`: devolvió 1.144 **series**, no 1.144 estaciones únicas. Las series activas 36964 y 37019 se descargaron mediante `/a5/obs/puntual/series/{id}?timestart=2023-01-01T00:00:00Z&timeend=2026-10-22T23:59:59Z`.

Se exige `var.id=2`, procedimiento de medición directa, estación real y unidad `m`. No se reinterpretan simulaciones ni otras variables como altura medida. La consulta se realizó el 22/10/2026; los primeros cachés preceden al registro automático de adquisición y por eso su instante exacto `retrieved_at` figura como nulo, con esa explicación. Sus bytes originales y SHA-256 sí están conservados. No se inventó una hora de descarga.

| Serie | Estación | Coordenadas [longitud, latitud] | Originales/admitidas | Intervalo mediano | Rango observado m |
|---|---|---|---:|---:|---:|
| 36964 | Iguazú – Pto. Iguazú | [-54,580000; -25,593333] | 33.599 / 33.599 | 0,5 h | 4,07 a 33,46 |
| 37019 | Manso – Los Moscos | [-71,641389; -41,353333] | 3.934 / 3.934 | 4 h | 0,51 a 1,50 |

Las primeras observaciones activas disponibles son de septiembre de 2024. Hay huecos y 37019 termina en julio de 2026. Los niveles son relativos al cero hidrométrico de cada estación, no alturas universales ni profundidades para cruzar. Los registros recibidos no presentaron duplicados conflictivos ni valores inválidos según los controles implementados; eso **no equivale a certificar la calidad física de cada sensor**. No se atribuye a estos datos la revisión consolidada del SNIH. El [portal SNIH](https://snih.hidricosargentina.gob.ar/) permite distinguir la información de sensores de los datos históricos consolidados.

Cada ejemplo tiene una hora UTC de emisión y como entrada las cuatro mediciones más recientes que ya tenían `timestart <= emisión` y `timeupdate <= emisión`. Se excluyen historias con menos de cuatro registros, último dato de más de 6 h o extensión histórica mayor a 48 h. Las variables son cuatro niveles, tres diferencias respecto del último nivel, antigüedad, extensión histórica y seno/coseno del día del año y de la hora. Los límites de frescura son controles de disponibilidad, no etiquetas de peligro.

La salida es el nivel **realmente medido** exactamente a emisión +3 h o +6 h. Si falta esa medición, se excluye el ejemplo: no hay interpolación, imputación, SMOTE, datos generados ni conversión de faltantes en cero. Los modelos ajustan el cambio observado respecto del último nivel; al predecir se vuelve a sumar ese nivel. Es una transformación invertible de una medición real, no una etiqueta sintética.

### Particiones y comparación

Las particiones son independientes por estación: entrenamiento con objetivos anteriores al 01/01/2025; validación de enero a junio de 2025; prueba de julio a diciembre de 2025. Se purgan objetivos que cruzan los cortes. Las etiquetas de entrenamiento y validación también deben tener `timeupdate` anterior a su corte, para evitar seleccionar modelos con etiquetas revisadas/publicadas después. Los datos de 2026 no intervienen en el ajuste ni en la selección ni en las métricas de prueba.

`timeupdate` es la actualización de la versión final recibida, utilizada como aproximación conservadora de disponibilidad. No se dispone de un registro de primera publicación ni de todas las revisiones históricas. Por eso la evaluación es retrospectiva y condicionada a ese metadato; no acredita una simulación operativa perfecta de lo que el servidor entregaba en cada instante.

Se comparan persistencia, regresión lineal con estandarización ajustada solo en entrenamiento, RF (150 árboles, profundidad 8, hoja mínima 5) y XGBoost (200 árboles, profundidad 3, tasa 0,05, objetivo cuadrático, hist, sin submuestreo). Semilla 42 y dos hilos. No se realizó búsqueda de hiperparámetros sobre el test. Se selecciona el menor MAE de **validación**, con preferencia por persistencia en empates. Se reportan todos los candidatos en prueba sin cambiar esa selección posteriormente.

| Serie/horizonte | Entrenamiento | Validación | Prueba | Seleccionado por validación | MAE seleccionado m | RMSE seleccionado m | MAE persistencia m |
|---|---:|---:|---:|---|---:|---:|---:|
| 36964 / 3 h | 2.002 | 3.710 | 3.578 | RF | 0,71671 | 1,52456 | 0,69433 |
| 36964 / 6 h | 2.000 | 3.703 | 3.570 | RF | 0,88900 | 1,84246 | 0,84788 |
| 37019 / 3 h | 561 | 944 | 880 | Persistencia | 0,00500 | 0,01259 | 0,00500 |
| 37019 / 6 h | 574 | 993 | 935 | Persistencia | 0,00707 | 0,01749 | 0,00707 |

Los resultados mensuales completos de las estaciones activas están en el JSON. Los meses no se presentan como eventos de inundación identificados independientemente. La comparación no respalda una mejora del ML en las estaciones conservadas.

36964 empeora frente a persistencia y tiene RMSE alto. Aunque la lineal obtiene menor MAE en el test de 3 h, no se la selecciona usando ese resultado: eso sería aprovechar el conjunto reservado. En 37019 gana persistencia; no se presenta como un logro del ML. Los cuatro artefactos activos tienen `visualization_allowed:false` y `deployment_approved:false`.

La auditoría independiente recalculó MAE/RMSE de cuatro candidatos, identidades de filas, objetivos exactos, fechas de disponibilidad, conteos de particiones y hashes de las 8.963 predicciones de prueba activas. No sustituye una validación prospectiva. No se evaluó transferencia a otra estación, otro río o un cruce de sendero; no hay intervalos de predicción calibrados ni evaluación específica de crecidas extremas. Un MAE histórico no es una cota del error futuro.

### Aplicabilidad a senderos

No se encontró evidencia suficiente para aprobar una relación estación–curso–sector de sendero. Ni una estación del Iguazú representa automáticamente el arroyo Arrechea, ni una estación del Uruguay representa por proximidad cualquier recorrido de El Palmar. El registro `backend/src/data/environmentalModels.json` conserva `reviewed_route_associations:[]`. Se pueden calcular niveles experimentales de estación, pero **no se muestran valores numéricos en rutas del catálogo**.

Para habilitar una relación se necesita cartografía o documentación pública que identifique el mismo curso y sector representado, identificador real del sendero en la base, hash de su geometría, estación, río, fecha de revisión y fuentes HTTPS. Agregar una relación al JSON es una acción de revisión de evidencia; no debe autocompletarse por distancia. La importación contrasta la geometría con la ruta real de PostgreSQL y la lectura vuelve a comprobar la asociación, permitiendo revocarla.

## Nieve: acceso comprobado y trabajo pendiente

[MOD10A1 v6.1](https://nsidc.org/data/mod10a1/versions/61) es un producto diario de 500 m en grilla sinusoidal. Se descubrió la colección CMR `C2565093311-NSIDC_CPRD`, cuyo identificador de versión es `61` (los nombres de archivo incluyen `061`). Se consultaron metadatos del 1 al 3 de julio de 2025 en Refugio Frey, Mirador de los Cóndores y Pampa Alta; sus coordenadas y fuentes provienen del catálogo existente, exportadas en `training/data/environmental/geography.json`.

Los metadatos públicos no son observaciones de nieve. Los HDF científicos están protegidos por Earthdata y no se descargaron; tampoco se procesaron píxeles, QA, reproyección ni altitud IGN. La cuenta gratuita debe configurarse localmente mediante el método oficial, sin subir credenciales al repositorio. La documentación del producto exige citar su DOI.

Una vez habilitado el acceso, faltan adquisición de originales, verificación de bandas/calidad, exclusión de nubes/oscuridad/agua/fill, correspondencia IGN, disponibilidad real de cada producto y particiones espaciales/temporales. La publicación puede ser posterior al día observado: no debe usarse la fecha del píxel como disponibilidad. Solo entonces corresponde comparar persistencia/logística/RF/XGB y reportar accuracy, precision, recall, macro-F1, confusión y calibración. No hay esas métricas en este trabajo porque no hay etiquetas adquiridas.

## Fuego: acceso diario y evaluación independiente

El [archivo FIRMS](https://firms.modaps.eosdis.nasa.gov/download/) solicita autenticación Earthdata o código por correo; no se ingresaron datos personales ni se solicitaron envíos. Distingue datos NRT de calidad científica, con reemplazo de aproximadamente cinco meses. MODIS y VIIRS tienen distinta resolución y cobertura; no se mezclaron registros entre sensores. No se descargó un CSV científico para entrenamiento.

Se verificó la [API ORNL](https://modis.ornl.gov/data/modis_webservice.html) y su [catálogo real](https://modis.ornl.gov/rst/api/v1/products): ofrece MOD14A2/MYD14A2 de ocho días, sin MOD14A1 diario ni MOD10A1. Un compuesto de ocho días no se convierte en etiqueta de 24 h. Un CSV de detecciones positivas tampoco prueba que los demás sectores hayan sido observados sin fuego.

Ese impedimento inicial de acceso se resolvió con la colección pública MOD14A1 de Planetary Computer: se descargaron máscaras diarias y QA y se conservaron los originales. La metodología, los cambios de muestreo antes de ajustar modelos, las particiones, métricas y límites se documentan por separado en [fire.md](fire.md), `fire-source-audit.json` y `fire-results.json`. MOD14A1 contiene días separados dentro de un archivo; no es el resumen MOD14A2. [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries) no se usó. El módulo no estima propagación, evacuación ni seguridad ante incendios.

## Backend, app y modo sin conexión

El contrato compartido está en `backend/src/contracts/environmental.{js,d.ts}` para incluirse en la imagen Docker y en Expo. Versiona modelo, esquema, geometría, evidencia, fuente, observación, disponibilidad de entradas, emisión, objetivo y vencimiento. Diferencia `available`, `experimental`, `no_data`, `not_approved`, `expired` y `error`; un estado sin información no lleva número. Se valida orden temporal, valores finitos, horizonte y checksum SHA-256 del lote. El checksum detecta corrupción; no es una firma criptográfica de autenticidad.

`GET /api/trails/:id/environmental` lee snapshots precalculados; no descarga datasets, llama a NASA ni entrena en una petición. La migración `015_environmental_snapshots.sql` es aditiva. Ante un artefacto inhabilitado, cambio de geometría, evidencia incompatible o asociación revocada, se omite la predicción. Una falla de almacenamiento produce estado `error`, sin inventar un resultado.

Python exporta estados de estación a `training/data/environmental/private/station-forecasts.json` y diagnósticos de fuego a `fire-forecasts.json` en la misma carpeta. Tras la exclusión de alcance no hay modelos hidrométricos habilitados; fuego no superó su evaluación. El exportador Node prepara lotes de ruta solo con modelos habilitados, relaciones previamente revisadas y valores vigentes. Hoy genera **cero lotes**. El importador permite previsualizar y solo aplicar a una base local explícita; usa transacción e importación idempotente. No se configuró cron ni publicación automática.

La app consulta el módulo en detalle, preparación y el panel «Ambiente» del mapa activo. Diferencia último nivel observado y predicción, muestra fecha, modelo, alcance, error histórico, limitaciones y fuente. Los reportes/avisos oficiales conservan sus flujos existentes; los estados ambientales no los reemplazan. No se emiten alertas clínicas, instrucciones de cruce ni recomendaciones de evacuación.

SQLite suma `environmental_json` al paquete ya existente de mapas, aislado por cuenta. La descarga conserva el snapshot validado; una falla ambiental no impide verificar los mosaicos. La lectura local verifica geometría y checksum. Sin red se conserva el valor descargado y, al vencer, se rotula explícitamente como histórico; no se genera una inferencia nueva. La sincronización de paquetes intenta refrescar después de 15 minutos y las pantallas también al reconectar. Un fallo de proveedor conserva el caché anterior. Las operaciones de GPS, registro, pausa y SOS no dependen del resultado ambiental.

## Reproducción y límites operativos

En Windows usar `npm.cmd` si PowerShell bloquea `npm.ps1`. Desde la raíz:

```powershell
# Crear/usar el entorno local; el lock reproduce las dependencias del experimento.
py -m venv .venv-ai
.venv-ai\Scripts\python.exe -m pip install -r docs/environmental-models-2026-10-22/requirements-lock.txt
npm.cmd run fetch:environmental
npm.cmd run train:environmental:river
npm.cmd run validate:environmental
npm.cmd run predict:environmental
npm.cmd run test:environmental:data
npm.cmd run typecheck
npm.cmd test -- --runInBand
npm.cmd --prefix backend run build
npm.cmd --prefix backend test -- --runInBand
```

`fetch:environmental` usa cachés existentes y verifica sus hashes; `-- --refresh` renueva explícitamente las dos series INA activas, conservando la versión anterior por hash en `training/data/raw/environmental/archive`. Esto puede cambiar la evidencia y requiere reentrenar/evaluar. Para reproducir exactamente esta corrida se necesitan los originales locales con los hashes registrados: una API viva puede revisar su histórico. El lock y [environment.json](environment.json) describen las dependencias de esta ejecución; no se promete igualdad binaria entre plataformas.

`train:environmental:snow` termina con error explicativo porque no se adquirieron observaciones nivales. Fuego tiene comandos separados y requiere las máscaras y QA descargadas: `fetch:environmental:fire`, `train:environmental:fire`, `validate:environmental:fire` y `fetch:environmental:fire:recent`. La auditoría de resultados requiere los originales y CSV privados de prueba; falla si faltan, en lugar de verificar únicamente el JSON agregado.

Cuando exista evidencia válida de asociación, `predict:environmental` dejará archivos `route-{id}-snapshots.json` en la carpeta privada. Para una base **local de pruebas** ya configurada:

```powershell
# Aplicar previamente las migraciones habituales solo a esa base local.
node backend/scripts/importEnvironmentalSnapshots.js --file training/data/environmental/private/route-123-snapshots.json
# La primera orden solo previsualiza; aplicar requiere el indicador explícito.
node backend/scripts/importEnvironmentalSnapshots.js --file training/data/environmental/private/route-123-snapshots.json --apply --local-only
```

`123` es un ejemplo de identificador, no una asociación aprobada ni un archivo entregado. Estas órdenes no se ejecutaron sobre una base real. No se distribuyen observaciones INA en Git porque el acceso público no aclara por sí solo sus términos de redistribución. Citar el organismo, la consulta y los hashes; antes de redistribuir originales, resolver las condiciones de uso.

La validación de software ejecutada cubre contrato, API, preview/aplicación idempotente en base aislada, aprobación, ausencia y vencimiento, asociación revocada, geometría, integridad, almacenamiento SQLite, cuentas, reconexión y conservación de mapas. La evidencia y las limitaciones finales de las pruebas están en [verification.md](verification.md). No se realizó una salida de campo ni validación visual en un dispositivo físico.

El registro JSON de artefactos se carga al iniciar Node. Después de regenerarlo, el servidor local debe reiniciarse para utilizar esa versión; este trabajo no instaló un servicio de recarga ni un planificador de lotes.
