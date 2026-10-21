# Recomendación por datos del catálogo

La app selecciona un sendero real de PostgreSQL mediante reglas explícitas. Usa destino, experiencia del perfil, duración y dificultad. El paisaje es un criterio secundario. No consulta opiniones, reseñas, estrellas ni relevancias asignadas por personas. No entrena ni ejecuta un modelo para esta selección, y no necesita datos sintéticos.

## Datos esenciales y procedencia

Una ficha utilizable necesita ID, nombre, ubicación, descripción, distancia positiva, dificultad reconocida y duración interpretable. La respuesta conserva los valores de la ficha, sus fuentes y fecha de revisión cuando existen. Las fuentes suministradas deben pertenecer a los proveedores admitidos por el catálogo.

La tarjeta muestra distancia, duración, dificultad y desnivel de ascenso si está documentado. Actualmente el desnivel que recibe la API proviene del perfil de elevación guardado o de un perfil de referencia incluido que coincida con clave, nombre y geometría de la ruta. Se calcula con Copernicus DEM GLO-90 mediante Open-Meteo. La pantalla lo identifica como estimado sobre la traza disponible y aclara que no es una medición de campo. El desnivel ausente sigue siendo nulo y se muestra como no documentado: nunca se interpreta como cero ni se calcula a partir de distancia o dificultad. No se usa para ordenar porque no está disponible de forma comparable en todo el catálogo.

Las fichas antiguas sin procedencia se identifican como `catalog_only`, sin inventar fuentes, fecha ni alcance de ida y vuelta. Si la duración total no está confirmada, no cuenta como coincidencia con un rango de tiempo. Las estimaciones publicadas conservan su aviso; no se fabrican medidas para completar fichas.

La revisión del 21/10 agrega fuentes y límites por campo para las diez fichas iniciales; `partial` distingue las verificaciones incompletas. Una página que confirma un destino no verifica automáticamente todos sus atributos. Las contradicciones de duración y los avisos se muestran en la tarjeta. Un tiempo total publicado puede estar confirmado aunque la forma de la traza sea desconocida: no se deduce un recorrido circular de la palabra circuito. Ver [la validación, fuentes y pendientes](catalog-validation-2026-10-21/README.md).

## Orden de selección

1. Buscar únicamente dentro del destino. Conservar aliases y calificadores geográficos; un posible error de escritura exige que el usuario corrija el destino antes de buscar. Nunca cambiar de ciudad automáticamente.
2. Priorizar las dificultades contempladas para el perfil: principiante, fácil; intermedio, fácil o moderada; avanzado, cualquiera. Es una regla del producto, no una certificación de aptitud. Si ninguna coincide, conservar la menor dificultad local y advertir que supera el perfil.
3. Dentro de ese grupo, priorizar las coincidencias de duración total, después dificultad elegida y después paisaje. El primer criterio tiene prioridad sobre los siguientes; no se suman puntuaciones aprendidas o valoraciones.
4. Entre opciones del mismo grupo, ordenar por menor dificultad publicada, duración total confirmada, menor duración, menor distancia y finalmente ID ascendente. El ID solo resuelve empates de forma reproducible. No se afirma que menor distancia equivalga a mayor seguridad.

Si no hay coincidencia exacta, se ofrece una alternativa local con las diferencias explícitas en `preferenceAdjustments`. No se cambian sus atributos para ajustarlos a la búsqueda. `no_results` significa que ese destino no tiene fichas utilizables; `clarification` pide precisar un destino ambiguo o corregir su escritura.

Estas reglas expresan decisiones transparentes del producto. No son resultados de aprendizaje automático ni prueban adecuación, seguridad o satisfacción. La experiencia declarada y la dificultad publicada tienen límites; las condiciones actuales y habilitaciones deben verificarse antes de salir.

## App y API

Se conservan las cuatro preguntas de búsqueda: destino, paisaje, duración y dificultad. Son condiciones que indica el usuario para su salida; no son etiquetas de entrenamiento ni puntuaciones de senderos. La experiencia se obtiene del perfil de la cuenta autenticada. Si falta, la app pide completarlo y regresa a la búsqueda. Se conserva el flujo de una tarjeta con acceso al detalle y opción de buscar otro sendero.

`POST /api/ai/recommend-trail` requiere autenticación. El cuerpo contiene `destination`, `trailTypes`, `duration`, `difficulty` y opcionalmente `experience` para clientes antiguos. La API valida estrictamente el contrato, rechaza consultas fuera de alcance y limita solicitudes por cuenta e IP. `GET /api/ai/destinations` devuelve destinos del catálogo y también requiere autenticación. No existe un endpoint de chat.

Una respuesta correcta contiene un solo objeto `recommendation`, los datos reales, avisos y una explicación con plantillas. Declara `ranking: { "method": "catalog", "modelVersion": null }`. No devuelve probabilidad de satisfacción ni confianza del modelo.

## Ejecución y verificación

```powershell
npm.cmd --prefix backend run build
npm.cmd run typecheck
npm.cmd --prefix backend test -- --runInBand tests/aiRecommendations.test.js
```

La selección no requiere Python, claves de proveedores generativos ni variables `TRAIL_ML_*`. El arranque del servidor no inicia el antiguo worker y el endpoint no lo importa. Configurar un modelo antiguo no cambia las recomendaciones.

Para comprobar una base local existente se conservan `ranking:smoke` y `ranking:coverage`. El smoke usa HTTP y PostgreSQL locales, requiere una cuenta y catálogo previos y no escribe datos. `catalog:export` exporta atributos del catálogo; no crea etiquetas de relevancia.

El código anterior de ranking por valoraciones en `backend/ml/` se conserva como material histórico de investigación, desconectado de la API. Su entrenamiento, ausencia de etiquetas y métricas históricas no son requisitos ni resultados del recomendador actual. Se retiraron las herramientas de recolección de opiniones. Los modelos públicos de fatiga, AMS, OSM y APN pertenecen a tareas separadas y conservan su evaluación.
