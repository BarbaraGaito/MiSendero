# MiSendero: evaluación con fuentes públicas reales

La política exige mediciones públicas y etiquetas observadas independientemente de los predictores. No se generan datos sintéticos: no hay data augmentation y todas las filas de entrenamiento, validación y prueba son observaciones públicas. Los CSV, entrenadores y modelos históricos con contexto inventado o etiquetas por reglas fueron eliminados del repositorio.

## Pipeline vigente

Los adaptadores en `training/python/public_sources.py` leen únicamente snapshots públicos auditados. `training/data/public/sources.lock.json` fija SHA-256 de los archivos originales y `source_catalog.json` conserva versiones, licencias y checksums publicados. Ningún CSV procesado arbitrario ni fila de los datasets anteriores se mezcla con ellos. Cambiar un archivo o agregar un snapshot de OSM sin actualizar su auditoría hace fallar la preparación.

| Evaluación | Mediciones | Etiqueta independiente | Alcance |
| --- | --- | --- | --- |
| Fatiga | Pulso medido por Empatica y tiempo desde el inicio publicado de cada tarea | Respuesta original Borg modificada de GeoFatigue, conservada como `Borg N` | Tareas de 20 minutos al aire libre con carga; 40 participantes |
| AMS | HR y SpO2 medias nocturnas publicadas | Resultado original `MOR_AMS+`, codificado reversiblemente como AMS+/AMS- | Hipoxia física controlada equivalente a 4200 m; 24 participantes |
| Dificultad técnica de tramos | Geometría OSM y relieve original IGN de 30 m | `sac_scale` nativo anotado por colaboradores | 288 tramos de seis regiones argentinas; test geográfico Ushuaia/Mendoza |
| Dificultad de recorridos completos | Distancia y duración estimadas publicadas por APN, conservando el sentido indicado | Dificultad oficial publicada, incluida media-alta | 52 recorridos de cinco parques; test geográfico Tierra del Fuego |

No se inventan velocidad, desnivel, pulso de reposo, fatiga ni etiquetas faltantes. Se omiten registros incompletos. No se calculan etiquetas con umbrales de HR, SpO2, pendiente o distancia. Convertir una respuesta Borg en el texto `Borg N` o renombrar el resultado binario AMS conserva el valor observado sin inferirlo desde los sensores. Las categorías nativas no se convierten en bajo/medio/alto.

GeoFatigue contiene respuestas subjetivas observadas, y OSM anotaciones comunitarias publicadas: son independientes del modelo, pero no constituyen una certificación de seguridad ni garantizan una verdad objetiva universal. El estudio de altitud mide personas reales en hipoxia controlada; no genera datos fisiológicos por simulación numérica.

## Separación y auditoría

`training/python/train_public.py` reserva una sola partición por participante con semilla 42 para fatiga/AMS. Para las fuentes argentinas usa los parques/regiones declarados en el catálogo antes de entrenar: Tierra del Fuego para APN, Ushuaia/Mendoza para OSM. Las redes conectadas, nombres y relaciones compartidas permanecen juntas. No se prueban otras semillas ni particiones para mejorar los resultados. Los grupos del test no participan en tuning ni validación cruzada. La selección de parámetros usa GroupKFold solo en entrenamiento.

No hay imputación aprendida ni escalado global. SGD, regresión logística y MLP ajustan `StandardScaler` únicamente dentro del entrenamiento de cada fold; los bosques no escalan entradas. Los filtros, conversiones y uniones temporales son determinísticos y están documentados. En GeoFatigue se toma un minuto completo de pulso previo a cada respuesta, dentro de una ventana máxima de dos minutos. Las ventanas de todos los registros de una persona permanecen en el mismo grupo.

El ajuste del 25/10/2026 compara 76 configuraciones por tarea de Random Forest, Extra Trees, regresión logística, SGD y MLP con backpropagation. Incluye las cuatro configuraciones anteriores. Selecciona el mayor F1 macro medio en los mismos folds por grupos, con desempate por orden fijo. El test no elige algoritmos ni parámetros. `selection.json` conserva el plan, predicciones fuera de fold, resultados y advertencias de convergencia de todos los candidatos. La CV usada para seleccionar es optimista; no se presenta como estimación independiente de generalización. Ver [comparación con la corrida anterior](../../docs/ai-optimization-2026-10-25/README.md).

Cada familia escribe:

