# Auditoría de métricas de IA de MiSendero — 12/11/2026

La prioridad es mejorar la validación antes de seguir probando arquitecturas. **Fatiga con Borg previa** es el candidato más útil para investigar: reduce el error en puntos, pero no mejora la identificación de los niveles altos respecto de repetir el autorreporte anterior. **La mejora más directa para la app** está en el catálogo: faltan rutas compatibles con ciertos perfiles y duración total confirmada. **AMS** queda como investigación; la prueba disponible es demasiado pequeña y estudia otro escenario.

## Qué está en uso

El [panel de métricas](../ai/modelMetrics.ts) muestra cinco evaluaciones de investigación. Los cinco archivos del panel coinciden con sus artefactos originales y declaran `deployment_approved: false`. El [motor móvil](../ai/inferenceEngine.ts) devuelve `sin_datos` para predicciones de fatiga y riesgo; el [análisis del reloj](../services/wearableMetrics.ts) usa reglas sobre lecturas recientes. El [recomendador](../backend/src/ai/assistant.ts) ordena el catálogo con reglas y devuelve `ranking.method: "catalog"`. El [entrenamiento histórico de ranking](trail-ranking-2026-10-17/policy-v4-training-status.json) registró cero etiquetas y ninguna métrica de relevancia; el ranking entrenable está [desconectado de la API](trail-recommendation.md).

## Resultados recalculados

Se verificaron los hashes de las predicciones y su procedencia, la separación de grupos, las cinco copias del panel y las matrices de confusión. Accuracy es el porcentaje de aciertos exactos. F1 macro pondera igual cada clase del vocabulario declarado; accuracy balanceada promedia el recall de las clases observadas en test. Conviene leer ambas con el número de casos por clase y el número de grupos. Los resultados de tareas distintas tienen etiquetas y poblaciones distintas.

| Modelo | Aciertos exactos | F1 macro | Accuracy balanceada | Grupos reservados en test | Referencia simple: accuracy / F1 |
| --- | ---: | ---: | ---: | --- | --- |
| Fatiga, pulso y tiempo | 57/179 (31,84 %) | 0,199 | 20,89 % | 12 personas | Borg 3: 25,14 % / 0,045 |
| Fatiga, Borg previa y contexto | 108/179 (60,34 %) | 0,319 | 38,71 % | Las mismas 12 personas | Repetir Borg previa: 43,58 % / 0,335 |
| Mal agudo de montaña (AMS), estudio nocturno | 5/8 (62,50 %) | 0,619 | 62,50 % | 8 personas | Siempre AMS−: 50,00 % / 0,333 |
| Dificultad de tramos OSM + IGN | 47/49 (95,92 %) | 0,330 | 66,67 % | 2 regiones; 3 de 6 clases | Siempre `hiking`: 93,88 % / 0,161 |
| Dificultad de recorridos APN | 11/13 (84,62 %) | 0,542 | 72,22 % | 1 parque; 3 de 4 clases | Empate en ajuste: `media`, 23,08 % / 0,094; `baja`, 61,54 % / 0,190 |

El F1 publicado de fatiga con pulso usa 9 etiquetas; el de fatiga con Borg previa usa 11, incluidas Borg 0 y 10, ausentes como objetivos. La comparación siguiente aplica las mismas 11 etiquetas y los mismos 179 casos. En APN, `media` fue el desempate original; `baja` se muestra para que la comparación no dependa de ese desempate. Ambas referencias se determinan con etiquetas de entrenamiento.

### Fatiga: hay una mejora útil en el tamaño del error

| En los mismos 179 casos | Acierto exacto | F1 macro, 11 clases | Error absoluto medio | A ≤1 punto | Detectó Borg ≥7 cuando estaba presente |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bosque de pulso y tiempo | 31,84 % | 0,163 | 1,30 puntos | 110/179 (61,5 %) | 8/19 |
| Repetir Borg previa | 43,58 % | **0,335** | 0,99 puntos | 141/179 (78,8 %) | **13/19** |
| MLP con Borg previa y contexto | **60,34 %** | 0,319 | **0,42 puntos** | **175/179 (97,8 %)** | **13/19** |

