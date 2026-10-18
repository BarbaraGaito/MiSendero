# Validación funcional de MiSendero — 17 de octubre de 2026

La campaña ejecutó **483 casos de producto: 482 aprobados y uno fallido**. El caso fallido corresponde a la duplicación de reportes cuando se repite una petición después de perder su confirmación. Los 15 escenarios solicitados cuentan con una ficha completa y aserciones automatizadas vinculadas: 14 tienen evidencia aprobada dentro de ese alcance y MF07 conserva el fallo observado. Las validaciones end-to-end, manuales y sobre dispositivos físicos están registradas como **no ejecutadas**.

La [estrategia](ESTRATEGIA.md) establece los niveles, las condiciones adversas y el protocolo físico. La [matriz completa](2026-10-17/final-seed-20261017/matrix.md) desarrolla por escenario ID, RF/RNF, objetivo, precondiciones, datos, pasos, resultado esperado, obtenido, evidencia, estado y observaciones. También se entrega en [CSV](2026-10-17/final-seed-20261017/matrix.csv) y [JSON](2026-10-17/final-seed-20261017/matrix.json).

## Ambiente y procedimiento

Se utilizó Windows x64 10.0.22621, Node.js 24.19.0 y npm 11.17.0. Las fechas de cada comando se registran en UTC; el calendario de la campaña corresponde a Buenos Aires. El cliente utiliza Expo 57.0.26, React 19.2.3, React Native 0.86.3, Jest 29.7.0, jest-expo 57.0.5 y React Test Renderer 19.2.3. El backend utiliza Jest 30.4.2, Supertest 7.2.2, pg-mem 3.0.14 y TypeScript 5.9.3. Las versiones instaladas coinciden con ambos lockfiles en las dos ejecuciones de referencia.

El [registro de entorno](2026-10-17/final-seed-20261017/environment.json) incluye revisión Git, cambios locales, versiones y hashes de lockfiles. El [registro de comandos](2026-10-17/final-seed-20261017/commands.json) conserva argumentos, directorios, marcas horarias y códigos de salida. La revisión base es `357d01883df8fce5d09ac02bcd3aee682487a82c`; los cambios locales se identifican mediante el manifiesto de fuentes. No se consultaron cuentas operativas ni se realizaron descargas, inferencias pagas o avisos externos reales.

Se ejecutaron comprobación de tipos, compilación del módulo de IA del backend, dos controles del agregador, las suites completas instrumentadas y la sonda de aceptación. Se repitió la campaña con las semillas **20261017 y 73**, mediante órdenes aleatorias y ejecución secuencial. Los resultados individuales y los cuatro contadores de cobertura coinciden entre ambas ejecuciones. El control de integridad compara además hashes de entradas y evidencias. Las duraciones y fechas de cada ensayo se conservan como mediciones de ejecución y no se exige que sean idénticas.

## Resultado por componente

| Conjunto | Suites | Casos | Aprobados | Fallidos | Omitidos en Jest |
|---|---:|---:|---:|---:|---:|
| Cliente y servicios móviles | 47 | 336 | 336 | 0 | 0 |
| Backend, API y gestión web | 17 | 146 | 146 | 0 | 0 |
| Sonda de aceptación de reintento de reportes | 1 | 1 | 0 | 1 | 0 |
| **Campaña de producto** | **65** | **483** | **482** | **1** | **0** |

La comprobación de tipos, la compilación del backend y los dos controles del agregador aprobaron. Estos controles de infraestructura se informan separadamente de los casos de producto. “Omitidos en Jest” no incluye los protocolos físicos y manuales, que no se lanzaron y figuran como no ejecutados en la matriz.

| Nivel | Resultado obtenido |
|---|---|
| Unitarias | Ejecutadas: validación de ubicación y lecturas, reglas y abstención de inferencia, entre otros contratos. Los dobles nativos están identificados por caso. |
| Integración | Ejecutadas: SQL real en SQLite de Node, recuperación entre procesos, pantallas con dependencias controladas y API con pg-mem. Incluye el fallo MF07. |
| End-to-end | No ejecutadas: no se inició una build instalada conectada al backend. |
| Manuales | No ejecutadas: el protocolo está definido y no contiene resultados de un operador. |
| Dispositivos físicos | No ejecutadas: no se utilizó teléfono, emulador o wearable en esta campaña. |
| Usabilidad y campo | No forman parte de la evidencia obtenida en esta ejecución. |

