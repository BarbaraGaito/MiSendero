# Fuentes públicas adicionales para MiSendero

Investigación inicial: 14/10/2026. Objetivo: complementar modelos conservando mediciones públicas y etiquetas independientes. Desde el 15/10/2026 no se admiten datos sintéticos, tampoco como augmentation de entrenamiento. Tras la autorización posterior se incorporaron APN, IGN y la ampliación OSM argentina: ver [implementación, fuentes y resultados](datasets-argentina-2026-10-14.md).

## Relación con el PFI

Se revisaron las secciones 2.1.5 y 2.1.6 del documento proporcionado (páginas impresas 11–13; páginas PDF 13–15). El texto propone señales inerciales/cardíacas para fatiga; HR, SpO2, HRV y contexto para riesgo; y OSM más relieve para rutas. La mención del PDF a datos sintéticos no sustituye el requisito posterior del usuario, que no admite datos sintéticos.

El objetivo práctico no es acumular filas: hacen falta mediciones relevantes, etiquetas de la misma tarea y variables que la app pueda medir en condiciones equivalentes. Una publicación abierta no implica que sus registros individuales sean abiertos.

## Prioridad para rutas

| Fuente primaria | Qué aporta realmente | ¿Etiqueta independiente? | Aplicación y limitación |
| --- | --- | --- | --- |
| [Parques Nacionales: senderos de Tierra del Fuego](https://www.argentina.gob.ar/parquesnacionales/patagonia-austral/senderos-del-parque-nacional-tierra-del-fuego) | Fichas oficiales con dificultad, distancia, duración y desnivel | Sí: dificultad publicada por APN | Alta prioridad para Argentina. Crear un dataset de rutas completas con revisión manual de cada ficha, unidad, sentido del recorrido, fecha y coincidencia geométrica. No es un CSV masivo listo para entrenar. |
| [IGN: MDE-Ar](https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/Introduccion) y [modalidades de descarga](https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/faq) | Elevación argentina; productos de 30 m y otros de cobertura específica | No | Alta prioridad como predictor: perfil, desnivel y pendientes derivados del relieve. Las descargas y permisos varían según producto; confirmar licencia y cobertura de cada hoja. No generar etiquetas a partir de esas pendientes. |
| [Copernicus DEM GLO-30](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) | Modelo de superficie global de 30 m | No | Alternativa de cobertura amplia, bajo licencia propia gratuita con atribución. Puede incluir vegetación/infraestructura. Requiere revisar acceso/registro y resolución efectiva; no representa obstáculos pequeños. |
| [swissTLM3D hiking trails](https://opendata.swiss/en/dataset/swisstlm3d-wanderwege) + [swissALTI3D](https://www.swisstopo.admin.ch/en/height-model-swissalti3d) | Red oficial suiza y relieve de alta resolución | Categorías oficiales de sendero, no equivalencia automática a sac_scale T1–T6 | Útil para un modelo o validación geográfica separado. Suiza no valida rendimiento argentino. Descargar datos OGD originales, no mapas raster ni muestras limitadas a prueba. [Condiciones OGD](https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices): atribución obligatoria. |

Ejemplos comprobados de APN: Castorera figura como baja, Hito XXIV como media y Cerro Guanaco como alta. Son categorías publicadas, no calculadas por nosotros. No se asume que la dificultad global de APN sea igual a la dificultad técnica sac_scale de un tramo. Mantener tareas/etiquetas separadas hasta documentar equivalencias.

La recomendación es enriquecer las rutas argentinas con relieve y agregar fichas APN como una tarea de clasificación de rutas completas. No afirmar que un DEM por sí solo agrega ground truth ni que mejorará una métrica sin evaluarlo.

## Prioridad para fatiga

| Fuente primaria | Mediciones y etiqueta | Tamaño / acceso | Utilidad y condición de admisión |
| --- | --- | --- | --- |
| [Twente: Fatigue running in- and out of the lab](https://research.utwente.nl/en/datasets/fatigue-running-in-and-out-of-the-lab-data-underlying-the-publica/) / [DOI](https://doi.org/10.4121/ec2b2b53-2cba-49b4-a27d-7aa227e03120) | IMU, pulso Garmin a 1 Hz y agotamiento reportado 1–10 cada 90 s | 16 participantes; TCX, MVNX y XLSX; CC BY-NC-SA según ficha | Primera candidata para HR + movimiento + etiqueta temporal observada. Es carrera, no caminata: evaluar por dominio/participante. La ficha se pudo verificar; la descarga 4TU devolvió 403 en este entorno, por lo que todavía no se auditó toda la sincronización. |
| [WHAMAP](https://data.mendeley.com/datasets/8zt9g9g64c/1) | Cinco IMU de miembros inferiores y sensores de smartphone, 50 Hz; fatiga anotada por Borg en caminar, subir y hacer sentadillas | 10 participantes; CSV; CC BY 4.0 | Muy pertinente a la propuesta IMU del PFI. La ficha declara niveles 0–4: hay que auditar cómo se vinculan con respuestas Borg originales. No anuncia HR/SpO2 y no se pueden sustituir cinco IMU de piernas por un reloj sin validarlo. |
| [Northwestern: Wearable Network for Multi-Level Physical Fatigue](https://zenodo.org/records/12788571) | ECG/HR, HRV, temperatura e IMU; respuestas originales de fatiga | 43 sujetos; archivo de 12,7 GB; metadata del dataset CC BY 4.0 | Fuerte complemento fisiológico. El README confirma respuestas en USER FORM RESPONSE.xlsx. El [artículo](https://rogersgroup.northwestern.edu/files/2024/nexusworker.pdf), apartado Data analysis, interpola etiquetas entre respuestas: excluir esas etiquetas procesadas y usar únicamente las respuestas realmente observadas, con ventanas alineadas. Es trabajo industrial. |
| [De Luca / Luo / Clay: wearable + daily fatigue](https://zenodo.org/records/4266157) | Señales de pulsera cada minuto y cuestionarios diarios originales | 28 reclutados; 27 con señales/cuestionarios emparejados, 405 días; ~84,9 MB; metadata CC BY 4.0 | Útil para otra tarea: fatiga diaria en vida cotidiana. No copiar una etiqueta diaria a cada ventana de 5–10 segundos como si hubiera sido observada allí. Se verificaron cabeceras de un archivo de señales y del archivo de respuestas. |

No mezclar Borg 6–20, Borg modificado 0–10, agotamiento 1–10 y categorías 0–4 solo por tener nombres parecidos. Conservar escala/protocolo y comparar dominios por separado. Para Northwestern se recomienda reconstruir desde raw; no adoptar su pipeline procesado sin revisar qué variables son medidas, estimadas o etiquetas interpoladas.

Antes de agregar fuentes, GeoFatigue ya ofrece modalidades que nuestro baseline no aprovecha: la extracción vigente usa HR/tiempo. Revisar señales y biomarcadores originales disponibles puede aportar más información sin cambiar de población ni inventar columnas. La utilidad predictiva sigue pendiente de prueba.

## Riesgo fisiológico / AMS

Encontré candidatas públicas adicionales, pero ninguna queda declarada aquí lista para incorporarse al modelo de alerta de trekking.

| Fuente primaria | Evidencia pública comprobada | Estado para MiSendero |
| --- | --- | --- |
| [Dryad: Inflammatory gene expression during acute high-altitude exposure](https://datadryad.org/dataset/doi:10.6086/D1XM45) | Estudio de 15 personas con exposición real en altitud, AMS y saturación; publica un CSV fisiológico pequeño y datos de expresión génica. Dryad aplica CC0 como instrumento general de publicación. | Candidata para auditar el CSV fisiológico, no para usar expresión génica en una app. La descarga devolvió 403 aquí: no se verificaron columnas, alineación ni faltantes. No contar 15 personas por cada día como participantes independientes. |
| [Zenodo: estudio Regina Margherita, 4559 m](https://zenodo.org/records/4289128) | 18 hombres, ascenso pasivo y reposo; AMS según definición funcional publicada. Dataset XLSX y metadata CC BY 4.0. | Posible complemento de AMS en altitud real, no de riesgo durante marcha. Dos descargas obtenidas no pasaron integridad ZIP/checksum: fuente anunciada públicamente, archivo no certificado en esta investigación. Verificar primero HR/SpO2 individuales y criterio AMS; no mezclar definiciones distintas. |
| [AMS_biomarker: datos de autores](https://github.com/Monica1227/AMS_biomarker/tree/main/data) | CSV inspeccionados: 152 filas de cuestionarios/síntomas/LLS y 106 filas de marcadores clínicos | Es información real, pero el CSV clínico revisado contiene laboratorio (hormonas, proteínas, etc.), no HR/SpO2 de pulsera. No soluciona directamente el modelo actual y no se verificó licencia explícita de reutilización del repositorio. Filas/muestras no equivalen automáticamente a personas independientes. |

No asignar AMS basándose en SpO2/HR y luego evaluar contra ese AMS inventado. Si una fuente solo aporta etiquetas o biomarcadores no disponibles en la app, no combinarla fila por fila con HR de otra población. Medición y respuesta deben corresponder a la misma persona, momento y protocolo.

## Fuentes útiles para otros componentes, sin etiquetas de fatiga/AMS

- [WildPPG, ETH Zürich](https://siplab.org/projects/WildPPG): 16 participantes, ~216 h de PPG/ECG, acelerometría, temperatura y altitud; incluye caminar y hiking hasta 3571 m. Muy útil para estimación/calidad del pulso y robustez a movimiento. El ground truth es HR por ECG, no fatiga ni AMS. Datos CC BY-NC-SA 4.0 según publicación; código GPL-3.0 es una licencia distinta.
- [SMN: datos meteorológicos horarios](https://www.datos.gob.ar/dataset/smn-datos-meteorologicos-horarios/archivo/smn_2.1): temperatura, presión, viento y humedad observados por estaciones argentinas. Sirven como contexto si se conserva estación, fecha, distancia y diferencia de altitud. No presentar la lectura de una ciudad como si hubiera sido medida sobre el sendero. Confirmar continuidad histórica, versión y licencia del recurso descargado.
- [ESA WorldCover](https://esa-worldcover.org/en/data-access): cobertura de suelo derivada de teledetección; potencial predictor de entorno. Es un producto clasificado, no observación fisiológica ni etiqueta de dificultad. Solo usarlo declarando esa naturaleza derivada.
- [ERA5-Land](https://climate.copernicus.eu/climate-reanalysis): reanálisis basado en modelos y observaciones. Para el criterio estricto de mediciones reales no lo usaría como sustituto de meteorología medida. Podría ser contexto modelado explícitamente separado, si se aceptara ese alcance en otro momento.

## Resultados de la búsqueda que NO son datasets abiertos listos para entrenar

1. **[Wei et al., 2022](https://link.springer.com/article/10.1186/s12859-022-04749-0)**, citado en el PFI: el artículo dice que los datos no son públicos por restricciones éticas/privacidad y solo se entregan bajo solicitud. No recomendarlo como descarga pública disponible.
2. **[Everest Base Camp / Zenodo 20428956](https://zenodo.org/records/20428956)**: publica índices de artefactos, selección de variables y resultados de modelos, y excluye registros crudos por consentimiento/ética. Se inspeccionó el inventario de archivos; no contiene una tabla de entrenamiento individual con predictores y resultado AMS. Sirve para metodología, no para sumar pacientes.
3. **PAMAP2/WESAD/BIDMC**: útiles para actividad, estrés o procesamiento de señales; sus etiquetas no se vuelven fatiga o AMS por cambiarles el nombre.
4. **[Twente IMU 2021](https://research.utwente.nl/en/datasets/dataset-underlying-the-research-on-physical-fatigue-detection-in-/)**: tiene Borg real, pero la ficha muestra CC BY-NC-ND. No es la misma licencia ni el mismo dataset que Twente 2026. No lo priorizaría frente a una alternativa con mejor adecuación de variables/licencia; cualquier restricción concreta debe verificarse sobre el uso pretendido.

## Orden de trabajo propuesto

1. **Rutas argentinas:** inventario de fichas APN, normalización revisada y relieve IGN/Copernicus; reservar parques/redes completos para evaluación. La dificultad sigue siendo la publicada.
2. **Fatiga con HR:** auditar Twente 2026 y Northwestern usando respuestas originales, variables comunes medidas y particiones por persona; comparar por separado con GeoFatigue. No concatenar etiquetas incompatibles ni rellenar sensores faltantes.
3. **Fatiga por movimiento:** auditar WHAMAP para un modelo IMU propio solo si se dispone de sensores/ubicaciones comparables en el producto.
4. **AMS:** comprobar archivos/variables de Dryad y Regina Margherita; mantener resultados nocturnos, de reposo y durante marcha separados. No prometer una mejora ni habilitar alertas sin evidencia de la tarea de campo.

Para todo dataset admitido: fijar versión/URL/checksum/licencia; registrar etiqueta y momento original; filtrar o quitar variables ausentes; conservar grupos independientes; no generar filas sintéticas; sellar el test antes de nuevas decisiones de modelado y publicar métricas y baseline aun si empeoran.

## Nivel de verificación

Se revisó documentación primaria de repositorios, autores y organismos oficiales. Se inspeccionaron muestras pequeñas de archivos de Northwestern, De Luca y AMS_biomarker, e inventarios de Zenodo. No se descargaron los 12,7 GB de Northwestern ni todos los archivos de Twente/WHAMAP. Se registraron las limitaciones de acceso/integridad en lugar de declarar esas fuentes auditadas. En la ejecución posterior se descargaron y verificaron 11 teselas IGN y fichas APN, y se entrenaron dos tareas argentinas separadas; las otras candidatas siguen pendientes de incorporación.
