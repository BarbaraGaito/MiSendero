# Recomendador local: datos, entrenamiento e inferencia

El producto usa una encuesta de cuatro preguntas, toma la experiencia del perfil guardado de la cuenta y devuelve una ruta de PostgreSQL. Si el perfil falta, la app exige completar primero su encuesta y luego vuelve al recomendador. No tiene chat. El código de entrenamiento supervisado está implementado; **no hay un modelo personalizado entrenado con evidencia real suficiente todavía**. En ese estado la API utiliza una referencia determinista y lo declara en `ranking.method`.

## Decisión de modelo

Se implementó *learning to rank pointwise*: `RandomForestRegressor` de scikit-learn aprende una relevancia graduada 0–3 para cada par encuesta–sendero y sus predicciones ordenan los candidatos. No predice seguridad ni probabilidad de satisfacción. Son 80 árboles, profundidad máxima 6, hojas de al menos 3 ejemplos y un hilo. La semilla es 42 y cada consulta pesa lo mismo, independientemente de cuántos candidatos tenga.

La elección permite relaciones no lineales en datos tabulares y tratamiento nativo de faltantes, con recursos CPU acotados. [Referencia oficial de Random Forest 1.7](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.RandomForestRegressor.html). Regresión logística sería una buena referencia para etiquetas binarias, pero perdería la graduación propuesta; HistGradientBoosting es una alternativa futura a comparar cuando haya más datos. No se afirma que Random Forest sea superior antes de medirlo con etiquetas reales.

La ubicación se aplica **antes** del modelo y nunca se amplía a otra ciudad para completar la respuesta. La política v4 devuelve una alternativa local aun cuando difieran el tiempo, paisaje o dificultad. Prioriza el perfil: Principiante favorece Baja; Intermedio favorece Baja/Media; Avanzado admite las tres. Si no hay ninguna dentro del nivel, selecciona el nivel menos exigente disponible y advierte que supera el perfil, sin afirmar aptitud. Omitir experiencia conserva la prioridad de principiante; las etiquetas para entrenar exigen experiencia explícita.

La política v4 prioriza coincidencias exactas; cuando faltan, conserva primero paisaje, luego duración, luego dificultad, sin descartar todos los candidatos por esos valores. Las diferencias aparecen en `preferenceAdjustments` y las plantillas explicativas. Se conservan los aliases documentados, los calificadores provinciales y la diferencia entre ciudad explícita y provincia. Un posible error de una letra exige confirmar la escritura: no se cambia automáticamente de ciudad.

## Dataset y contrato de etiquetas

`npm --prefix backend run ranking:prepare` lee `trails` sin escrituras y genera:

- `training/data/trail-ranking/catalog.json`: candidatos verificados y auditoría de faltantes.
- `training/data/trail-ranking/prepared/examples.jsonl` y `manifest.json`: pares etiquetados y hashes. Sin etiquetas, el primer archivo queda vacío. `prepared/` está ignorado por Git.

Para agregar etiquetas reales, proporcionar un JSONL revisado:

```powershell
npm --prefix backend run ranking:prepare -- --labels training/data/trail-ranking/private/labels.jsonl
```

Debido a que `ranking:prepare` ejecuta build y preparación en un mismo script, para pasar parámetros en cualquier shell también puede usarse explícitamente:

```powershell
npm --prefix backend run build
node backend/scripts/prepareTrailRanking.js --labels training/data/trail-ranking/private/labels.jsonl
```

Cada fila debe tener exactamente estos campos. Los marcadores son una descripción del contrato: **no son observaciones ni ejemplos para entrenar**:

```json
{
  "queryId": "identificador_anonimo_consulta",
  "splitGroupId": "identificador_anonimo_participante",
  "preferences": {
    "destination": "destino realmente evaluado del catálogo",
    "trailTypes": ["bosques"],
    "duration": "2-4",
    "difficulty": "moderada",
    "experience": "intermedio"
  },
  "trailId": 123,
  "relevance": 2,
  "source": "expert_judgment",
  "consentVerified": true,
  "synthetic": false,
  "completeCandidateSet": true
}
```

`trailId` debe ser un ID real de la base exportada. Los identificadores anónimos admiten 8–80 letras ASCII, números, guiones o guiones bajos. No usar correo, nombre, token de cuenta ni coordenadas personales. La correspondencia de participantes y el consentimiento quedan en el registro de investigación protegido, fuera del repositorio y del modelo. Marcar `consentVerified` exige una revisión humana del consentimiento; el booleano por sí solo no lo acredita.

