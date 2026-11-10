# Optimización de modelos públicos — 25/10/2026

Se ejecutaron 304 configuraciones, 76 por tarea, con 1368 ajustes de validación cruzada por participantes, regiones o parques. Se obtuvieron mejoras descriptivas en tres tareas y se conservó el modelo anterior de AMS porque el candidato empeoró en el test. Todos continúan siendo modelos de investigación con `deployment_approved: false`.

## Resultados sobre las mismas observaciones de test

| Tarea | Accuracy anterior → candidato | F1 macro anterior → candidato | Precisión macro anterior → candidato | Recall macro anterior → candidato | Decisión |
| --- | ---: | ---: | ---: | ---: | --- |
| Fatiga Borg | 24,02 % → **31,84 %** | 0,1904 → **0,1990** | 0,1948 → 0,2045 | 0,2499 → 0,2089 | Publicar candidato |
| AMS nocturno | 62,50 % → 50,00 % | 0,6190 → 0,5000 | 0,6333 → 0,5000 | 0,6250 → 0,5000 | **Conservar anterior** |
| Tramos OSM | 95,92 % → 95,92 % | 0,2760 → **0,3298** | 0,3298 → 0,3264 | 0,2500 → 0,3333 | Publicar candidato |
| Recorridos APN | 76,92 % → **84,62 %** | 0,5417 → 0,5417 | 0,7500 → 0,5417 | 0,4583 → 0,5417 | Publicar candidato |

Las mejoras no abarcan todas las métricas: fatiga pierde recall macro y APN pierde precisión macro mientras gana accuracy y recall. OSM conserva el número total de aciertos y cambia su distribución entre clases. Las métricas completas, cambios pareados e incertidumbre están en [comparison.json](comparison.json). El AMS publicado conserva accuracy 62,50 % y F1 0,6190; el resultado 50 % del candidato está preservado y rechazado como reemplazo.

## Selección dentro de entrenamiento

La búsqueda fija incluye las cuatro configuraciones históricas de Random Forest, otras 24 configuraciones de Random Forest, 24 de Extra Trees, 4 de regresión logística, 8 de SGD con pérdida logística y 12 MLP. Las MLP usan backpropagation con L-BFGS, Adam o SGD; se comparan tamaño de capas y regularización. Los bosques comparan profundidad, tamaño de hojas, número de variables por división y ponderación de clases. La lista y su semilla se fijaron antes de calcular predicciones de test de los candidatos.

| Tarea | F1 CV anterior → seleccionado | Candidato | Parámetros seleccionados |
| --- | ---: | --- | --- |
| Fatiga | 0,1762 → 0,2103 | Random Forest | 150 árboles; profundidad 12; hoja 1; `max_features=0.7`; sin ponderación de clases |
| AMS | 0,6667 → 0,7333 | Extra Trees, rechazado al publicar | 150 árboles; profundidad 3; hoja 1; `max_features=0.7`; sin ponderación de clases |
| OSM | 0,1057 → 0,1482 | Random Forest | 150 árboles; profundidad 3; hoja 1; `max_features=sqrt`; sin ponderación de clases |
| APN | 0,2223 → 0,2694 | Random Forest | 150 árboles; profundidad 8; hoja 4; `max_features=sqrt`; sin ponderación de clases |

Cada candidato recibe los mismos folds de `GroupKFold` originales. El F1 macro usa un vocabulario fijo de etiquetas de entrenamiento entre folds. Los empates conservan el primer candidato de una lista reproducible. Las configuraciones históricas siguen siendo elegibles. SGD, regresión logística y MLP ajustan escalado dentro de cada fold; los pesos se calculan solo con las etiquetas de ese entrenamiento. No se duplican ni generan observaciones. Se desactiva el early stopping que reservaría filas al azar dentro de un participante. Las advertencias de convergencia quedan registradas.

