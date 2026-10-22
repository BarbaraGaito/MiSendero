# DUO-GAIT: evaluación de fatiga inducida al caminar con una muñeca

Fecha: 22 de octubre de 2026. [Datos originales](https://zenodo.org/records/8244887), [publicación de los autores](https://doi.org/10.1038/s41597-023-02391-w), [código original](https://github.com/HPI-CH/fatigue-dual-task-data).

## Qué permite estudiar

DUO-GAIT incluye 16 personas que caminaron antes y después de un protocolo de agotamiento con levantamientos repetidos de una silla y chaleco con carga. Cada persona tiene una visita de caminata simple (`ST`) y otra con una tarea mental simultánea (`DT`), en pasillo interior. Se conservan las condiciones originales `control` y `fatigue`; no se crean etiquetas a partir del pulso, del tiempo o de un umbral elegido por MiSendero.

La tabla original confirma en `ST` **16/16 respuestas Borg de 15,5 a 18,5** tras el protocolo. El lactato aumentó en las 16 personas respecto de la media de sus dos mediciones de reposo: medias basales de 0,55–1,55 mmol/L y valores posteriores de 1,7–8,8 mmol/L. En `DT`, las 16 respuestas Borg están entre 16 y 18,5 y el lactato posterior entre 2,5 y 10,2 mmol/L; faltan ambas mediciones basales de lactato de `sub_18`. No se imputan. Borg y lactato respaldan la manipulación experimental, pero el lactato aislado no equivale a una medición completa de fatiga.

Las referencias se recogieron tras el ejercicio de agotamiento, antes de la segunda caminata. **No se predice retrospectivamente ese Borg con datos posteriores:** el objetivo es clasificar la condición original de cada caminata. La persistencia y recuperación de la fatiga dentro de esos seis minutos no tienen una referencia independiente por ventana. Por ello no se evalúan el instante de aparición de fatiga, su intensidad continua ni alertas durante trekking.

## Datos descargados e integridad

Se recuperaron únicamente los **64 CSV completos de muñeca izquierda**, cuatro por persona, que suman 271.814.213 bytes sin comprimir, aproximadamente 98,7 MB comprimidos. Se leyeron miembros individuales mediante rangos HTTP para evitar descargar todo `interim.zip`, de 3.025.750.473 bytes. Se validaron estado HTTP 206, rango y longitud; las respuestas incompletas se rechazaron. Cada CSV se verificó con el CRC32 del índice ZIP remoto y se registró su SHA-256 local. **No se verificó el MD5 del ZIP completo**, porque no se descargó entero. Esta limitación no debe sustituirse por una afirmación de integridad completa del depósito.

Se leyeron además `raw/subject_info.csv` e `interim/interruptions.csv` por el mismo mecanismo. El informe conserva solo las columnas de referencia Borg/lactato de la primera tabla, sin las variables demográficas. Los originales de sensores, índices y metadatos quedan bajo `training/data/raw/duo-gait/`, excluidos de Git. [Descargador reproducible](../../training/python/download_duo_wrist.py), [lector de rangos](../../training/python/duo_gait_remote.py).

La aceleración original está en `g` y se convierte a m/s² multiplicando por 9,80665; el giro está en grados/s. El tiempo se lleva al inicio de cada segmento. Las conversiones y el origen temporal siguen [el código de los autores](https://github.com/HPI-CH/fatigue-dual-task-data/blob/60285b72750fd91bb2634daeacbdd5611c520644/src/data/imu.py). Los intervalos observados corresponden a aproximadamente 128 Hz. Las duraciones completas de los 64 segmentos van de 370,31 a 419,84 segundos.

## Ventanas, participantes y método fijo

Antes de consultar el resultado del clasificador se fijó el mismo intervalo **20–320 segundos**, cinco minutos desde un inicio común respecto del segmento manual de los autores, para todas las grabaciones. Se usan ventanas consecutivas de cinco segundos sin superposición. No se selecciona un porcentaje de la duración final ni se utiliza la duración futura como entrada. La segmentación manual y las anotaciones de pausa pertenecen al dataset; reconocer automáticamente la marcha y las pausas durante el uso de la app queda fuera de esta prueba.

Se exige señal finita, tiempo creciente, al menos 600 muestras por ventana y ningún hueco interno o de borde mayor de 25 ms. Se excluyen ventanas que se superponen con las interrupciones anotadas por los autores, interpretadas desde el inicio del segmento. De **3.840 ventanas candidatas** se excluyeron 11 por interrupciones y se conservaron **3.829 (99,71 % del intervalo seleccionado)**: 1.917 de `ST` y 1.912 de `DT`. Esa cobertura no representa el porcentaje de toda la visita: solo puntúa los cinco minutos fijados de cada segmento.

El modelo fijo usa 14 características: media, desviación, mediana, percentiles 10 y 90, RMS y rango, para cada magnitud de aceleración y giro de la muñeca izquierda. No recibe opinión, Borg, lactato, ID, índice original, tiempo transcurrido, tarea ni pulso. Es Random Forest de 150 árboles, profundidad máxima 5, mínimo 10 ventanas por hoja, pesos equilibrados y semilla 42.

Se realizan 16 rondas reservando **una persona completa con ambas visitas**. En cada ronda se entrena solamente con `ST` de las otras 15 personas. Se evalúa `ST` de la persona reservada como prueba principal y su `DT` como comprobación secundaria de transferencia de tarea. No se entrena con `DT` ni se eligen parámetros con sus resultados. La referencia constante usa la condición más frecuente del entrenamiento, sobre exactamente las mismas ventanas. Un control separado recibe exclusivamente cantidad de muestras e intervalo mediano, para comprobar una asociación con el muestreo como la hallada en UCD.

## Resultados del modelo fijo

| Evaluación en personas reservadas | Ventanas | Acierto | Referencia constante | Precisión/PPV de `fatigue` | Sensibilidad de `fatigue` |
| --- | ---: | ---: | ---: | ---: | ---: |
| Caminata simple `ST`, prueba principal | 1.917 | 59,21 % | 50,08 % | 60,02 % | 54,75 % |
| Caminata con tarea mental `DT`, transferencia secundaria | 1.912 | 58,68 % | 49,84 % | 59,00 % | 57,77 % |

El control de muestreo obtiene **50 % de exactitud equilibrada** en ambas tareas; predice siempre `fatigue`. No se observó la capacidad de discriminación por muestreo encontrada en UCD, aunque este control no descarta todos los factores de confusión.

En `ST`, la matriz de confusión es `[[611, 349], [433, 524]]`, filas reales `control`/`fatigue` y columnas predichas en el mismo orden. Se omiten **433 de 957 ventanas posteriores al protocolo (45,25 %)** y hay 349 falsos positivos entre 960 ventanas de control. En `DT`, la matriz es `[[568, 385], [405, 554]]`. No se convierten estos recuentos en episodios ni avisos por hora, porque las ventanas consecutivas están correlacionadas y no se definió una regla de alertas.

Al remuestrear las 16 personas completas 10.000 veces, el intervalo percentil exploratorio del 95 % para acierto `ST` es **53,26–65,38 %**, para PPV **53,64–68,73 %** y para sensibilidad **35,83–73,04 %**. La media por persona de exactitud equilibrada es 59,23 %, con intervalo 53,28–65,38 %. La precisión estadística depende de **16 personas**, no de 1.917 observaciones independientes de fatiga. Los intervalos usan predicciones de prueba fijas y no incluyen toda la incertidumbre de selección de fuente, entrenamiento o transferencia de entorno.

[Predicciones, referencias, exclusiones y versiones](duo-wrist-results.json). Reproducción: `python training/python/download_duo_wrist.py` y después `python training/python/evaluate_duo_wrist.py`, con NumPy, pandas y scikit-learn. Los otros módulos importados están en `training/python/`.

## Seguimiento exploratorio con selección anidada

Después de conocer el resultado del modelo fijo, se realizó un seguimiento con **26 características**: las 14 anteriores y seis descriptores de ritmo para cada magnitud. Son frecuencia dominante entre 0,5–4 Hz, proporción de potencia del pico, proporción de potencia en esa banda respecto de 0,5–10 Hz, entropía espectral en 0,5–10 Hz, pico de autocorrelación y su retardo entre 0,3–1,5 s. No son biomarcadores clínicos de fatiga validados: describen periodicidad y distribución de energía del movimiento.

Se fijaron cinco candidatos antes de leer sus resultados: constante, regresión logística C=1, SVM RBF C=1 o C=10 y el Random Forest anterior. En cada una de las 16 rondas exteriores se eligió el candidato por exactitud equilibrada en **tres grupos interiores de personas** de `ST`. Toda normalización se ajustó dentro del entrenamiento de cada ronda mediante pipelines. La persona reservada, sus dos visitas y todos sus datos quedaron fuera de la selección y del ajuste; `DT` no intervino en ninguno. Se eligió SVM C=1 en 12 rondas, Random Forest en 3 y regresión logística en 1. No se escogió un único modelo mirando cuál acertó más en las personas de prueba.

| Evaluación anidada | Acierto | Referencia constante | Precisión/PPV de `fatigue` | Sensibilidad de `fatigue` |
| --- | ---: | ---: | ---: | ---: |
| `ST`, 16 personas y 1.917 ventanas | 60,35 % | 50,08 % | 60,74 % | 58,20 % |
| `DT`, mismas 16 personas y 1.912 ventanas | 59,62 % | 49,84 % | 59,40 % | 61,63 % |

La matriz `ST` es `[[600, 360], [400, 557]]`: **400 de 957 ventanas posteriores al agotamiento omitidas (41,80 %)** y 360 falsos positivos entre 960 controles (37,50 %). La matriz `DT` es `[[549, 404], [368, 591]]`. En `ST`, los intervalos percentiles exploratorios del 95 % agrupados por persona son **53,39–67,01 %** para acierto, **53,47–70,07 %** para PPV y **41,34–74,03 %** para sensibilidad. El promedio por persona de exactitud equilibrada es 60,36 %, intervalo 53,44–66,98 %.

La mejora de acierto frente al modelo fijo es de aproximadamente **1,15 puntos porcentuales**; no se hizo una prueba que establezca superioridad estadística entre estos dos métodos. Ambos conservan bastantes falsos positivos y omisiones. Esta selección anidada evita elegir modelos con la persona de prueba, pero el diseño de características se hizo después de observar el primer experimento: **sigue siendo un seguimiento exploratorio sobre una fuente conocida**, no una validación externa nueva.

[Resultados, selecciones interiores y predicciones](duo-wrist-nested-results.json), [script reproducible](../../training/python/evaluate_duo_wrist_nested.py). Reproducción posterior al benchmark fijo: `python training/python/evaluate_duo_wrist_nested.py`; utiliza exclusivamente los archivos locales ya verificados y registra el SHA-256 del primer informe.

**Redacción defendible para la tesis:** “En DUO-GAIT, un seguimiento exploratorio con selección anidada por persona obtuvo 60,35 % de acierto y 60,74 % de valor predictivo positivo al distinguir condiciones de caminata simple anteriores y posteriores a un protocolo de agotamiento, usando aceleración y giro de muñeca izquierda. Se evaluaron 1.917 ventanas de 16 personas reservadas completas, con intervalo exploratorio de acierto 53,39–67,01 %. El resultado describe ese protocolo interior y no valida detección de fatiga durante trekking.”

## Alcance para la tesis y la app

Esta fuente permite una **prueba de concepto de discriminación de condiciones antes/después de agotamiento al caminar**, con mediciones reales de una muñeca y referencias de un estudio publicado, sin pedir opiniones al usuario durante la inferencia. El modelo fijo obtiene una ventaja moderada sobre la referencia, con muchos falsos positivos y omisiones. Ese resultado no sostiene recomendaciones fiables de fatiga durante una excursión.

Falta demostrar transferencia de pasillo a sendero, de agotamiento por levantamientos con carga a fatiga de marcha prolongada y de Physilog5 a un reloj/celular real. Tampoco se evaluó el pulso: el Polar H10 registra la visita completa, pero no se verificó una alineación temporal precisa con los segmentos IMU. No se desplazan ni concatenan esos registros para fabricar coincidencias.

El metadato Zenodo inspeccionado declara acceso abierto, pero **no incluye un campo de licencia para los datos**. La licencia CC BY 4.0 del artículo y MIT del código no establecen por sí solas la licencia de redistribución de los archivos. No se publican los datos descargados ni se aprueba su uso productivo. No se integró ningún modelo ni se publicaron cambios de MiSendero.