Fuentes de etiquetas admitidas: `expert_judgment` y `consented_user_rating`. Escala consistente: 0 no lo elegiría, 1 coincidencia débil, 2 adecuado, 3 muy adecuado. El estudio debe fijar instrucciones y documentar si el evaluador es un experto o el propio usuario. No confundir evaluación experta con satisfacción observada.

Cada consulta debe tener una valoración explícita para **todos sus candidatos compatibles de la primera etapa no vacía** en el snapshot. Repetir las mismas preferencias y grupo en cada fila. La preparación comparte la política del endpoint y agrupa aliases de la misma área geográfica al calcular la huella de preferencias, evitando separar consultas equivalentes entre entrenamiento y evaluación. Rechaza candidatos desconocidos, incompatibles, duplicados o ausentes, campos personales adicionales y datos sintéticos. No convierte rutas no elegidas, clics ni actividades finalizadas en etiquetas negativas. La app no guarda encuestas ni activa recolección de datos automáticamente; un estudio requiere su protocolo y consentimiento.

## Características y faltantes

`backend/src/ai/featureSpec.json` fija versión, nombres y orden. Node genera los mismos vectores para entrenamiento e inferencia mediante `featuresFor`. Python consume esos vectores; no mantiene una segunda implementación de sus transformaciones.

Incluye coincidencia de paisajes, cercanía al tiempo preferido, minutos, distancia, dificultad, experiencia, desnivel de referencia cuando está documentado, indicadores de terreno y dificultad preferida. El destino es una restricción: `destination_match` vale 1 entre los candidatos ya filtrados, no enseña geocodificación al modelo. Provincia/parque se consideran a través de la ubicación documentada; no se asignan coordenadas ni categorías geográficas supuestas. «Indiferente» no se convierte en una preferencia física inventada.

`null` pasa a `NaN` únicamente dentro de scikit-learn. No se rellena el catálogo con alturas, terrenos o distancias estimados por el modelo. Las referencias de elevación disponibles pueden provenir de trazas y DEM, son aproximadas y no mediciones de campo. Un desnivel genérico no se transforma en ascenso acumulado. Los tiempos derivados de ida permanecen señalados; estudiar por separado su incertidumbre. El modelo no recibe clima, accesibilidad o seguridad actual no verificada.

La referencia determinista asigna `4 × coincidencia de tipos + 2 × cercanía de duración + margen de esfuerzo + cercanía de dificultad preferida` dentro de la etapa seleccionada. Los empates se resuelven por ID. Es una referencia basada en reglas, **no ML entrenado**. La versión 4 conserva el orden de vectores y cambia política y referencia: regenerar ejemplos, entrenar y evaluar de nuevo. La versión/hash rechaza artefactos anteriores. La duración sin alcance documentado pasa a null en proximidad y minutos del vector; no se trata como un total conocido. Las fichas antiguas sin fuente se identifican como `catalog_only`, no como verificadas externamente.

## Entrenar y evaluar

Instalar Python 3.11 o 3.12. Usar la misma versión menor al entrenar y servir, y las dependencias fijadas:

```powershell
py -3.12 -m venv .venv-trail-ranking
.\.venv-trail-ranking\Scripts\python.exe -m pip install -r backend/ml/requirements.lock.txt
npm --prefix backend run ranking:prepare
.\.venv-trail-ranking\Scripts\python.exe backend/ml/train.py --catalog training/data/trail-ranking/catalog.json --prepared training/data/trail-ranking/prepared --output backend/ml/artifacts/version-nueva
```

En Linux reemplazar el intérprete por el de su entorno virtual. No se entrena dentro del servidor ni durante una solicitud. El entrenamiento sin etiquetas devuelve `insufficient_real_data`, código de salida 2, un `training-status.json`, **ningún modelo y métricas nulas**. Es el resultado esperado del catálogo actual.

La política mínima de ingeniería exige 300 pares, 100 consultas, 10 componentes independientes, 10 senderos y 60 consultas con valoraciones distintas entre candidatos. No son una garantía estadística ni un tamaño universalmente suficiente. Debe justificarse representatividad, diversidad de preferencias, acuerdo entre evaluadores y potencia de la evaluación. La política no fabrica filas para alcanzar los mínimos.