## Cobertura de código

La medición conserva los **145 archivos propios del cliente y 37 del backend** en el inventario JS/TS. La cobertura conjunta de líneas fue **5597/6373 = 87,82%**, sobre el objetivo interno del 85%. La suma utiliza contadores de líneas de inventarios disjuntos; no promedia porcentajes. El inventario incluye archivos no importados por las pruebas. No se modificó el alcance productivo para mejorar el porcentaje.

| Componente | Líneas cubiertas / ejecutables | Sentencias | Ramas | Funciones |
|---|---:|---:|---:|---:|
| Cliente | 4611/5265 — 87,57% | 83,86% | 73,76% | 77,36% |
| Backend | 986/1108 — 88,98% | 86,89% | 78,48% | 84,28% |
| **Conjunto** | **5597/6373 — 87,82%** | **84,40%** | **74,32%** | **78,30%** |

Los [contadores e inventario](2026-10-17/final-seed-20261017/coverage-summary.json) y la [tabla por archivo](2026-10-17/final-seed-20261017/coverage-modules.csv) corresponden a las suites convencionales instrumentadas. La sonda MF07 se ejecuta e informa separadamente; su fallo no desaparece por la cobertura alcanzada ni por las aprobaciones de otros casos. Las pruebas Python de investigación y la exactitud predictiva de modelos tienen procedimientos y denominadores propios.

## Comportamientos demostrados y brechas

La evidencia obtenida demuestra la conservación de estados locales ante cortes controlados, la distinción entre operación pendiente y confirmada, el filtrado de ubicaciones no utilizables y el aislamiento de cuentas. La prueba de recuperación utiliza escrituras confirmadas sobre un archivo SQLite: después de cerrar la conexión, otro proceso Node ejecuta los repositorios de lectura y recupera una sesión pausada, un punto con 8 metros acumulados, un reporte pendiente y los metadatos del mapa. No representa un reinicio nativo, un corte de energía ni una interrupción durante una transacción.

Los ensayos de espacio inyectan ENOSPC y comprueban que el mapa permanece incompleto y no se ofrece como utilizable. Los ensayos de batería presentan 15%, nivel desconocido y error de consulta sin fabricar un valor; los eventos de ciclo de vida comprueban retiro del watcher. El aviso visual de batería es informativo. No se midieron autonomía, consumo ni restricciones de segundo plano de un teléfono.

En SOS, las pruebas de pantalla conservan el evento pendiente sin invocar la API cuando la red está ausente. Una cancelación del compositor y un resultado `sent` del adaptador mantienen explícitamente la entrega sin confirmar. La API conserva la identidad del SOS al reintentar. Son resultados de contratos y estados; no acreditan recepción de un SMS por un contacto.

El fallo **MF07** muestra un límite concreto del efecto único en reportes. La sonda envía dos peticiones con el mismo contenido y fecha de observación; el servidor acepta ambas con HTTP 201 y conserva **dos filas, IDs 1 y 2**, frente a la única fila esperada. La primera respuesta se descarta conceptualmente para representar que el cliente perdió su acuse después del commit. La [salida de la sonda](2026-10-17/final-seed-20261017/acceptance-probe.txt) y su [resultado Jest](2026-10-17/final-seed-20261017/probe-results.json) conservan el conteo real y la aserción fallida. El resultado se reproduce con la segunda semilla. La cola local y la idempotencia de SOS no acreditan por sí solas idempotencia remota de reportes.

