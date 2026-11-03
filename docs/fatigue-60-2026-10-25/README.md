# Fatiga: accuracy exacta de 60,34 % verificada

**Objetivo numérico alcanzado: 108/179 = 60,3352 %.** El modelo ganador es una red neuronal MLP con Borg previa observada y contexto de actividad. La auditoría reproducible está en [goal-completion.json](goal-completion.json). Es un resultado de investigación sobre un benchmark publicado y reutilizado; requiere evaluación prospectiva independiente antes de habilitar inferencia de campo.

El usuario autorizó expresamente: **«Puede usar una Borg previa»**. Esa respuesta se incorpora como entrada observada de la misma sesión, con antigüedad de **1 a 15 minutos**. Se excluyen respuestas actuales, futuras y de otras sesiones. El modelo ganador no utiliza pulso ni otros sensores: el resultado corresponde a autoevaluación previa y contexto. El modelo publicado de sensores solos conserva **31,8436 %** y su inferencia continúa sin aprobación de campo.

## Evaluación preservada

Se predice el **valor Borg nativo exacto**. No se agrupan etiquetas en bandas ni se cuentan aciertos por tolerancia ±1. Se mantienen las 666 observaciones activas originales: 487 respuestas de 28 participantes para entrenamiento y validación; 179 respuestas de otros 12 participantes para test. No se eliminan casos difíciles ni se agregan respuestas de reposo al denominador.

La selección de cada familia usa cinco folds de `GroupKFold` dentro de entrenamiento. Imputación y escalado se ajustan dentro de cada fold. El test no participa en la búsqueda de hiperparámetros de cada familia. Como se evaluaron sucesivamente varias familias en el mismo benchmark ya publicado, este resultado es descriptivo y puede tener optimismo por reutilización. La separación de participantes al entrenar no convierte el benchmark reutilizado en una nueva confirmación externa.

| Resultado en los mismos 179 casos | Accuracy exacta | F1 macro |
| --- | ---: | ---: |
| Modelo publicado de sensores solos | 31,8436 % | Ver métricas originales |
| Repetir la última Borg observada | 43,5754 % (78/179) | 33,5078 % |
| MLP con Borg previa y contexto | **60,3352 % (108/179)** | **31,8635 %** |

La accuracy supera la referencia de Borg previa en **16,7598 puntos porcentuales**. El F1 macro es inferior al de esa referencia: la mejora de accuracy no demuestra una mejora uniforme en todas las intensidades. Borg 0 y 10 no tienen observaciones en esta cohorte; se mantienen explícitas en el vocabulario y en el cálculo macro de 11 clases. Hay pocos ejemplos en los extremos de la escala. Estos límites aparecen también en el panel de administración, que muestra ambos resultados de referencia.

## Artefacto ganador y entradas

Archivos bajo `training/data/fatigue-research/calibrated-alternatives-v1/`:

- `selection.json`: 60 candidatos completos y predicciones fuera de fold; ganador `alternative-023` por accuracy media de validación.
- `selection-source.py`: copia del código con el que se congeló la selección.
- `evaluation/model.calibrated.json`: modelo portable de datos, de aproximadamente 22 KB; no requiere cargar pickle.
- `evaluation/model.joblib`: artefacto local entrenado, conservado para auditoría con SHA-256.
- `evaluation/metrics.json` y `evaluation/test_predictions.csv`: métricas y predicción de cada caso original reservado.

La red tiene capas ocultas **16 y 8**, activación ReLU, optimizador **L-BFGS**, regularización `alpha=10`, máximo de 1000 iteraciones y semilla 42. El ajuste final convergió en 312 iteraciones; no hubo advertencias de convergencia en sus cinco folds. La accuracy CV media fue **60,8206 %**. Aprende el cambio desde Borg previa y lo traduce al valor Borg actual, limitado al rango nativo 0–10. Se compararon también algoritmos de árboles, SVM, modelos lineales y variantes neuronales.

Las 13 entradas, en orden, son:

