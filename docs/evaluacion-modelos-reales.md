# Comparación reproducible de los modelos con datos públicos reales

El proyecto evalúa cuatro tareas distintas: Borg observado en GeoFatigue, resultado AMS del estudio nocturno, dificultad de tramos OSM y dificultad publicada por APN. Cada tarea conserva sus etiquetas originales. Sus métricas no son intercambiables ni validan las categorías de fatiga/riesgo de la app durante trekking.

La [evaluación de fatiga orientada a trekking](fatigue-trekking-evaluation-2026-10-22/README.md) añade error ordinal, referencia e incertidumbre por participante sobre el test GeoFatigue ya reservado, y documenta qué datos harían falta para una prueba externa en senderos.

## Actualizar la evaluación sin volver a entrenar

Desde la raíz del proyecto:

```powershell
npm.cmd run evaluate:ai
npm.cmd run validate:ai-data
```

El primer comando verifica las fuentes originales, los CSV, las particiones y las predicciones guardadas. Después añade comparaciones a los informes de `training/data/public/<modelo>/metrics.json` y a sus copias en `ai/models/`. No ajusta un modelo, no modifica etiquetas ni características, no cambia el test y no genera observaciones. Conserva `trained_at`; registra una fecha separada de actualización de la evaluación.

El nuevo bloque `evaluation_details` también se genera en los futuros entrenamientos. El validador recalcula ese bloque a partir de las fuentes y predicciones, por lo que rechaza comparaciones modificadas manualmente.

## Qué comparar

- **Accuracy:** proporción de coincidencias exactas con la etiqueta nativa.
- **F1 macro del modelo y de referencia:** ambos se calculan con el mismo vocabulario de etiquetas, incluidas las clases sin observaciones en test. La referencia predice siempre la clase más frecuente en entrenamiento; el test no elige esa clase ni resuelve sus empates.
- **Accuracy balanceada:** promedio del recall de las clases realmente observadas en test. Reduce el efecto del desbalance, pero no mide el desempeño de clases ausentes. Por eso se muestran por separado la cobertura de clases y las ausencias en entrenamiento/test.
- **Grupos independientes:** participantes, regiones o parques, según la fuente. Varias ventanas de una misma persona no equivalen a varias personas. Un test con un solo parque no permite evaluar variación entre parques de test.

La documentación de [métricas de scikit-learn](https://scikit-learn.org/stable/modules/model_evaluation.html) explica las referencias simples y la interpretación de métricas para clases desbalanceadas; [accuracy balanceada](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.balanced_accuracy_score.html) se define como el promedio del recall por clase observada.

Una diferencia favorable sobre la referencia es descriptiva. No es una prueba de significación, no garantiza generalización y no habilita automáticamente el uso en campo. Tampoco un F1 bajo demuestra por sí solo que la causa sea underfitting: pueden intervenir el tamaño y la distribución de las muestras, las variables disponibles o el cambio entre grupos.

## Resultados ampliados del 21/10/2026

Se recalcularon comparaciones sobre las predicciones de los entrenamientos del 15/10/2026, sin nuevos ajustes ni cambios de observaciones:

| Tarea | F1 macro modelo | F1 macro referencia | Accuracy balanceada | Clases presentes en test | Grupos de test |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fatiga — Borg | 0,1904 | 0,0446 | 24,99 % | 9/9 | 12 |
| AMS nocturno | 0,6190 | 0,3333 | 62,50 % | 2/2 | 8 |
| Tramos OSM | 0,2760 | 0,1614 | 50,00 % | 3/6 | 2 |
| Recorridos APN | 0,5417 | 0,0938 | 61,11 % | 3/4 | 1 |

Fatiga supera a la referencia en F1 macro, aunque su accuracy sigue por debajo de ella; las métricas responden preguntas distintas. En OSM, la accuracy convencional de 95,92 % convive con 50 % de accuracy balanceada y tres clases sin observaciones en test. APN reserva un solo parque y no evalúa la clase media-alta. Las tablas describen estas observaciones; no prueban rendimiento para clases, grupos o usos que no fueron evaluados.

Los JSON conservan las matrices de confusión, los soportes por clase y las predicciones necesarias para verificar los cálculos. La referencia de APN conserva el desempate original de entrenamiento; no se eligió la clase con mejor resultado mirando el test.

## Próximos datos que aportarían evidencia

Para fatiga, hacen falta observaciones independientes de las clases poco representadas y validación de la tarea final. Para AMS, deben distinguirse las medias nocturnas de las lecturas durante una caminata; la etiqueta del estudio no se transfiere automáticamente a alertas instantáneas. Para OSM/APN, ampliar la cobertura de clases y regiones/parques permite evaluar mejor la generalización geográfica. Toda incorporación debe conservar una etiqueta publicada u observada independientemente de los predictores, fuente y procedencia verificables.

La comparación se muestra en las herramientas de administración del perfil. Los modelos siguen identificados como investigación mientras no exista una validación específica para el uso propuesto. El recomendador de senderos usa reglas sobre atributos del catálogo, sin valoraciones humanas ni etiquetas de relevancia. Estas reglas no constituyen un modelo aprendido o una validación científica de adecuación o seguridad.

## Detección de caídas (experimental, 2026-10-22)

Modelo independiente de los de dificultad, fatiga y mal agudo de montaña, entrenado con UniMiB SHAR (30 participantes, caídas experimentales, teléfono en el bolsillo). Evaluación por participante, resultados, limitaciones y estado de cada capacidad (entrenado / evaluado / integrado / monitoreo continuo **no** validado): `docs/fall-detection-2026-10-22/README.md`.
