# Fundamento y alcance para la tesis

## Descripción defendible del sistema

MiSendero implementa una selección de senderos basada en atributos documentados y reglas explícitas de compatibilidad. El destino delimita el catálogo disponible; las condiciones declaradas por la persona orientan la prioridad de experiencia, duración, dificultad y paisaje. Distancia y tiempo registrados ayudan a resolver empates. El sistema explica diferencias y conserva los faltantes sin producir etiquetas de relevancia.

La familia de recomendadores basados en restricciones tiene antecedentes académicos, por ejemplo Felfernig y Burke (2008), *Constraint-based recommender systems: technologies and research issues*, [DOI 10.1145/1409540.1409544](https://doi.org/10.1145/1409540.1409544), con [registro institucional](https://tugraz.elsevierpure.com/en/publications/constraint-based-recommender-systems-technologies-and-research-is/). La referencia aporta contexto metodológico; no demuestra que el orden de reglas de MiSendero sea óptimo ni valida sus decisiones sobre trekking. La clasificación de esta implementación como selección basada en conocimiento es una interpretación de su funcionamiento.

## Qué respaldan las fuentes y qué decide el producto

| Elemento | Respaldo o criterio | Límite |
| --- | --- | --- |
| Ubicación, distancia, tiempo y dificultad | Ficha del administrador u organismo turístico, identificando el itinerario y el alcance | Datos de otro acceso, solo ida o solo contexto del destino no verifican una ruta completa |
| Considerar tiempo, dificultad y capacidad personal | APN Nahuel Huapi aconseja informarse sobre tiempo de marcha y dificultad y elegir según capacidad propia | Esa orientación general no fija los umbrales concretos de la app |
| Principiante → fácil; intermedio → fácil/moderada; avanzado → cualquiera | Política explícita del producto | No es una escala validada de aptitud, esfuerzo fisiológico o seguridad |
| Prioridad experiencia, tiempo, dificultad, paisaje | Política reproducible para resolver una búsqueda | No se demostró que maximice satisfacción o reduzca incidentes |
| Menor dificultad, tiempo o distancia para desempatar | Convención transparente entre candidatos comparables | Menor distancia no implica menor exposición, dificultad técnica ni riesgo |
| Ascenso de la traza | Estimación derivada de muestras del modelo de elevación y geometría documentada | No es medición de campo; una traza parcial no representa el recorrido completo |

La orientación del parque puede consultarse en [Trekking y actividades de montaña de Nahuel Huapi](https://nahuelhuapi.gov.ar/trekking-y-actividades-de-montana/). Esa fuente respalda considerar las variables; no se le atribuye el filtro de perfiles o los desempates implementados. Las dificultades de organismos diferentes se conservan con sus etiquetas nativas en la procedencia; normalizarlas a tres categorías no prueba equivalencia entre escalas.

## Cómo se evaluó

Se construyeron doce escenarios funcionales sobre fichas reales, seleccionando casos con cifras publicadas y casos de ambigüedad, falta de datos y contradicción entre fuentes. Los resultados esperados se declararon explícitamente: por ejemplo, que 90 minutos de ida y vuelta de Lahuán Solitario pertenezcan a la ventana de 1–2 horas, que no se cambie de ciudad automáticamente y que un tiempo solo de ida no confirme un total.

El informe conserva entradas, fuentes, respuesta, comprobaciones y hashes para repetir la ejecución. Los parámetros de búsqueda son entradas de prueba; no representan personas reclutadas ni forman un conjunto de entrenamiento. Tampoco se usan las propias recomendaciones como etiquetas correctas para entrenar otro modelo.

Las comprobaciones permiten afirmar que el programa respeta los requisitos evaluados y comunica incertidumbre. No permiten afirmar generalización poblacional, precisión fisiológica, satisfacción ni eficacia para prevenir accidentes. La revisión documental verifica trazabilidad y coherencia de atributos; no sustituye una evaluación independiente de adecuación de los recorridos.

## Datos reales, datos derivados y faltantes

Las cifras publicadas provienen de fuentes identificables. La distancia total derivada de una distancia de ida se marca con su transformación. Las elevaciones son valores de un modelo digital real consultado para coordenadas reales y el ascenso se calcula a partir de ellos: constituyen información derivada, sin inventar observaciones humanas o mediciones de campo. La admisibilidad de datos derivados debe describirse según la metodología de la tesis; no se los debe llamar mediciones directas.

La búsqueda documental posterior incorporó dos referencias de duración y estableció la exclusión de los otros siete tiempos totales y ocho ascensos acumulados de los cálculos que requieren esos campos. Los datos respaldados de otras variables del mismo sendero pueden conservarse. Cada análisis declara su cantidad efectiva de registros y distingue referencias publicadas de mediciones y estimaciones. Las contradicciones no se resuelven eligiendo la cifra más conveniente para aprobar una ventana. Ver [datos incorporados y criterio de exclusión](../catalog-source-search-2026-10-21/README.md).

## Texto propuesto

> Se desarrolló un sistema de selección de senderos basado en atributos del catálogo y reglas explícitas de compatibilidad. Los datos se vincularon a sus fuentes y se distinguieron valores publicados y estimaciones derivadas. Los campos sin respaldo compatible se excluyeron de los cálculos de la variable correspondiente, sin imputación, declarando el número efectivo de registros por análisis. La evaluación consistió en escenarios reproducibles de conformidad funcional y comprobaciones de trazabilidad. Los resultados no se interpretan como validación de aptitud física, seguridad o satisfacción de usuarios. No se generaron etiquetas sintéticas ni se entrenó el recomendador con opiniones.