La CV usada para elegir el máximo entre 76 configuraciones tiene sesgo de selección. Sus ganancias no son una evaluación independiente. El [procedimiento de validación por grupos](https://scikit-learn.org/stable/modules/cross_validation.html) y la [documentación de redes MLP](https://scikit-learn.org/stable/modules/neural_networks_supervised.html) describen estas herramientas.

VGG19 y YOLO requieren una tarea de imágenes; estas cuatro tareas reciben variables tabulares. Las MLP y SGD se evaluaron como alternativas para esos predictores. Los ganadores de CV fueron bosques; no se fuerza una red neuronal cuando su validación es inferior.

## Integridad y publicación

Se conservaron exactamente los CSV, etiquetas, características, procedencia, semilla 42, participantes y regiones/parques de las particiones originales. Los SHA-256 previos y las métricas están en [baseline.json](baseline.json); las predicciones previas, en [baseline-predictions](baseline-predictions). Las observaciones de test no se añadieron al entrenamiento ni a la CV. Solo se evaluó la configuración seleccionada de cada tarea, sin probar otras configuraciones contra el test después de conocer sus resultados.

La selección de hiperparámetros y la decisión de reemplazar el artefacto son pasos distintos. Se añadió una regla que conserva el anterior si el candidato pierde accuracy o F1 macro en el test fijo. Esta regla de conservación se incorporó después de observar los resultados de esta corrida; **no fue prerregistrada**. Por tanto, el test sí se utilizó para decidir qué reemplazos publicar. Las comparaciones son descriptivas sobre un test ya publicado, y necesitan una evaluación externa nueva antes de afirmar generalización. El rechazo de AMS no demuestra que sus hiperparámetros anteriores sean universalmente mejores.

[publication.json](publication.json) identifica todos los candidatos y las decisiones. El intento de AMS conserva su dataset, procedencia, selección, modelo, métricas y predicciones en `training/data/public/physio_risk/rejected-candidates/20261025-selected/`. Se restauraron sus artefactos anteriores comprobando los hashes originales. No se buscó un segundo candidato mirando el test. El pipeline futuro aplica esa conservación automáticamente y archiva cada intento rechazado en una carpeta nueva.

El exportador JSON reproduce las probabilidades y decisiones de scikit-learn para bosques, regresión logística, SGD y MLP, incluyendo escalado y semántica float32 de las divisiones de árboles. El entrenamiento comprueba la igualdad antes de escribir predicciones. El validador recalcula métricas de train/test y de todas las predicciones fuera de fold; verifica fuentes originales, particiones, plan de búsqueda y hashes. Los modelos y los candidatos rechazados se auditan sin cargar pickle.

Los hashes del código que ejecutó el ajuste están en `reproducibility` de cada candidato. Sus tres archivos correspondientes se preservan en [evaluated-code](evaluated-code). Los cambios posteriores agregan la conservación automática del anterior; no modifican los algoritmos ni el plan de búsqueda usado en esta corrida.

## Tamaño de muestra e incertidumbre

Fatiga conserva 179 ventanas de 12 participantes en test. Su mejora de accuracy es de 14 aciertos netos; el intervalo descriptivo por bootstrap de participantes para el cambio de accuracy es aproximadamente +2,23 a +12,92 puntos porcentuales. El intervalo del cambio de F1 incluye cero: no se demuestra una mejora concluyente de F1 macro.

AMS tiene ocho participantes de test; el candidato pierde un acierto. OSM tiene dos regiones, con 49 tramos en total, y tres clases nativas ausentes en test. Sus intervalos por regiones son muy amplios. APN tiene 13 recorridos de un único parque; gana un acierto y no permite estimar variación entre parques de test.

`comparison.json` calcula 2000 réplicas pareadas con semilla 42, remuestreando grupos completos. Con un único grupo devuelve un intervalo nulo explicado, en lugar de tratar los recorridos como parques independientes. Estos intervalos no corrigen la decisión posterior de publicación ni reemplazan datos externos.

## Compatibilidad de fuentes adicionales

Se mantuvo el número de observaciones: fatiga 666, AMS 24, OSM 288 y APN 52. La unión OSM + IGN ya aporta geometría y elevación de los mismos tramos; APN conserva una tarea distinta de recorridos completos y etiquetas oficiales que no equivalen a `sac_scale`.

Se revisaron [Zenodo 4266157](https://zenodo.org/records/4266157), con cuestionarios diarios de fatiga, y [Zenodo 13906740](https://zenodo.org/records/13906740), que usa Borg 6–20. Sus etiquetas y ventanas no equivalen a las respuestas Borg modificadas de GeoFatigue. No se inventó una conversión de escala ni se propagaron etiquetas diarias a minutos como observaciones independientes. El rendimiento de AMS sigue pendiente de ampliar observaciones con HR/SpO₂ nocturnas y un desenlace AMS comparable, además de participantes externos de evaluación.

## Reproducir y verificar

Desde la raíz, con `.venv-ai` y los snapshots originales auditados:

```powershell
npm.cmd run tune:ai
npm.cmd run train:ai-selected
npm.cmd run test:ai-data
npm.cmd run typecheck
npm.cmd test -- --runInBand ai/__tests__ mobile/screens/__tests__/profileAndWearableScreens.test.tsx
```

La primera orden realiza la búsqueda usando solo entrenamiento. La segunda valida la selección guardada y evalúa esa única configuración por tarea. Si un candidato pierde accuracy o F1 frente al artefacto publicado sobre el mismo test, conserva el anterior y archiva el intento. Comparaciones con datos o particiones diferentes se identifican como evaluaciones nuevas.

Para regenerar la comparación original, incluidos los intentos rechazados:

```powershell
.\.venv-ai\Scripts\python.exe training/python/compare_public.py --baseline docs/ai-optimization-2026-10-25/baseline.json --candidates docs/ai-optimization-2026-10-25/publication.json --output docs/ai-optimization-2026-10-25/comparison.json
```

Verificación realizada: **34 pruebas Python aprobadas**, incluidas fuentes y candidato AMS rechazado; **52 pruebas Jest aprobadas** en tres suites; TypeScript sin errores. Ningún modelo se habilitó para inferencia en campo.
