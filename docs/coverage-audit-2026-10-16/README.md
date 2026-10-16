# Auditoría de cobertura de MiSendero — 16/10/2026

**Resultado: 5357/6123 líneas del producto JavaScript/TypeScript, 87,49 %.** Supera el umbral de líneas de RNF-11, con inventario completo y sin reducir el denominador. No acredita un 85 % de sentencias, ramas o funciones. El criterio docente debe confirmarse si la devolución original no especifica el indicador.

| Componente | Archivos inventariados | Suites / casos aprobados | Líneas | Sentencias | Ramas | Funciones |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cliente | 141 | 44 / 308 | 4539/5190 · **87,45 %** | 4931/5893 · 83,67 % | 3233/4422 · 73,11 % | 1015/1318 · 77,01 % |
| Backend, API y script web | 31 | 16 / 114 | 818/933 · **87,67 %** | 914/1069 · 85,50 % | 357/468 · 76,28 % | 136/166 · 81,92 % |
| **Producto JS/TS conjunto** | **172** | **60 / 422** | **5357/6123 · 87,49 %** | **5845/6962 · 83,96 %** | **3590/4890 · 73,42 %** | **1151/1484 · 77,56 %** |

Hay además **2 pruebas del agregador** con `node:test`, separadas del recuento del producto. Pasan las **14 pruebas unittest de investigación Python**, cuyo informe independiente muestra **485/696 líneas (69,68 %), 196/301 ramas (65,12 %) y 68,30 % combinado de coverage.py**. Python no alcanza el 85 %. No se suma a JS/TS porque pertenece a la investigación y usa otra instrumentación y otra definición de ramas. El 87,49 % no se presenta como cobertura de todos los lenguajes del repositorio.

## Evidencia entregada

- [Tabla por archivo, cuatro indicadores y SHA-256](modules.csv).
- [Contadores, grupos, inventario completo y hashes de fuentes](summary.json).
- [Entorno final y cotejo de versiones instaladas con el lockfile](environment.json).
- [Comparación de ejecuciones](executions.json).
- [Líneas no ejecutadas por archivo](uncovered-lines.csv).
- [Medición inicial con alcance completo](baseline-summary.json).
- [Redacción académica aplicada a la sección 4.4](section-4.4.tex) y [verificación del cambio acotado](thesis-edit.json).
- [Paquete de reportes originales HTML, LCOV, JSON y resultados de pruebas](coverage-evidence.zip). Extraerlo y abrir `final/index.html`; los informes por componente señalan el código cubierto y no cubierto. Contiene también las mediciones iniciales, la repetición y Python.
- [Manifiesto SHA-256 de fuentes, pruebas, configuración y evidencias](manifest.json).

Los reportes abiertos directamente desde este workspace están en [coverage/final/index.html](../../coverage/final/index.html) y [coverage/python/html/index.html](../../coverage/python/html/index.html). Estos directorios se regeneran; la copia comprimida conserva la evidencia de esta revisión.

## Qué se midió y por qué

La tesis define **RNF-11** en `tables/requirements_rnf.tex` como al menos 85 % conjunto de líneas ejecutables del código propio. `tables/requirements_nfr_measurement.tex` prescribe sumar líneas cubiertas y ejecutables, incluir archivos no importados y justificar exclusiones. Se usa esa definición interna. No se localizó la devolución docente original; corresponde confirmar formalmente si requiere líneas, sentencias, ramas, cada componente por separado u otro universo. Si exigiera 85 % conjunto de ramas, funciones o sentencias, estos resultados **no lo satisfacen**. En esta ejecución, ambos componentes también superan individualmente el 85 % de líneas, aunque el control automático implementa el criterio conjunto documentado en RNF-11.

La fórmula es `100 × (4539 + 818) / (5190 + 933)`. No se promedian porcentajes. Los inventarios son disjuntos: los módulos de `backend/src/data` importados por el cliente se cuentan solamente en backend. El proveedor es Babel/Istanbul en ambos proyectos, sobre líneas de fuente; las versiones de sus bibliotecas se conservan en el registro de entorno. La agregación suma contadores y es comparable bajo esta definición, aunque los proyectos usen distintas versiones de Jest.

Se informan las cuatro métricas: líneas ejecutadas al menos una vez, sentencias ejecutadas, alternativas de ramas ejercitadas y funciones invocadas. Ninguna indica por sí sola calidad de las aserciones, corrección de todos los escenarios ni seguridad del sistema. Los archivos de interfaces o reexportación que Babel considera sin instrucciones aportan `0/0`; la convención de visualización de Istanbul es 100 %, pero no agregan líneas cubiertas al numerador ni al denominador.