Las correcciones, retiros y vencimientos se comprueban mediante reemplazo de la copia local por la respuesta vigente del servidor y controles de autorización. La carrera de ediciones entre dos instalaciones no se ejecutó. Las muestras fisiológicas son fixtures con datos faltantes, antiguos, futuros o inválidos; los puentes HealthKit y Health Connect están sustituidos. El error del servicio de recomendación deja operativos el mapa local y el registro GPS entre servicios, mientras que la inferencia devuelve abstención para entradas no evaluables o modelos no habilitados. Estos ensayos no acreditan un wearable físico, una evaluación clínica, exactitud predictiva ni continuidad de una sesión nativa completa ante cualquier excepción interna.

La eliminación de cuenta está implementada y posee pruebas locales y de API sobre contraseña, revocación, limpieza de registros y suspensión de envíos ante respuesta incierta. Se vincula con RF-14.1, RF-14.2 y RNF-02/RNF-07; el catálogo funcional no asigna un RF específico a la baja. No se acredita borrado físico de backups o servicios externos.

## Decisiones y alcance académico

Se adoptaron estados de aceptación observables por entidad y nivel. MF07 conserva como resultado esperado un único efecto remoto y como resultado obtenido el fallo de duplicación. El comando funcional retorna código 1 por ese caso; la sonda no se omite ni convierte su fallo en una aprobación. Los datos de prueba se aíslan y el entorno fija las dependencias y el reloj cuando su valor determina la lógica. La segunda ejecución cambia el orden de los casos y conserva las mismas decisiones de aceptación.

La distinción entre guardado local, aceptación HTTP y entrega al contacto permite interpretar las emergencias sin atribuir confirmaciones externas inexistentes. La recuperación entre procesos aporta evidencia sobre escrituras confirmadas en SQLite bajo el adaptador utilizado. El reemplazo de reportes usa el servidor como estado de referencia de la lectura actualizada; no se atribuye una fusión de ediciones concurrentes. La batería desconocida se representa explícitamente y la retirada del watcher en segundo plano corresponde al comportamiento definido por RNF-06.

Las condiciones de dispositivo conservan su protocolo y estado no ejecutado: reinicio del teléfono, interruptor GPS y permisos reales, precisión en terreno, tiles sobre filesystem nativo, almacenamiento agotado, restricciones de batería, entrega de SMS y lecturas de wearables. No se dispuso de una herramienta de conexión Android o emulador en PATH ni en las ubicaciones habituales consultadas; no se inició una build nativa. La evidencia describe los componentes efectivamente ejecutados. La ausencia de una observación física no se transforma en aprobación por inferencia.

## Cambios y reproducción

Se implementaron cuatro pruebas nuevas de integración de servicios/SQLite, tres variantes de batería y dos variantes de SOS offline. Se agregó la sonda de aceptación MF07, el catálogo de escenarios, el ejecutor de campaña y el verificador de evidencias. Las pruebas de batería y SOS restablecen sus respuestas por caso y desmontan las pantallas. La suite de preparación reserva 30 segundos para la inicialización bajo instrumentación y garantiza desmontaje al finalizar cada caso, conservando sus aserciones funcionales. El caso de recuperación crea y elimina un archivo temporal exclusivo. Se agregó `test:functional` a los scripts y una exclusión puntual para archivos temporales de trabajo. No se modificó lógica de producción, el inventario de cobertura ni los resultados esperados de las pruebas existentes.

```powershell
npm.cmd run test:functional -- --output=validation/functional/mi-ejecucion --seed=20261017
npm.cmd run test:functional -- --output=validation/functional/mi-repeticion --seed=73
node testing/functional/verify.cjs validation/functional/mi-ejecucion validation/functional/mi-repeticion
```

Los dos primeros comandos terminan con **código 1 por MF07**. El verificador comprueba integridad y repetición de resultados; su aprobación no redefine el resultado funcional. Los [manifiestos de evidencias](2026-10-17/final-seed-20261017/evidence-manifest.json) y de [fuentes](2026-10-17/final-seed-20261017/source-manifest.json) permiten comprobar los archivos evaluados y los resultados retenidos. La [segunda ejecución](2026-10-17/final-seed-73/summary.json) conserva sus propias marcas horarias y evidencias. La redacción de la sección 4.4 se entrega también como [fuente LaTeX](4.4-pruebas-funcionales.tex).
