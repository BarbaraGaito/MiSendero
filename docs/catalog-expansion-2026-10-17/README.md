# Ampliación del catálogo: 20 senderos reales

Revisión de fuentes: **17 de octubre de 2026**. Carga aplicada únicamente a PostgreSQL local: **32 → 52 registros**, sin modificar los 32 anteriores. Ver [evidencia de la transacción](local-import.json). No se conectó ni se modificó Amazon RDS.

## Recorridos incorporados

Las distancias de la tabla son las del itinerario completo indicado. «Travesía» significa que el regreso requiere otra caminata o transporte; el regreso no está incluido. Los dos circuitos de Península Belgrano tienen la misma cabecera, pero trazados distintos. La ruta sur del Lanín es diferente de la ruta norte al Refugio BIM ya existente.

| Sendero | Provincia | km | Tiempo de marcha | Dificultad normalizada | Itinerario | Fuente |
|---|---|---:|---|---|---|---|
| Che Roga | Corrientes | 4,4 | 2 h 30 min | Media | Ida y vuelta | A |
| Histórico Tapé Porá | Corrientes | 1 | 1 h | Baja | Ida y vuelta | A |
| La Chuña | Salta | 4 | 2 h | Baja | Ida y vuelta | B |
| Laguna Los Patitos | Salta | 3 | 1 h 30 min | Baja | Ida y vuelta, a pie | B |
| Piedra Movediza | La Pampa | 2,4 | 2 h | Media | Ida y vuelta, guía obligatorio | C |
| Farallones | San Luis | 9 | 4 h | Alta | Ida y vuelta, guía obligatorio | D |
| Cerro Leoncito | San Juan | 8 | 3 h | Alta¹ | Ida y vuelta | E |
| Pampa Alta | Tierra del Fuego | 4,7 | 2 h | Media | Travesía Ensenada–Pipo | F |
| Cerro Alto El Petiso | Chubut | 16 | 7 h | Alta | Ida y vuelta, guía obligatorio | G |
| Laguna Escondida | Chubut | 6² | 3 h 30 min | Media | Ida y vuelta | G |
| Cascada Arroyo del Hacha | Chubut | 2² | 1 h | Media | Ida y vuelta | G |
| Cerro Cocinero | Chubut | 16² | 6 h | Alta | Ida y vuelta | G |
| Cerro Llao Llao desde Villa Tacul | Río Negro | 5² | 2 h | Baja³ | Ida y vuelta desde Villa Tacul | H, M |
| Secretos bajo nuestros pies | Córdoba | 1,056 | 1 h | Baja | Ida y vuelta desde Estacionamiento 1 | I |
| Puesto Los Chorizos | Tucumán | 9² | 3 h⁴ | Baja | Ida y vuelta desde Santa Rosa | J |
| El Pozón | Tucumán | 0,404² | 30 min⁴ | Baja | Ida y vuelta desde camping Santa Rosa | J |
| Península Belgrano, Circuito Chico | Santa Cruz | 9,6 | 3–4 h | Media | Circuito | K |
| Península Belgrano, Circuito Grande | Santa Cruz | 16,8 | 5–6 h | Alta | Circuito | K |
| Puerto Canoa–Cara Sur del Volcán Lanín | Neuquén | 20 | 9 h⁵ | Alta | Ida y vuelta | L |
| Laguna Rosales–San Martín de los Andes | Neuquén | 14 | 4 h⁵ | Baja | Travesía | L |

1. APN publica «media/alta». Se conserva ese valor en `provenance.native.difficulty` y se normaliza como Alta por criterio conservador. «Moderada» se normaliza como Media.
2. Distancia total calculada duplicando la distancia de ida publicada. El dato nativo, su alcance y la conversión permanecen registrados; no se presenta como distancia medida por GPS.
3. La fuente la clasifica como Baja, con advertencia de exigencia media según estado físico. No se confunden las variantes de Villa Tacul y Puerto Pañuelo.
4. **Estimaciones derivadas**, no tiempos totales oficiales: APN publica respectivamente 90 y 15 minutos de ida. Se duplican para planificar el retorno y se marcan con `duration_is_derived: true`. La descripción y las precauciones lo explican. Para entrenamiento/evaluación sobre tiempos medidos deben excluirse o tratarse como estimaciones; no como etiquetas observadas.
5. El Circuito Andino publica tiempo neto de caminata sin descansos. Para las demás fuentes tampoco se asume que estén incluidos descansos, traslados o trámites.