## Estructura y alcance real

| Área | Stack y configuración | Alcance instrumentado |
| --- | --- | --- |
| Cliente | Expo 57.0.26, React 19.2.3, React Native 0.86.3; Jest 29.7.0, jest-expo 57.0.5, React Test Renderer 19.2.3; `jest.config.js` | `app`, `mobile`, `services`, `database`, `ai`, `types`, `scripts`, `app.config.js`, `metro.config.js` |
| Backend | Node.js/Express; Jest 30.4.2, Supertest 7.2.2, pg-mem 3.0.14; `backend/jest.config.js` | Todo JS propio de `backend/src` y `backend/scripts`, incluidos página web de cuentas y utilitarios de mantenimiento |
| Investigación | Python 3.12.14, unittest, coverage.py 7.6.1; `testing/python-coverage.ini` | Todos los `.py` de `training/python`, incluidos módulos no importados; se excluyen únicamente `test_*.py` |
| Instrumentación de pruebas | `node:test`; `testing/coverage-tools.test.cjs` | Verifica el cálculo y el control de aceptación; no se usa para inflar cobertura de producción |

`testing/coverage-scope.cjs` enumera recursivamente archivos propios, con independencia de las importaciones de los tests. `collectCoverageFrom` instrumenta también los no ejecutados. El agregador falla si falta algún archivo del inventario o aparece otro fuera de él. Las pantallas sin tests, los scripts con 0 % y la configuración de arranque permanecen contabilizados.

Las siguientes categorías quedan fuera del denominador JS/TS por su naturaleza, no por su porcentaje:

| Categoría | Tratamiento y justificación |
| --- | --- |
| Tests, `__mocks__`, `testing`, configuración de Jest y de TypeScript | Infraestructura de evaluación; no son comportamiento de producción. Los dos tests de cálculo se reportan aparte. |
| `node_modules` | Código de terceros; versiones identificadas por lockfile y registro de entorno. |
| `.d.ts` | Declaraciones sin ejecución. Los `.ts` de tipos siguen en el inventario. |
| SQL de migraciones | No lo instrumenta Istanbul; se ejercita indirectamente con pg-mem. No se afirma cobertura de instrucciones SQL ni de PostgreSQL real. |
| JSON de catálogo, modelos y términos | Datos leídos por código instrumentado; no se convierten sus filas en líneas cubiertas. |
| Imágenes, fuentes, SVG, HTML y CSS | Recursos y presentación; el JS servido por la página web sí se instrumenta. No se afirma cobertura visual del DOM ni del navegador. |
| Documentación, reportes y directorios temporales | Artefactos derivados; `tmp` se excluye además del descubrimiento de tests para evitar ejecutar copias de pruebas. |
| Entrenamiento Python | Reporte completo y separado, incluido el código con 0 %; no se oculta su resultado inferior al umbral. |

## Línea de base, cambios y reproducción

La revisión de partida fue `c33b658b2556a089db7040e7c935796152848eb4`, sin cambios locales al comenzar. La cifra histórica de 54 + 39 = 93 no describe esa revisión. La sección 4.4 disponible al iniciar contenía a su vez 173 + 86 = 259 y una declaración de 85 % sin evidencia vinculada. El conjunto encontrado y ejecutado antes de tocar pruebas fue **185 + 93 = 278**; todos aprobaron. Se conserva su salida JSON.

| Etapa | Cliente: líneas | Backend: líneas | Conjunto | Resultado de tests |
| --- | ---: | ---: | ---: | --- |
| Configuración previa, sólo archivos importados | 2116/2528 · 83,70 % | 662/806 · 82,13 % | No se usa: alcance incompleto y solapado | 185 + 93 aprobados |
| Inventario completo, casos originales | 2082/5190 · 40,11 % | 662/933 · 70,95 % | 2744/6123 · **44,81 %** | 185 + 93 aprobados; control de cobertura falla |
| Pruebas ampliadas, instalación limpia y versiones bloqueadas | 4539/5190 · 87,45 % | 818/933 · 87,67 % | 5357/6123 · **87,49 %** | 308 + 114 aprobados; control pasa |

Se cubrieron **2613 líneas adicionales**, manteniendo **6123 líneas** en el denominador. Se agregaron **123 casos del cliente y 21 del backend**. No se eliminaron pruebas, no se rebajaron expectativas, no se introdujeron pruebas de mera existencia de módulos ni directivas `istanbul ignore`.

Cambios principales:

1. Instrumentación completa por proyecto y reportes HTML, JSON, LCOV y CSV; agregación ponderada y control de 85 % con contadores exactos, sin aceptar un redondeo de 84,999 %.
2. Pruebas de permisos y filtros GPS; ciclo de eventos y limpieza de coordinadores; persistencia SQLite de sesiones, reseñas y planes por cuenta.
3. Pruebas de contratos HTTP, errores de API y cancelación por timeout; pantallas de autenticación, consentimiento, perfil, planes, reportes, navegación y catálogos.
4. Pruebas de descarga y verificación offline, paquetes incompletos, cancelación y errores locales; selección en mapas, gestos, geometría y liberación de recursos Three.js, altimetría y accesibilidad del selector de puntos.
5. Contratos iOS/Android de datos fisiológicos, coherencia temporal de lecturas, ausencia de permisos y separación del simulador.
6. Pruebas de gestión web de cuentas y moderación; validación de licencias de fotografías, mantenimiento de elevaciones, pronóstico y umbrales meteorológicos; adaptador real del webhook con transporte controlado e idempotencia.
7. Aislamiento de fixtures en cola, autenticación, actividades y senderos. Se amplió sólo el presupuesto del limitador de autenticación del entorno de tests para que los fixtures no consuman un límite compartido.
8. Registro y cotejo de dependencias reales. La instalación inicial tenía Expo 54.0.36, React 19.1.0 y RN 0.81.5, frente al lockfile de Expo 57/React 19.2.3/RN 0.86.3. Se instalaron limpiamente los lockfiles con los comandos documentados y se preservó el entorno anterior en `tmp/coverage-original-environment/`. **Los lockfiles no se cambiaron.**
9. Un ajuste de compatibilidad en `HomeScreen.tsx`: se expresaron las posiciones absolutas de la sombra sin usar `StyleSheet.absoluteFillObject`, ausente en los tipos de RN 0.86.3. El aspecto y los contadores de líneas permanecieron iguales. `tsc --noEmit` pasa con las dependencias bloqueadas.
10. Actualización de CI: mismo comando de cobertura, Node 24.19.0, evidencias aun ante fallos y LCOV con rutas normalizadas para Sonar. CI remoto y Sonar no se ejecutaron desde esta sesión; su resultado futuro requiere el workflow correspondiente.

### Comandos principales

Desde la raíz, con Node 24.19.0 y npm 11.17.0:

```powershell
npm.cmd ci --legacy-peer-deps --ignore-scripts
npm.cmd ci --prefix backend --ignore-scripts
npm.cmd run typecheck
npm.cmd run test:coverage -- --output=coverage/final --randomize --seed=20261016 --showSeed
```

En Unix se utiliza `npm` en lugar de `npm.cmd`. El runner usa UTC para ambos procesos. La instalación limpia se comprobó primero en una copia aislada y luego sus dependencias se utilizaron en el workspace principal. `npm ci` sin `--legacy-peer-deps` falla por pares opcionales faltantes; intentar resolverlos de nuevo genera conflictos de pares de Expo. No se presenta ese procedimiento de instalación de tests como validación de una build nativa. La [documentación de npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/) exige conservar las opciones que afectan el grafo del lockfile.

Repetición con otro orden y dos workers:

```powershell
$env:TZ='UTC'
npm.cmd test -- --coverage --maxWorkers=2 --randomize --seed=73 --showSeed --json --outputFile=coverage/repeat/client/test-results.json --coverageDirectory=coverage/repeat/client
npm.cmd --prefix backend test -- --coverage --maxWorkers=2 --randomize --seed=73 --showSeed --json --outputFile=../coverage/repeat/backend/test-results.json --coverageDirectory=../coverage/repeat/backend
node testing/summarize-coverage.cjs coverage/repeat
```

Python, con el entorno y los datos de investigación del repositorio disponibles:

```powershell
.\.venv-ai\Scripts\python.exe -m pip install -r testing/requirements-coverage.txt
npm.cmd run test:coverage:python
```

El entorno Python requiere además `training/python/requirements-public.lock.txt` y los archivos de evidencia que validan las pruebas. El runner fija `PYTHONHASHSEED=0`, escribe JSON, XML, HTML y `execution.log`. Los comandos no reentrenan ni reemplazan los modelos. El instrumento combinado de coverage.py cuenta oportunidades de líneas y ramas; por eso su 68,30 % no debe confundirse con el 69,68 % de líneas.

## Independencia y determinismo

El primer control de orden, semilla 20261016, encontró **un fallo del cliente y seis del backend** en pruebas preexistentes. El resumen de cola esperaba estados creados por un test anterior; autenticación requería usuarios registrados antes; actividades y catálogo conservaban inserciones ajenas. Se pasó a preparar o limpiar esos datos en cada caso, manteniendo sus expectativas. Las salidas originales se conservan en el archivo de evidencias.

