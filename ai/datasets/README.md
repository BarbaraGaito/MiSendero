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

No hay imputación aprendida ni escalado global. Los filtros, conversiones y uniones temporales son determinísticos y están documentados. En GeoFatigue se toma un minuto completo de pulso previo a cada respuesta, dentro de una ventana máxima de dos minutos. Las ventanas de todos los registros de una persona permanecen en el mismo grupo.

Cada familia escribe:

- `training/data/public/<modelo>/dataset.csv`: variables y etiquetas originales normalizadas, sin identificadores personales ni ubicación exacta.
- `provenance.json`: hashes, transformaciones y correspondencia de filas con archivos/observaciones públicas; metadatos de auditoría separados de las variables.
- `test_predictions.csv`: respuesta observada y predicha del test para recalcular las métricas.
- `metrics.json`: resultados, baseline, grupos/folds y limitaciones.
- `model.forest.json`: bosque experimental con `deployment_approved: false`.

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

Las fichas APN aportan estimaciones publicadas, no tiempos individuales observados. Las respuestas dinámicas de APN, OSM y el índice IGN pueden cambiar. El downloader rechaza cambios de hash y exige auditar una nueva versión, sin actualizar el lock automáticamente. Conservar los snapshots locales para reproducir exactamente esta corrida.

## Resultados y uso en la app

Para ampliar la comparación con la referencia sin reentrenar ni alterar las observaciones, ejecutar `npm.cmd run evaluate:ai`. Añade F1 de referencia, accuracy balanceada y cobertura de clases; el panel de administración presenta estas comparaciones. Ver [el procedimiento y sus límites](../../docs/evaluacion-modelos-reales.md).

Ver [auditoría y resultados](../../docs/ai-real-data-audit.md) e [incorporación de fuentes argentinas](../../docs/datasets-argentina-2026-10-14.md). El panel presenta estas métricas como investigación y muestra su tarea/población; la evaluación real de una fuente no demuestra rendimiento clínico ni transferencia a trekking.

`npm run train:ai` ejecuta el pipeline público y copia solo las métricas a `ai/models/*Metrics.json` para el panel. Los bosques no se incluyen en la app: ninguno tiene aprobación para el uso concreto. Sus funciones de inferencia conservan la abstención cuando falta validación, pero ya no bloquean el resumen del reloj. El resumen usa las lecturas recientes de pulso y SpO₂ con reglas explícitas de aviso, sin presentar etiquetas de fatiga/riesgo clínico ni porcentajes de confianza del modelo. Ver [análisis operativo de lecturas](../../docs/analisis-lecturas-wearable.md).

Esta separación evita usar una evaluación de Borg, AMS nocturno o sac_scale como si validara las antiguas salidas bajo/medio/alto. Los modelos públicos requieren más datos, variables relevantes y una validación de la tarea final antes de habilitar inferencia de campo.