Los rangos oficiales se conservan como rangos. El recomendador usa el extremo superior como referencia conservadora y exige que ambos extremos estén dentro del intervalo pedido: 3–4 h no se ofrece como coincidencia del filtro 4–6 h.

## Fuentes consultadas

- A: [Administración de Parques Nacionales, Mburucuyá](https://www.argentina.gob.ar/node/150096).
- B: [APN, El Rey](https://www.argentina.gob.ar/parquesnacionales/region-noroeste/parque-nacional-el-rey/actividades).
- C: [APN, Lihué Calel](https://www.argentina.gob.ar/parquesnacionales/regionpatagonia/parque-nacional-lihue-calel/actividades).
- D: [APN, Sierra de las Quijadas](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-sierra-de-las-quijadas/actividades).
- E: [APN, El Leoncito](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-el-leoncito/actividades).
- F: [APN, senderos de Tierra del Fuego](https://www.argentina.gob.ar/parquesnacionales/patagonia-austral/senderos-del-parque-nacional-tierra-del-fuego).
- G: [APN, Los Alerces](https://www.argentina.gob.ar/parquesnacionales/regionpatagonia/parque-nacional-los-alerces/actividades).
- H: [Bariloche Trekking, Cerro Llao Llao](https://barilochetrekking.com/sendero-mb2/), ficha técnica con variante Villa Tacul y apoyo cartográfico del Club Andino Bariloche. El sitio oficial de turismo municipal remite a estas fichas técnicas.
- I: [APN, Quebrada del Condorito](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-quebrada-del-condorito/actividades).
- J: [APN, Aconquija](https://www.argentina.gob.ar/parquesnacionales/region-noroeste/parque-nacional-aconquija/actividades).
- K: [APN, Perito Moreno](https://www.argentina.gob.ar/parquesnacionales/patagonia-austral/parque-nacional-perito-moreno/actividades).
- L: [Ente Oficial de Turismo Patagonia Argentina, Circuito Andino](https://patagonia.gob.ar/senderos/circuito-andino/), etapas 8 y 16.
- M: [Turismo de Bariloche, Trekking](https://www.barilocheturismo.gob.ar/es/aventura-trekking), descripción del bosque de Cerro Llao Llao. Los tiempos municipales de otras variantes no se trasladan a Villa Tacul. Esta fuente complementaria se anexó a la ficha local mediante [operación auditable](appendReviewedSource.cjs).

La revisión acredita el origen documental de los atributos, **no la apertura ni la seguridad actual**. Consultar siempre al administrador sobre habilitación, registro, guía, accesibilidad y condiciones vigentes.

## Datos que quedan sin completar

Los 20 registros incluyen nombre, ubicación/área, provincia, descripción, distancia, duración y alcance, dificultad nativa/normalizada, paisajes documentados, URL, sección de la fuente, fecha de revisión y precauciones. Los requisitos de guía se conservan donde la fuente los informa. `not_documented` y `null` significan desconocido, no ausencia de un requisito.

No se inventaron trazas, coordenadas iniciales, fotografías ni desnivel positivo acumulado. Todos quedan `null`. Un «desnivel» genérico o una altitud publicada no se transforma en ascenso acumulado. El detalle de la app muestra la ficha y sus fuentes; no habilita mapa, descarga de mapa ni altimetría para registros sin traza verificada. No se agregan perfiles de parques con datos de acceso o teléfonos supuestos.

## Carga y comprobación local

Desde la raíz del repositorio, con `backend/.env` apuntando al PostgreSQL local existente:

```powershell
npm --prefix backend ci --ignore-scripts
npm --prefix backend run db:catalog:preview
npm --prefix backend run db:catalog:apply
npm --prefix backend run catalog:export
npm --prefix backend test -- --runInBand catalogExpansion.test.js
npm --prefix backend run build
```

No ejecutar `db:seed` ni migraciones para cargar esta ampliación. El esquema existente ya permite los campos documentados en `provenance`.

El importador ejecuta una transacción, bloquea la tabla durante la carga, valida las 20 fichas, compara claves/nombres/alias normalizados y utiliza `ON CONFLICT DO NOTHING`. Verifica un SHA-256 de **todas las columnas de los registros anteriores** antes de confirmar. Si algo falla, revierte la transacción. Repetirlo no sobrescribe fichas existentes ni crea copias. No requiere que la base tenga exactamente 32 registros: esa era la cantidad auditada localmente, no una condición del código.

El CLI comprueba que la conexión sea a `localhost`, `127.0.0.1` o `::1`; rechaza hosts remotos, incluso en simulación. No se cambió la URL de la aplicación, que continúa apuntando a AWS. **Los nuevos registros no aparecerán en esa app hasta efectuar una carga explícita y revisada en RDS.** Esta entrega no realiza esa operación ni altera `misendero.service`, Nginx o credenciales de producción.

## Uso posterior en Machine Learning

`npm --prefix backend run catalog:export` genera `training/data/catalog/misendero-catalog.jsonl` desde PostgreSQL local, no desde ejemplos inventados. Incluye los 52 registros presentes, sus IDs locales, procedencia, valores faltantes, alcance de tiempos y conversiones. Los IDs pueden variar en otra base; para las nuevas fichas usar `catalog_key` como identidad transportable.

El lote nuevo está en `backend/src/data/catalogExpansion20261017.js`; se identifica con `catalog_batch: catalog-2026-10-17`. La exportación conserva también los registros anteriores: algunos carecen de documentación o de características estructuradas; esos campos permanecen nulos y **no deben tratarse automáticamente como datos verificados**. Filtrar/calificar por procedencia al construir un dataset.

Estos son **datos de características**, no un dataset supervisado de preferencias y elecciones. `relevance_label` es `null` en todos los casos; `synthetic` es `false`. No se entrenó un recomendador con esta carga ni se calcularon métricas de precisión. Todavía hacen falta consultas/preferencias y evaluaciones de relevancia o elecciones reales obtenidas con consentimiento, además de un protocolo de separación por consulta/usuario para evaluar sin fuga de información.

No asociar artificialmente la dificultad publicada con una etiqueta de satisfacción del usuario. Los circuitos que comparten tramos, como Península Belgrano, deben considerarse al separar datos para evitar una evaluación demasiado optimista.

## Archivos de esta ampliación

- `backend/src/data/catalogExpansion20261017.js`: fichas documentadas y conversiones reproducibles.
- `backend/scripts/importCatalogExpansion.js`: validación, deduplicación e importación local explícita.
- `backend/scripts/exportCatalogFeatures.js`: exportación de características sin información personal.
- `backend/tests/catalogExpansion.test.js`: pruebas del lote y del importador.
- `backend/package.json`: comandos de simulación, carga y exportación.
- `backend/src/ai/catalog.ts`: fuentes aceptadas, lectura de rangos y filtrado conservador de duración.
- `types/index.ts` y `mobile/screens/TrailDetail.tsx`: circuitos, fuentes y ficha sin GPS.
- `training/data/catalog/misendero-catalog.jsonl`: catálogo exportado para la preparación posterior del dataset.

Al finalizar esta ampliación, la sustitución de OpenAI seguía pendiente. Posteriormente se completaron la integración sin proveedores generativos y el pipeline supervisado; su estado actual está en [la auditoría del recomendador](../trail-ranking-2026-10-17/README.md). El entrenamiento personalizado sigue pendiente de etiquetas reales suficientes.

## Verificación realizada

- PostgreSQL local: carga de 20 registros, 32 anteriores intactos; repetición de carga con 0 inserciones y 20 coincidencias existentes.
- `catalogExpansion.test.js`: 32 pruebas aprobadas, incluyendo importación sobre el esquema real en pg-mem, alias con acentos, idempotencia, datos faltantes y rollback ante errores.
- Backend sin `aiRecommendations.test.js`: 17 suites / 146 pruebas aprobadas. Comprobación posterior de catálogo, trazas anteriores y API de senderos: 3 suites / 71 pruebas aprobadas.
- Aplicación: 46 suites / 327 pruebas aprobadas en la revisión general. Después se agregó y ejecutó la prueba de ficha sin GPS junto con el resto de `catalogueScreens.test.tsx`: 13 pruebas aprobadas.
- `npm --prefix backend run build` y `npm run typecheck`: aprobados.
- **Resultado histórico de esta etapa**: la suite antigua `aiRecommendations.test.js` tuvo 21 aprobadas y 11 fallidas porque aún esperaba OpenAI o el contrato anterior sin experiencia. En la implementación posterior se adaptó al recomendador local y se agregaron pruebas del worker: el backend completo pasó 185 pruebas. Los resultados iniciales de esta sección corresponden a la ampliación del catálogo, no al estado final de la integración.