La MLP ganó **30 aciertos exactos netos** frente a repetir Borg previa. El intervalo descriptivo del 95 % por remuestreo pareado de personas fue **+10,6 a +22,8 puntos porcentuales** en accuracy; para F1 macro, **−0,040 a +0,054**. El F1 observado cae 0,016 y el intervalo incluye mejoras y deterioros. En el corte exploratorio Borg ≥7, la MLP omitió 6 de 19 casos, igual en cantidad que la referencia; ambas tuvieron cero positivos entre las otras 160 observaciones. Borg ≥7 es un corte descriptivo de la escala, sin significado de alerta en esta auditoría.

El bosque de pulso y tiempo cae de **F1 0,799 en ajuste a 0,199 en test** y obtuvo 0,210 en validación cruzada por persona. Eso es compatible con sobreajuste y con información insuficiente para distinguir intensidades usando esas dos entradas. La MLP usa una Borg real de la misma sesión, de 1 a 15 minutos antes, y datos de la tarea; no usa pulso. Repetir la Borg previa nunca sobreestimó la respuesta en estas 179 filas, lo que hace especialmente importante incluir descensos tras pausas y recuperación en la próxima evaluación. [GeoFatigue](https://ubisensing.ai/projects/geofatigue/) midió tareas con carga en exteriores bajo un protocolo fijo; el desempeño en caminatas aún no está medido. El resultado retenido sigue siendo **108/179**: el [objetivo histórico de 80 %](fatigue-80-2026-10-25/README.md) sigue pendiente. El control CatBoost de 63,80 % en validación cruzada logró solo 102/179 en el mismo test histórico.

### Dificultad y AMS: los errores que importan quedan detrás del promedio

- **OSM + IGN:** `hiking` representa 46 de 49 casos. El modelo agrega un acierto a esa referencia y clasifica como `hiking` los dos tramos `mountain_hiking`. No hay tramos de las tres clases alpinas en test; el F1 medio de validación por región es 0,148. Falta evidencia justamente en las clases donde subestimar la dificultad importa más.
- **APN:** acierta las 8 rutas `baja`, 2 de 3 `media` y 1 de 2 `alta`; una `alta` se clasificó como `media`. No hay casos `media-alta` y todo el test es de Tierra del Fuego. El F1 medio en los cuatro folds de validación es 0,269. Para fichas con dificultad oficial publicada, ese dato es la referencia del producto. El candidato tendría un uso verificable como apoyo para revisar fichas sin dificultad documentada, una vez validado en parques nuevos.
- **AMS:** detecta 3 de 4 positivos y reconoce 2 de 4 negativos: un positivo omitido y dos falsos positivos. Cada persona cambia la accuracy en 12,5 puntos. El candidato posterior subió en validación cruzada, pero en el mismo test bajó de 5/8 a 4/8. La [fuente original](https://zenodo.org/records/11505046) estudia hipoxia controlada nocturna equivalente a 4.200 m; sus promedios de pulso y SpO₂ no representan las lecturas instantáneas de una caminata.

### Recomendador actual: cobertura no es coincidencia

Se ejecutó la implementación vigente sobre las 51 fichas del repositorio y 38 ubicaciones, variando un paisaje por vez, duración, dificultad y experiencia. Las **19.152** combinaciones dieron una ruta dentro del destino. Solo **1.433 (7,5 %)** cumplieron todas las preferencias evaluadas; **17.719 (92,5 %)** necesitaron una alternativa. La duración quedó fuera de rango o sin alcance confirmado en **11.872** combinaciones (62,0 %); 9 fichas tienen el tiempo total sin confirmar. Los motivos de discrepancia pueden superponerse.

Para principiantes, en **3.528 de 6.384** combinaciones (55,3 %) la ruta supera el nivel previsto por las reglas: corresponde a 21 de las 38 ubicaciones sin opción compatible con ese perfil. El script lista esas ubicaciones tal como aparecen en el catálogo, incluso cuando varias corresponden a un mismo parque. Esto permite priorizar qué fichas incorporar y cuándo mostrar que no hay una opción para el perfil. La grilla da el mismo peso a cada combinación y no representa tráfico, satisfacción ni aptitud en campo. Se usaron fichas locales, sin consultar producción.

## Qué mejorar, en orden

1. **Recomendaciones: cubrir primero los huecos del catálogo.** Priorizar las ubicaciones sin rutas para principiantes y confirmar si los tiempos incluyen el regreso. Revisar que, cuando solo haya rutas por encima del nivel, la app las muestre como alternativas claramente separadas. Medir por destino y experiencia el porcentaje de coincidencias, el porcentaje sin opción compatible y la cobertura de duración total. Si se evalúa relevancia con personas en el futuro, comparar las reglas vigentes con cualquier alternativa en consultas nuevas y usar acierto de relevancia en la primera sugerencia; usar NDCG@3 si se muestran varias opciones y existen valoraciones para ordenarlas.
2. **Fatiga: congelar la MLP y las referencias antes de probarlas con datos nuevos.** Buscar mediciones públicas reales con autorreportes Borg comparables, personas y senderos distintos, pausas, cambios de terreno y observaciones de los extremos de la escala. Medir por separado qué proporción de ventanas tiene Borg previa vigente y entradas compatibles; incluir sesiones sin historial y faltantes de reloj en la evaluación de cobertura. Comparar con última Borg, pulso y tiempo, y una referencia simple de cambio ajustada solo en entrenamiento. Fijar antes del test las tolerancias de error, el recall en niveles altos y la cobertura mínima; reportar acierto exacto, MAE, F1 macro, errores hacia abajo y sus intervalos por persona. Mantener la meta del 80 % exacto como indicador de investigación y conservar el denominador histórico.
3. **OSM y APN: conseguir más geografía y etiquetas difíciles.** Mantener separados tramos y recorridos completos. Para OSM, buscar clases alpinas y añadir variables verificables como superficie, exposición y pendiente; para APN, incorporar parques nuevos con categorías `alta` y `media-alta`. Separar por región/parque y familias de rutas que comparten tramos. Comparar con las referencias simples y reportar recall de las categorías exigentes y tasa de subestimación, con soporte explícito por clase.
4. **AMS: mantener deshabilitada la inferencia y separar el estudio del uso en campo.** Solo retomar si hay una cohorte externa con desenlace comparable, un momento de predicción definido y entradas disponibles en ese mismo momento. En una evaluación futura, fijar el umbral en validación y reportar sensibilidad, especificidad, falsas alarmas por salida y calibración con intervalos. Ocho personas no permiten fijar un umbral fiable para la app.
5. **Panel y selección: hacer visibles las condiciones de cada cifra.** Junto a accuracy mostrar aciertos/total, cantidad de grupos, referencia, clases ausentes y recall de las clases clave. Para fatiga, alinear el vocabulario en la comparación y etiquetar explícitamente el requisito de Borg previa. Los candidatos de octubre se eligieron por validación cruzada, pero se consultó el test publicado para decidir reemplazos y se reutilizó en varios experimentos de fatiga. Congelar el próximo test externo, decidir con validación por grupos y predefinir los criterios. Si se retoma el ajuste de hiperparámetros con pocos grupos, usar [validación cruzada anidada](https://pmc.ncbi.nlm.nih.gov/articles/PMC1397873/) para separar selección de estimación interna; reservar el test externo para la evaluación final.

## Reproducción

```powershell
.\.venv-ai\Scripts\python.exe training/python/audit_model_metrics.py
npm.cmd run validate:ai-data
npm.cmd --prefix backend run build
node backend/scripts/auditCatalogRecommendationFit.js
```

El script de métricas lee predicciones congeladas, no entrena modelos ni carga archivos pickle. El remuestreo usa 5.000 réplicas por persona, semilla 42, sobre un test histórico; los intervalos son descriptivos. Se verificaron también 52 pruebas del backend de recomendaciones, 26 de inferencia y pantallas móviles y los 12 escenarios documentados del catálogo. La auditoría no cambia modelos ni reglas de la app.
