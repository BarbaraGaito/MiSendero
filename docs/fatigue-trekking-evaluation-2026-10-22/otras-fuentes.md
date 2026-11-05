# Otras fuentes revisadas el 22 de octubre de 2026

## WAUC: esfuerzo durante actividad física con carga mental

[Sitio de los autores](https://musaelab.ca/wauc-dataset/), [documentación oficial](https://github.com/MuSAELab/WAUC-A-Multi-Modal-Database-for-Mental-Workload-Assessment-Under-Physical-Activity), [artículo](https://doi.org/10.3389/fnins.2020.549524).

El estudio reúne 48 participantes; la tabla demográfica descargada distingue 22 en cinta y 26 en bicicleta. La tabla original `subjective_ratings_with_labels.csv` descargada tiene 282 filas de 47 personas, seis sesiones por persona y dos columnas de esfuerzo (`Perceived Exertion (1)` y `(2)`) con valores observados de 6 a 19. La documentación informa que la persona 1028 no tiene respuestas. El artículo diferencia respuestas antes y después del descanso; antes de evaluar hay que confirmar la correspondencia exacta entre esas dos columnas y los segmentos de señal.

Incluye ECG de Bioharness 3, PPG y acelerómetro Empatica E4 y otras modalidades. Podría servir para una prueba de esfuerzo percibido en cinta separando personas; la actividad mental simultánea puede afectar fisiología y respuestas, y no es una prueba exterior ni de trekking. No se debe interpretar la clasificación de carga mental del artículo como precisión de fatiga física.

Acceso comprobado: se descargaron etiquetas y demografía usando los enlaces públicos originales con User-Agent de navegador y Referer del sitio. Las etiquetas tienen 10.462 bytes y SHA-256 `e828f68f517f9f9bb756e29e3984868619726fc42a8c10815aa41a0378b06f7c`. El enlace `raw.rar` devolvió 403, tanto con como sin HTTP Range; no se descargaron ni verificaron las señales completas. La copia de Kaggle tampoco pudo inventariarse desde esta sesión. La nueva versión ofrece una muestra individual mediante Google Drive, pero su contenido no se ha descargado. Falta confirmar los términos específicos de reutilización del archivo, además de la cita solicitada por los autores.

## Columbia: Data After Cardio

[Repositorio oficial](https://github.com/Columbia-ICSL/data_after_cardio), [artículo SenSys 2025](https://doi.org/10.1145/3715014.3722065).

La tabla pública `general_information.csv` se descargó y contiene 731 filas, 728 nombres únicos de clip y 250 sesiones de ejercicio de 59 personas. Los clips de la misma sesión de ejercicio comparten respuesta, por lo que no son observaciones independientes de fatiga. Las 250 sesiones se distribuyen en las etiquetas nativas 1:28, 2:82, 3:75, 4:61 y 5:4; no se encontraron respuestas contradictorias entre clips de la misma sesión. Hay tres nombres de clip duplicados y nueve filas sin archivo de reloj del mismo nombre en el inventario actual. El inventario tiene 726 archivos de reloj.

Se verificó un CSV real de reloj con columnas `timestamp,heart rate,distance,activity type,time`. La tabla de respuestas tiene SHA-256 `2f57d1d099bf94cff30bfc701818036b506a1a54ec06eff82a0c20bd58757bf3`; commit/inventario inspeccionado: `6467a7d387d78882643a281a2e50aa4d219e7368`. El repositorio declara MIT. El libro demográfico y las señales no se guardaron en el proyecto.

Su límite principal es temporal: las señales publicadas se sincronizan con habla/respiración de recuperación **después** de correr y de declarar el esfuerzo. No es válido usar pulso posterior a la respuesta para afirmar una predicción previa a ella durante el ejercicio. Serviría para investigar esfuerzo residual durante recuperación; el estudio no demuestra transferencia a senderismo. El README enumera seis descripciones de esfuerzo mientras la tabla inspeccionada usa cinco valores; documentar esa diferencia antes de reutilizar clases.

## Otros archivos inspeccionados y excluidos por ahora

- [Fourth fatigue diagnosis states, Figshare](https://figshare.com/projects/Fourth_fatigue_diagnosis_states/119580): el archivo público `database.xlsx` se descargó en memoria y se verificó con el MD5 del repositorio (`ff3f25618b96f155a1d9f551e2dbf1dd`). Tiene 2.919 filas de datos y 45 columnas, con características de movimiento, EMG y `labels`, sin columna de pulso ni ID explícito de participante. SHA-256 `cff4474d09c065d22922ca076a84f8e9cbf45ea1610f45e61d4c031416b72f03`; licencia CC BY 4.0. No permite todavía una prueba independiente por persona y no corresponde a las entradas de pulso del modelo actual. No se atribuye a MiSendero la exactitud publicada por sus autores.
- [Alfaro, caminata con carga y cinta](https://zenodo.org/records/23208045): la API oficial confirma título y sensores relevantes, pero declara acceso `embargoed` hasta **7 de abril de 2027** y no entrega archivos. Un catálogo secundario lo presenta como abierto; para esta decisión prevalece el registro primario. No es utilizable ahora.
- [CORA, caminatas exteriores en EPOC](https://doi.org/10.34810/DATA219): la publicación describe pulso y consumo de oxígeno durante caminatas, pero no se verificó una etiqueta sincronizada de fatiga ni se pudo recuperar el inventario del repositorio. Además, la población clínica exige una evaluación propia de transferencia. No se admite como prueba de fatiga en senderistas sanos.
- [Fatiga de trabajadores que escalan postes](https://doi.org/10.3389/fpubh.2024.1462675): el artículo ofrece datos brutos mediante solicitud al autor, sin descarga pública identificada, y su modelo usa pruebas no disponibles en el reloj. No es una alternativa directamente utilizable.

## Decisión

Entre estas fuentes nuevas, WAUC es la candidata más cercana para evaluar pulso y esfuerzo durante locomoción, pendiente de recuperar las señales y revisar tiempos de respuesta. Columbia es la alternativa de acceso más comprobado, pero corresponde a recuperación posterior al ejercicio. Ninguna de las fuentes revisadas añade una validación de detección de fatiga durante trekking. No se generaron etiquetas ni se entrenó un modelo con tareas incompatibles para obtener un porcentaje.