Tras el aislamiento, se comprobaron la ejecución principal secuencial y la repetición con semilla 73/dos workers. Pasaron los mismos 422 casos y coincidieron exactamente los cuatro contadores agregados. La instalación limpia reprodujo los resultados. Las pruebas nuevas fijan el reloj cuando interviene en la lógica, simulan el transporte y los límites nativos, limpian registros y efectos, y utilizan almacenamiento en memoria por entorno de test. Los identificadores y secretos aleatorios de fixtures de backend no participan en expectativas concretas ni sustituyen una semilla de orden.

Esto acredita repetibilidad en las ejecuciones conservadas, no una garantía universal de determinismo. El informe identifica el código mediante hashes y una revisión base más cambios locales; no atribuye los nuevos casos a un commit que todavía no existe.

## Brechas y próximas pruebas útiles

Quedan **766 líneas JS/TS sin ejecutar**. [uncovered-lines.csv](uncovered-lines.csv) conserva la lista exacta, sin ocultar módulos con 0 %.

| Ruta crítica | Evidencia automatizada actual | Brecha y siguiente comprobación |
| --- | --- | --- |
| Offline | SQLite real en memoria, tiles/caché a través de mocks de archivos; descarga incompleta, cancelación, verificación al abrir y fallback local | Caída del proceso durante escritura, disco lleno en distintas fases, actualización de paquete mientras se usa y recuperación de copias dañadas en el sistema de archivos real |
| Sincronización | Cola, propiedad por cuenta, reintentos, idempotencia, cambio de red y primer plano, suspensión durante baja | Terminación entre confirmación remota y commit local, reconexión prolongada y concurrencia entre instalaciones contra API y PostgreSQL reales |
| Ubicación | Permisos denegados, eventos, precisión/antigüedad/orden/velocidad, distancia persistida, aviso de desvío | `AlertRouteScreen.tsx` sigue en 0 % (31 líneas); recuperación hasta retomar ruta, pérdida de señal y restricciones del sistema en campo |
| Persistencia | Sesiones, reseñas, planes y propiedad por usuario; APIs con pg-mem | Reinicio completo de la app, migraciones y transacciones con PostgreSQL real; fallos adicionales en borrado/actualización offline |
| Autenticación | Registro/login, términos independientes, errores HTTP, revocación/baja y página web con DOM controlado | Arranque `app/index.tsx` y layout siguen sin ejecutar (23 líneas); carrera de rehidratación, SecureStore y biometría/llavero reales; DOM/navegador E2E |
| Emergencias | SOS local y simulado, planes/check-in, webhook con deduplicación y reintentos; distingue pendiente/aceptado | Proveedor real, entrega al contacto, permisos SMS, reinicios y comprobación operativa. No se acredita rescate ni asistencia por un HTTP 2xx |
| Mapas y wearable | Geometrías y gestos reales con GPU/puentes nativos controlados; rechazo de DEM ausente, lectura no autorizada o fuera de ventana | GPU y rendimiento, batería, HealthKit/Health Connect físicos, continuidad en segundo plano y revocación del sistema |
| Herramientas y presentación | Scripts de fotos/elevación parcialmente cubiertos; interfaces incluidas en el denominador | `scripts/train-ai.js`, `scripts/license-inventory.js`, arranque Metro y varias pantallas informativas sin tests; probar contratos de ejecución y salida en próximos cambios, con prioridad menor que errores críticos |
| Investigación Python | 14 tests de particiones, fuentes, privacidad, raster y evidencia de evaluación; todos los módulos en el informe | Pipeline de descarga/preparación, exportación y entrenamiento presentan brechas sustanciales. No se declara 85 % para investigación |

La cobertura automatizada aquí reportada se separa de **E2E**, **dispositivo**, **usabilidad**, **rendimiento en campo**, **precisión predictiva** y **compatibilidad del binario publicado**. No se ejecutaron nuevas validaciones de esas categorías. Que un puente nativo esté simulado o que una geometría sea correcta en CPU no acredita lectura física de sensores ni renderizado GPU.

## Fuentes metodológicas

La evidencia numérica proviene de los archivos instrumentados locales. Para el comportamiento de las herramientas se consultaron fuentes primarias: [Jest: collectCoverageFrom](https://jestjs.io/docs/29.7/configuration#collectcoveragefrom-array), [Jest: coverageThreshold](https://jestjs.io/docs/configuration#coveragethreshold-object), [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/) y [coverage.py: cobertura de ramas](https://coverage.readthedocs.io/en/7.6.1/branch.html).