```text
prior_borg, prior_age_minutes, prior2_borg, prior2_age_minutes,
prior_borg_slope, prior_in_current_task, prior_count_current_task,
elapsed_minutes, cumulative_active_minutes, task_order,
terrain_stairs, terrain_ramp, terrain_flat_trail
```

La Borg más reciente y su antigüedad son obligatorias y nunca se imputan. La segunda Borg previa y su pendiente pueden faltar; la imputación se aprende exclusivamente con entrenamiento. Se usa el contexto conocido hasta ese instante: tiempo de la tarea actual, tiempo activo acumulado, orden de tarea y tipo de terreno. La historia se limita a la sesión y a los 15 minutos anteriores. Las respuestas previas reales también se proporcionan durante el test; este protocolo evalúa un sistema con retroalimentación del usuario durante la actividad.

`ai/models/calibratedFatigueMetrics.json` es una copia exacta de las métricas verificadas. El panel de administración la presenta como una evaluación adicional, con requisito de Borg previa, referencia y advertencia de benchmark reutilizado. No se implementó captura de autoevaluaciones ni se activó el modelo en la predicción de caminatas. Para uso futuro en la app se necesita esa captura, contexto compatible y una evaluación independiente. Todos los artefactos mantienen `deployment_approved: false`.

## Experimentos conservados

| Experimento | Configuraciones | Mejor accuracy CV | Accuracy del candidato en test |
| --- | ---: | ---: | ---: |
| Ocho sensores y contexto causal | 64 | 40,40 % | No evaluado |
| Transferencia desde WorkerFatigue | 36 | 41,15 % | No evaluado |
| Regresión ordinal, coincidencia exacta | 60 | 39,99 % | No evaluado |
| Señales AVRO originales y movimiento | 45 | 42,87 % | No evaluado |
| Borg previa + sensores, v1 | 36 | 61,07 % | 58,6592 % (105/179) |
| Historial Borg y cambio de pulso, v2 | 73 | 61,42 % | 56,9832 % (102/179) |
| Ensamble de cinco modelos | 19 | 62,62 % | 57,5419 % (103/179) |
| Expertos para comienzo y continuidad de tarea | 72 | 61,57 % | No evaluado |
| Fusión de probabilidades de árboles y expertos | 92 | 64,43 % | 58,1006 % (104/179) |
| Historia de la sesión y tareas anteriores | 72 | 61,23 % | No evaluado |
| SVM, lineales y redes con Borg previa | 60 | 60,82 % | **60,3352 % (108/179)** |

No se ocultaron los resultados inferiores ni se seleccionó un candidato distinto del ganador por validación dentro de cada familia. Los evaluadores se niegan a sobrescribir evaluaciones congeladas. La búsqueda v2 se reanudó desde 27 candidatos guardados después de un error de escritura del sistema, sin cambiar datos, semilla ni parámetros.

La primera evaluación de la familia ganadora guardó el modelo, pero falló al escribir el CSV por un `import pandas` faltante. Se conservó el código original y se corrigió solo el reporte. Una comparación AST protege las definiciones de entrenamiento y predicción originales. La recuperación reutilizó el mismo modelo ya ajustado y dejó ambos hashes en `evaluation_recovery`. La auditoría final volvió a entrenarlo de forma independiente y comprobó que coincide.

## Datos adicionales y señales

Se prepararon 86 predictores causales de pulso, EDA, variabilidad de pulso publicada, respiración, temperatura, acelerometría, pasos y MET, y después 304 predictores con señales AVRO originales, intervalos entre picos, movimiento y sueño previo. Se conservaron las mismas respuestas nativas; las señales de alta frecuencia no se transformaron en nuevas observaciones etiquetadas. Las ventanas terminan antes de la respuesta y las brechas no se interpolan para fabricar datos espectrales.