- `training/data/public/<modelo>/dataset.csv`: variables y etiquetas originales normalizadas, sin identificadores personales ni ubicación exacta.
- `provenance.json`: hashes, transformaciones y correspondencia de filas con archivos/observaciones públicas; metadatos de auditoría separados de las variables.
- `test_predictions.csv`: respuesta observada y predicha del test para recalcular las métricas.
- `metrics.json`: resultados, baseline, grupos/folds y limitaciones.
- `model.forest.json` o `model.classifier.json`: modelo experimental en JSON con `deployment_approved: false`. El segundo formato conserva escalado y coeficientes de modelos lineales/redes cuando corresponde; el validador reproduce sus predicciones sin cargar pickle.
- `selection.json`: evidencia de selección exclusivamente dentro de entrenamiento, sin resultados de test por candidato.

`npm run validate:ai-data` verifica hashes, etiquetas originales, particiones, que el modelo se ajustó solo con las filas observadas de entrenamiento y recalcula accuracy/F1 del test. `npm run test:ai-data` comprueba filtraciones por grupos, que la validación cruzada ajusta solo filas observadas y el rechazo de fuentes modificadas.

## Reproducir

Se necesita Python de 64 bits, un entorno `.venv-ai` y las dependencias de `training/python/requirements-public.lock.txt`. El entorno ya está preparado en este workspace. Para otro equipo, crear el entorno e instalar ese archivo con pip. Los originales públicos quedan en `training/data/raw/public_audit/`, excluidos de Git.

```powershell
npm run fetch:ai-data
npm run prepare:ai-datasets
npm run train:ai
npm run validate:ai-data
npm run test:ai-data
```

Para separar selección de evaluación final:

```powershell
npm run tune:ai
npm run train:ai-selected
```

El segundo comando verifica los hashes, el plan y las predicciones fuera de fold del informe guardado; no vuelve a buscar candidatos. Cambiar datos o particiones invalida esa selección.

La publicación conserva el anterior si el candidato pierde accuracy o F1 macro sobre el mismo test. Archiva todos los artefactos del intento en `rejected-candidates/<versión>/`; el validador también los comprueba. Esta decisión sí usa el test y limita la interpretación a una comparación descriptiva. En la corrida del 25/10 se conservó AMS; el informe distingue sus mejores resultados de CV de la caída observada en test.

Las fichas APN aportan estimaciones publicadas, no tiempos individuales observados. Las respuestas dinámicas de APN, OSM y el índice IGN pueden cambiar. El downloader rechaza cambios de hash y exige auditar una nueva versión, sin actualizar el lock automáticamente. Conservar los snapshots locales para reproducir exactamente esta corrida.

## Resultados y uso en la app

Para ampliar la comparación con la referencia sin reentrenar ni alterar las observaciones, ejecutar `npm.cmd run evaluate:ai`. Añade F1 de referencia, accuracy balanceada y cobertura de clases; el panel de administración presenta estas comparaciones. Ver [el procedimiento y sus límites](../../docs/evaluacion-modelos-reales.md).

Ver [auditoría y resultados](../../docs/ai-real-data-audit.md) e [incorporación de fuentes argentinas](../../docs/datasets-argentina-2026-10-14.md). El panel presenta estas métricas como investigación y muestra su tarea/población; la evaluación real de una fuente no demuestra rendimiento clínico ni transferencia a trekking.

`npm run train:ai` ejecuta el pipeline histórico y copia sus métricas a `ai/models/*Metrics.json` para el panel. Sus bosques conservan los controles de aprobación originales y no se incluyen como modelos de campo. El resumen del reloj usa las lecturas recientes de pulso y SpO₂ con reglas explícitas de aviso. Ver [análisis operativo de lecturas](../../docs/analisis-lecturas-wearable.md).

El pipeline separado `npm run ai:field -- prepare|select|evaluate|validate` incorpora desde el 27/11/2026 los controles orientativos del prototipo: Borg causal sobre las mismas 666 observaciones de GeoFatigue y AMS de la siguiente etapa sobre 377 pares de visitas reales de Boos. Conserva evidencia en `training/data/field-ai/v1` y exporta a `ai/models/field`. El modelo Borg mejora MAE frente al autorreporte previo. AMS mejora discriminación y Brier, pero su umbral produce únicamente decisiones positivas en test; por eso la app suprime esa clasificación y ofrece solo una puntuación contextual. No se mezclan escalas incompatibles ni se habilita un diagnóstico clínico. El [README principal](../../README.md#inteligencia-artificial-y-recomendación) documenta resultados, reproducción y límites.

Esta separación evita usar una evaluación de Borg, AMS nocturno o sac_scale como si validara las antiguas salidas bajo/medio/alto. Los modelos públicos requieren más datos, variables relevantes y una validación de la tarea final antes de habilitar inferencia de campo.