Partición reproducible 60/20/20 por componentes que unen al mismo participante y a consultas con preferencias idénticas, transitivamente. Ninguno cruza entrenamiento, validación y test. El test queda para el informe final; no se ajustan hiperparámetros con él. La evaluación representa consultas nuevas sobre un catálogo conocido, no generalización a países o senderos nuevos. Para estudiar esa última capacidad se necesita un protocolo adicional de exclusión geográfica/familias de rutas. Itinerarios que comparten tramos deben declararse como tales.

Se calculan, por consulta y luego promediadas, Precision@1/@3, Recall@1/@3 y NDCG@1/@3. Relevante para Precision/Recall significa grado >=2; NDCG usa ganancia `2^grado-1`. Precision@K divide por K incluso si hay menos candidatos; Recall y NDCG omiten consultas sin positivos/ganancia y registran su soporte. El desempate es por ID, igual que Node. [Referencia de métricas de ranking](https://scikit-learn.org/stable/modules/model_evaluation.html).

Se informa coincidencia con restricciones obligatorias del candidato elegido y cobertura de IDs recomendados sobre el catálogo elegible del snapshot. La primera es una propiedad de los filtros externos al modelo, no una métrica de seguridad aprendida. La cobertura es específica de las consultas evaluadas; un catálogo sin preferencias etiquetadas no tiene una cobertura predictiva demostrada.

Ambas particiones de evaluación comparan modelo y baseline. Solo la **validación** decide elegibilidad operativa: NDCG@1 mejora >=0,01, NDCG@3 y Precision@1 no empeoran y las restricciones se cumplen. Es un umbral de ingeniería, no una prueba de significación. Un artefacto que no lo cumple queda `deployable: false` y el worker lo rechaza. No repetir selección mirando el test para después publicar ese mismo test como independiente.

## Artefactos y operación

Cada directorio nuevo conserva `model.joblib`, `metadata.json` y `training-status.json`. No se sobrescribe una versión existente. Los metadatos incluyen versión del modelo, semilla, parámetros, versiones Python/numpy/sklearn, hashes de datos, preparación, código de entrenamiento, especificación y modelo, particiones y evaluación.

`joblib` es pickle: solo cargar artefactos propios bajo control del operador. El SHA-256 detecta corrupción, no autoriza un archivo de terceros. No es seguro descargar y cargar un `.joblib` de Internet. [Advertencia oficial de persistencia](https://scikit-learn.org/1.7/model_persistence.html). Los artefactos binarios están ignorados en Git; publicar cada versión revisada en un almacenamiento privado con su manifiesto, o Git LFS privado. Conservar el commit del código correspondiente. El worker comprueba esquema, hash, versiones y elegibilidad antes de cargar.

Node crea un único hijo Python por proceso, mediante JSONL por stdin/stdout y sin shell ni puerto público. El hijo no recibe `DATABASE_URL`, claves ni datos de cuentas. Carga el modelo una sola vez, limita tramas y cantidades, y solo devuelve puntuaciones finitas. Node selecciona el ID de su propia lista filtrada y redacta con plantillas; Python no puede devolver coordenadas, textos o nombres inventados.

Sin configuración, mientras inicia, si falta Python/modelo, si hay corrupción, timeout o caída, el endpoint sigue con baseline. Una falla deshabilita ese worker hasta reiniciar el backend; no crea un bucle de procesos. Plazo de inferencia configurable 100–5000 ms, arranque máximo 15 segundos en segundo plano. No hay entrenamiento ni salida a Internet en el flujo de recomendación.

## Pruebas técnicas

```powershell
py -m unittest discover -s backend/ml/tests -v
npm --prefix backend test -- --runInBand
npm test -- --runInBand
npm run typecheck
```

Las fixtures Python entrenan un bosque sintético **solo dentro de directorios temporales** para verificar el pipeline y el protocolo. No se exportan como evidencia académica ni como modelo de producción. Su metadata contiene `synthetic: true`, `technicalTestOnly: true`, `deployable: false`. Servirlas requiere un flag de pruebas explícito y `NODE_ENV=test`; producción las rechaza. El comando de entrenamiento público no habilita ese modo.

La evidencia de datos reales y sus limitaciones está en [la auditoría](../../docs/trail-ranking-2026-10-17/README.md). El despliegue con systemd, RDS y reversión está en [la guía de integración](../../docs/trail-recommendation.md).
