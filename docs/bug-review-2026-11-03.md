# Revisión de bugs — 3 de noviembre de 2026

Se revisaron el arranque y la navegación, autenticación y cambios de cuenta, recorridos y GPS, finalización de actividades, mapas offline, reportes y sincronización, planes de regreso, SOS, preferencias y privacidad, catálogo y recomendaciones. La revisión combinó lectura de código, pruebas de pantallas con React Test Renderer, SQLite, Express/Supertest y pg-mem, y pruebas del módulo Python de ranking.

Se confirmaron y corrigieron seis problemas. Las pruebas de regresión nuevas fallaron con el código anterior y pasaron después de las correcciones.

| Problema | Reproducción e impacto anterior | Corrección |
| --- | --- | --- |
| GPS: pérdida del punto válido posterior a un salto | Tras una posición válida, un salto imposible se descartaba, pero se conservaba como referencia. La siguiente posición correcta también se descartaba y se perdía distancia real. | La referencia avanza únicamente después de validar y guardar el punto. [Código](../services/RouteTrackingCoordinator.tsx), [pruebas](../services/__tests__/coordinators.test.tsx). |
| GPS: seguimiento detenido tras un error transitorio | Si fallaba el inicio del observador nativo, el coordinador dejaba la ruta marcada como observada. Las actualizaciones posteriores nunca reintentaban el inicio. | Se libera esa marca al fallar, permitiendo reintentar en la próxima actualización. [Código](../services/RouteTrackingCoordinator.tsx), [pruebas](../services/__tests__/coordinators.test.tsx). |
| Finalización: carga infinita y confirmación incorrecta | Un error al guardar la actividad producía una promesa rechazada sin manejar. La pantalla seguía cargando y mostraba «Guardamos tu actividad». | Se informa el fallo, se oculta la confirmación y se permite reintentar con la misma identidad de recorrido. También se descartan respuestas de una pantalla que dejó de estar vigente. [Código](../mobile/screens/RouteCompletedScreen.tsx), [pruebas](../mobile/screens/__tests__/RouteCompletedScreen.test.tsx). |
| Actividades: conflicto de identidad por precisión numérica | La comparación exacta entre números de JavaScript y columnas PostgreSQL `REAL` podía devolver HTTP 409 para una actividad válida, incluso después de insertarla. Las coordenadas GPS con muchos decimales reproducen el problema. | Los valores de columnas `REAL` se comparan con precisión float32. Un cambio real en los datos sigue devolviendo 409. La prueba emula la precisión de PostgreSQL porque pg-mem conserva números de doble precisión. [Código](../backend/src/routes/activities.routes.js), [pruebas](../backend/tests/activities.test.js). |
| Actividades: fechas inválidas llegaban a la base | Cadenas como `not-a-date` o `2026-02-30T12:00:00Z` superaban la validación y terminaban en HTTP 500. | Se exigen fechas ISO válidas; se admiten desplazamientos horarios explícitos. Las solicitudes inválidas devuelven HTTP 400 antes de insertar. [Código](../backend/src/schemas/activities.schemas.js), [pruebas](../backend/tests/activities.test.js). |
| Mapas offline: borrar una descarga dañaba otras | Los tiles y los mapas básicos se comparten en el teléfono. Borrar una ruta eliminaba archivos que aún necesitaban otra ruta cercana o una descarga de otra cuenta. | Se consultan las descargas restantes de todas las cuentas y se conservan los archivos compartidos. Se siguen eliminando los archivos exclusivos y los que ya no tienen referencias. [Borrado](../services/offlineMaps.ts), [caché](../services/mapTileCache.ts), [pruebas de tiles](../services/__tests__/mapTileCache.test.ts), [pruebas de almacenamiento](../services/__tests__/offlineElevation.test.ts). |

La evidencia local de las regresiones anteriores y posteriores está en `reports/bug-review-2026-11-03/`. Los resultados completos de cobertura están en `coverage/bug-review-2026-11-03/`. Son directorios de evidencia local excluidos de Git; las pruebas de regresión forman parte del código versionable.

La ejecución completa terminó con **812 pruebas aprobadas**, sin fallos ni omisiones en las suites principales: 566 de la app en 64 suites y 246 del backend en 26 suites. Se añadieron nueve pruebas de regresión. La cobertura conjunta de líneas fue **86,47 %** (7336/8484), por encima del umbral del 85 %, con todos los archivos del inventario presentes. Por componente: app 87,47 % y backend 83,19 %. La cobertura de líneas no representa cobertura total de ramas o escenarios.

También pasaron el chequeo TypeScript de la app, la compilación del backend y la prueba funcional independiente de reintento de reportes (una observación remota tras perder la respuesta). Las herramientas y mapas preparados tuvieron 13 pruebas aprobadas y una omitida por restricciones de enlaces simbólicos de Windows. El ranking Python tuvo 15 aprobadas y una omitida por la misma restricción. Las pruebas alternativas de resolución canónica de rutas sí se ejecutaron.

Dos suites del backend agotaron inicialmente el tiempo de espera al ejecutarse junto a otros procesos. Pasaron al repetirlas de forma aislada y nuevamente en la ejecución completa de cobertura, usando el límite de tiempo habitual. No se cambiaron los límites de tiempo ni se ocultaron fallos.

La exportación de Expo terminó correctamente para **Android, iOS y web**, incluidos los bundles Hermes nativos y el worker/archivo WASM de SQLite para web. Se generó en `reports/bug-review-2026-11-03/export/`, sin cargar `.env`, con una URL HTTPS ficticia y Expo en modo offline. Esta comprobación empaqueta JavaScript y recursos; no genera ni instala un APK/IPA y no valida los módulos nativos en un dispositivo.

Comandos para repetir la validación desde la raíz del repositorio, con las dependencias ya instaladas:

```powershell
npm run typecheck
npm --prefix backend run build
node testing/run-coverage.cjs --output=coverage/bug-review-2026-11-03
node --test testing/offline-maps.test.cjs testing/coverage-tools.test.cjs testing/functional/environment-tools.test.cjs testing/functional/persistence-reader.test.cjs
.\.venv-ai\Scripts\python.exe -m unittest discover -s backend/ml/tests -v
# Solo para comprobar el empaquetado local; URL ficticia, no usar para distribuir.
$env:EXPO_NO_DOTENV = '1'
$env:EXPO_PUBLIC_API_URL = 'https://example.test/api'
$env:EXPO_OFFLINE = '1'
$env:CI = '1'
node node_modules/expo/bin/cli export --platform all --max-workers 2 --output-dir reports/bug-review-2026-11-03/export
```

La validación automatizada usa límites nativos y de red controlados. No equivale a una prueba física de GPS, batería, HealthKit/Health Connect, entrega de SMS o SOS, ni a una verificación del despliegue AWS. No había `adb`, emulador, Docker ni `psql` disponibles en PATH. La precisión de PostgreSQL se verificó en su frontera de lectura emulada, sin conectarse a una base real. Las pruebas Python corresponden al ranking del backend, no a toda la investigación de entrenamiento.

No se modificaron dependencias ni configuración de producción. No se hizo despliegue ni envío real de mensajes.