Se descargó el archivo procesado de [WorkerFatigue](https://github.com/payalmohapatra/WorkerFatigue), verificando el SHA-256 de Git LFS y los checksums originales de [Zenodo 12788571](https://zenodo.org/records/12788571). Cada respuesta se contrastó con `USER FORM RESPONSE.xlsx`. Se excluyeron once sesiones por discrepancias, falta de correspondencia inequívoca o de baseline, y una respuesta sin un minuto de señal compatible. Quedaron **307 respuestas observadas de 39 participantes adicionales**: 253 para ensayos de transferencia y 54 de ocho participantes externos reservadas, fuera del denominador de la validación GeoFatigue. La transferencia no mejoró suficientemente la validación; el ganador final se entrena con las 487 respuestas originales.

Se armonizaron únicamente HR, respiración y temperatura con unidades conocidas. HRV de definición desconocida no se convirtió a RMSSD, ni las aceleraciones de pecho se equipararon a las de muñeca. Se excluyeron objetivos interpolados. Los datos crudos permanecen bajo `training/data/raw/`, fuera de Git. No se ejecutó código descargado de los estudios.

El dataset de cinta caminadora [Zenodo 23208045](https://zenodo.org/records/23208045) no exponía archivos descargables por su embargo. Otros datasets revisados usan fatiga diaria o Borg 6–20 y no se combinaron mediante conversiones inventadas.

## Reproducción y comprobaciones

Las dependencias están fijadas en `training/python/requirements-fatigue-research.lock.txt`, que incluye los requisitos públicos. El entorno utilizado tiene Python 3.12, scikit-learn 1.9.1, fastavro 1.13.1 y XGBoost 3.4.1. El modelo MLP no necesita fastavro o XGBoost para inferir desde JSON.

Verificar el resultado existente, sin buscar otro modelo ni reescribir sus predicciones:

```powershell
.\.venv-ai\Scripts\python.exe training/python/validate_fatigue_release.py --output docs/fatigue-60-2026-10-25/goal-completion.json
npm.cmd run test:ai-data
npm.cmd run typecheck
npm.cmd test -- --runInBand ai/__tests__ mobile/screens/__tests__/profileAndWearableScreens.test.tsx
```

El verificador valida los hashes de fuentes, las 666 etiquetas originales, los 13 predictores reconstruidos desde cuestionarios y metadatos originales, los scores OOF de los 60 candidatos y el ganador por CV. Vuelve a ajustar sus cinco folds y el modelo final con los 487 casos de entrenamiento. Compara probabilidades y decisiones del nuevo ajuste, del artefacto guardado y del JSON en las 666 filas, con tolerancia numérica de 1e-10 para probabilidades y coincidencia exacta para decisiones. También comprueba los 179 resultados CSV, rechaza calibraciones ausentes/actuales/futuras/vencidas y verifica que alterar la etiqueta actual no afecta la predicción.

**Comprobaciones finales aprobadas:** 64 pruebas Python de datos y modelos; 52 pruebas Jest de inferencia e interfaz; `tsc --noEmit`; auditoría completa del artefacto. Hay 30 pruebas Python nuevas en esta investigación. [audit.json](audit.json) es un checkpoint anterior a la calibración y conserva su estado histórico; [goal-completion.json](goal-completion.json) contiene el resultado final.

Para repetir la selección neuronal sobre las entradas ya auditadas:

```powershell
.\.venv-ai\Scripts\python.exe training/python/fatigue_calibrated_alternatives.py
```

Se preservan todas las etapas en `training/python/fatigue_*.py`, la descarga en `fetch_fatigue_extra.py`, la preparación externa en `worker_fatigue.py` y los informes bajo `training/data/fatigue-research/`. En una ejecución nueva, preparar en orden `fatigue_features.py`, `fatigue_raw_features.py`, `fatigue_calibrated.py` y `fatigue_calibrated_v2.py`; luego ejecutar la selección neuronal y una sola evaluación con `fatigue_calibrated_alternatives.py --evaluate`, seguida de `export_fatigue_release.py`. Los evaluadores rechazan una evaluación existente para preservar su evidencia. Tras una nueva exportación, copiar sus métricas al snapshot de administración antes de ejecutar el verificador. Cambiar fuentes, plan, código de entrenamiento o partición requiere una versión nueva.
