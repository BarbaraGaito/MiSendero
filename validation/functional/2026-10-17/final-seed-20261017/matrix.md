# Matriz funcional de MiSendero

Ejecución: 2026-10-17T23:13:24.991Z. Semilla: 20261017.

Los resultados automatizados se limitan a las aserciones enlazadas. Ningún escenario se declara validado en dispositivo o de extremo a extremo.

| ID | Escenario | RF/RNF | Automatización | E2E / manual / dispositivo |
|---|---|---|---|---|
| MF01 | Descarga previa de rutas y mapas | RF-03, RF-03.1, RF-04, RNF-01 | Aprobado en el alcance automatizado | No ejecutados |
| MF02 | Acceso sin red al mapa descargado | RF-03.1, RF-04, RF-06, RNF-01 | Aprobado en el alcance automatizado | No ejecutados |
| MF03 | Ciclo de tracking GPS | RF-05, RF-05.1, RF-05.2, RF-05.3, RF-18, RNF-06 | Aprobado en el alcance automatizado | No ejecutados |
| MF04 | Pérdida y recuperación de conectividad | RF-06, RF-10, RF-11, RF-11.1, RNF-01 | Aprobado en el alcance automatizado | No ejecutados |
| MF05 | Persistencia y recuperación tras cierre | RF-10, RF-14.2, RF-18, RNF-05, RNF-02 | Aprobado en el alcance automatizado | No ejecutados |
| MF06 | Reporte colaborativo creado offline | RF-08, RF-10, RF-11.1, RNF-05 | Aprobado en el alcance automatizado | No ejecutados |
| MF07 | Sincronización diferida, reintentos y duplicados | RF-11, RF-11.1, RNF-05.1 | Fallido | No ejecutados |
| MF08 | Conflictos y reportes desactualizados | RF-09, RF-11.2, RNF-02, RNF-07 | Aprobado en el alcance automatizado | No ejecutados |
| MF09 | GPS desactivado, permiso denegado y precisión insuficiente | RF-06, RNF-06, RNF-07, RNF-10 | Aprobado en el alcance automatizado | No ejecutados |
| MF10 | Descarga incompleta y almacenamiento insuficiente | RF-03.1, RF-04.1, RNF-05, RNF-07 | Aprobado en el alcance automatizado | No ejecutados |
| MF11 | Batería baja y restricciones de segundo plano | RNF-06, RNF-07, RNF-10 | Aprobado en el alcance automatizado | No ejecutados |
| MF12 | SOS sin cobertura y confirmaciones de envío | RF-12, RF-12.1, RF-12.2, RNF-03, RNF-10 | Aprobado en el alcance automatizado | No ejecutados |
| MF13 | Lecturas fisiológicas faltantes o incorrectas | RF-19, RF-20, RNF-02.1, RNF-02.2, RNF-07 | Aprobado en el alcance automatizado | No ejecutados |
| MF14 | Fallo de IA y continuidad de navegación básica | RF-17, RF-20, RF-20.2, RNF-01, RNF-07 | Aprobado en el alcance automatizado | No ejecutados |
| MF15 | Eliminación de cuenta y datos | RF-14.1, RF-14.2, RNF-02, RNF-07 | Aprobado en el alcance automatizado | No ejecutados |

## MF01 — Descarga previa de rutas y mapas

**RF/RNF:** RF-03, RF-03.1, RF-04, RNF-01. **Prioridad:** alta.

**Objetivo:** Obtener un paquete local íntegro antes de comenzar la salida.

**Precondiciones:**

- Cuenta de prueba iniciada; red disponible.
- Proveedor de tiles habilitado para descarga; espacio suficiente.

**Datos:**

- Ruta con geometría, perfil de elevación, dos capas y reportes vigentes.
- Registrar ID de ruta y número de tiles previsto.

**Pasos del protocolo manual/dispositivo:**

1. Abrir detalle y descargar.
2. Observar progreso y esperar la finalización.
3. Consultar inventario local y comparar geometría, elevación y tiles con el plan.

**Resultado esperado:** El estado disponible aparece al terminar la persistencia y la verificación; los elementos del paquete coinciden con la ruta seleccionada.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/mapTileCache.test.ts — mapTileCache descarga todos los tiles a archivos locales verificables: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/offlineDownloadAndElevation.test.tsx — download displays actual tile progress and becomes available only after persistence completes: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** En automatización se controlan red, proveedor de tiles y filesystem; SQLite ejecuta SQL real. No equivale a una descarga sobre almacenamiento nativo.

## MF02 — Acceso sin red al mapa descargado

**RF/RNF:** RF-03.1, RF-04, RF-06, RNF-01. **Prioridad:** alta.

**Objetivo:** Consultar geometría y elevación locales y visualizar tiles ya descargados sin depender de la API.

**Precondiciones:**

- MF01 completado y cuenta conservada.
- Mapa verificado antes de desconectar.

**Datos:**

- Misma ruta de MF01.
- Modo avión con Wi-Fi y datos desactivados; GPS independiente de la red.

**Pasos del protocolo manual/dispositivo:**

1. Desconectar toda red.
2. Abrir mapa descargado y recorrer las dos capas y extremos del trazado.
3. Consultar elevación y detalle; observar solicitudes fallidas sin perder el contenido local.

**Resultado esperado:** Se conservan trazado, capas locales y elevación; la falta de información externa se representa explícitamente.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/offlineElevation.test.ts — persists all elevations in SQLite and reads them after network loss: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/trailRepository.test.ts — a downloaded elevation profile needs no network: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** La lectura local y la ausencia de consulta remota tienen evidencia automatizada. La representación gráfica de los tiles en el teléfono requiere ejecución nativa.

## MF03 — Ciclo de tracking GPS

**RF/RNF:** RF-05, RF-05.1, RF-05.2, RF-05.3, RF-18, RNF-06. **Prioridad:** alta.

**Objetivo:** Mantener identidad, tiempo activo y distancia durante inicio, pausa, continuación y finalización.

**Precondiciones:**

- Cuenta, contacto y confirmación de plan de salida válidos.
- GPS y permisos disponibles; mapa local verificado.

**Datos:**

- Tres posiciones válidas separadas en tiempo; pausa conocida.
- Sesión sin otra ruta activa.

**Pasos del protocolo manual/dispositivo:**

1. Iniciar recorrido y registrar posiciones.
2. Pausar; esperar y desplazarse durante la pausa.
3. Continuar, registrar otra posición y finalizar.
4. Abrir historial e intentar reanudar la sesión terminada.

**Resultado esperado:** La pausa no suma tiempo activo ni puntos; continuar conserva la sesión; finalizar es terminal y el resumen coincide con lo persistido.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/routeSession.test.ts — pause/resume preserves identity and excludes multiple pauses from active time: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/routeAndReportScreens.test.tsx — active route pauses durably before navigating and passes measured distance when finishing: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/routeTracking.test.ts — routeTracking stores GPS points and summarizes real distance: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Se usan posiciones y relojes controlados; no se atribuye al recorrido distancia medida en campo.

## MF04 — Pérdida y recuperación de conectividad

**RF/RNF:** RF-06, RF-10, RF-11, RF-11.1, RNF-01. **Prioridad:** alta.

**Objetivo:** Conservar la operación local y retomar los envíos al recuperarse una conexión utilizable.

**Precondiciones:**

- Recorrido activo, mapa local y cuenta autorizada.
- Posibilidad de alternar red sin alterar el permiso GPS.

**Datos:**

- Evento de red no alcanzable, fallo de petición y posterior respuesta confirmada.

**Pasos del protocolo manual/dispositivo:**

1. Durante el recorrido, cortar Wi-Fi y datos.
2. Crear un reporte y continuar consultando el mapa.
3. Restablecer la red; observar la cola y la confirmación de la API.

**Resultado esperado:** El reporte permanece local durante el corte; el coordinador reintenta con conectividad y sólo confirma al recibir aceptación.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/coordinators.test.tsx — sync validates idle sessions, reacts only to reachable network/foreground and removes listeners: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/functionalResilience.test.ts — MF06 offline report remains pending until connectivity and API acknowledgement: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** La secuencia de conectividad es inyectada. La continuidad simultánea de GPS, mapa y sincronización en una build instalada queda en el protocolo de dispositivo.

## MF05 — Persistencia y recuperación tras cierre

**RF/RNF:** RF-10, RF-14.2, RF-18, RNF-05, RNF-02. **Prioridad:** alta.

**Objetivo:** Recuperar escrituras confirmadas y conservar su propietario al abrir otro proceso.

**Precondiciones:**

- Sesión pausada, punto GPS, reporte pendiente y metadatos de mapa persistidos.
- No desinstalar ni borrar datos al cerrar.

**Datos:**

- Cuenta A y cuenta B; SQLite temporal dedicado.
- ID de sesión, distancia y contenido del reporte registrados antes del cierre.

**Pasos del protocolo manual/dispositivo:**

1. Persistir los datos y cerrar la aplicación completamente.
2. Reabrir con la misma cuenta y comparar estado, puntos, distancia y cola.
3. Cambiar a cuenta B y verificar aislamiento.
4. Repetir tras reinicio del dispositivo sin borrar datos.

**Resultado esperado:** Las escrituras confirmadas reaparecen sin cambiar de propietario; una sesión pausada no se convierte en otro recorrido.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/functionalResilience.test.ts — MF05 committed route, points, report and map survive an independent Node process: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Se cierra la conexión y otro proceso Node abre el archivo SQLite y ejecuta los repositorios de lectura. Identidad y SMS son dobles. No se ensaya corte de energía, terminación durante una transacción ni reinicio del teléfono.

## MF06 — Reporte colaborativo creado offline

**RF/RNF:** RF-08, RF-10, RF-11.1, RNF-05. **Prioridad:** alta.

**Objetivo:** Conservar una observación local con sus datos y un estado de envío honesto.

**Precondiciones:**

- Cuenta iniciada; sin red.
- Ubicación válida o punto del trazado elegido y validado.

**Datos:**

- Barro; severidad Media; estado Precaución; fecha de observación y coordenadas.
- Cuenta propietaria A.

**Pasos del protocolo manual/dispositivo:**

1. Crear reporte offline.
2. Consultar cola y reabrir el formulario o historial pertinente.
3. Restablecer red, provocar un error transitorio y luego permitir la aceptación.
4. Comparar contenido enviado y registro confirmado.

**Resultado esperado:** El reporte queda pendiente localmente, conserva el contenido y pasa a sincronizado tras la aceptación; el error mantiene posibilidad de reintento.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/functionalResilience.test.ts — MF06 offline report remains pending until connectivity and API acknowledgement: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/routeAndReportScreens.test.tsx — a distant GPS fix cannot submit; a validated map choice can and local persistence failure remains visible: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** La prueba nueva ejercita cola y SQL con transporte controlado; la prueba de pantalla verifica selección geográfica y error de persistencia. No constituyen un flujo de interfaz completo entre dos procesos.

## MF07 — Sincronización diferida, reintentos y duplicados

**RF/RNF:** RF-11, RF-11.1, RNF-05.1. **Prioridad:** crítica.

**Objetivo:** Comprobar reintentos y un único efecto remoto por observación ante respuestas perdidas.

**Precondiciones:**

- Operación local pendiente y backend de prueba aislado.
- Posibilidad de aceptar la petición en el servidor y descartar su primera respuesta.

**Datos:**

- Mismo contenido y fecha de observación en ambas peticiones.
- SOS con el mismo client_event_id y actividad con la misma identidad de sesión.

**Pasos del protocolo manual/dispositivo:**

1. Enviar una observación; hacer que el cliente no reciba su confirmación.
2. Reintentar la misma operación.
3. Contar registros remotos y comparar IDs.
4. Repetir el control con SOS y comprobar bloqueo de envíos concurrentes y backoff.

**Resultado esperado:** Un reintento de la misma observación produce un solo registro remoto y conserva su ID; la cola respeta el backoff y evita despachos simultáneos.

**Resultado obtenido — automatización:** Fallido.

- integración; services/__tests__/syncResilience.test.ts — concurrent sync calls share one dispatch: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/syncResilience.test.ts — SOS retries with backoff beyond five failures and cannot be bulk discarded: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; backend/tests/emergencyAlerts.test.js — emergency alerts accepts an SOS without GPS, ignores claimed delivery and deduplicates retries: **passed**. Evidencia: [backend-results.json](backend-results.json).
- integración; backend/tests/functional/reportRetry.probe.js — MF07 retrying a report after a lost response creates one remote observation: **failed**. Evidencia: [probe-results.json](probe-results.json). La aserción y el valor obtenido se conservan en el JSON y en acceptance-probe.txt.

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Fallo observado.

**Observaciones:** La sonda ejecuta dos peticiones sobre la API y cuenta filas en pg-mem. La pérdida de respuesta se representa descartando el primer acuse: no se afirma haber cortado un enlace físico.

## MF08 — Conflictos y reportes desactualizados

**RF/RNF:** RF-09, RF-11.2, RNF-02, RNF-07. **Prioridad:** alta.

**Objetivo:** Evitar que una copia local vieja prevalezca sobre una corrección, retiro o vencimiento aceptado por el servidor.

**Precondiciones:**

- Dos cuentas y dos sesiones de la cuenta autora.
- Mapa con reportes almacenados y servidor con una corrección o retiro posterior.

**Datos:**

- Reporte vigente, reporte observado hace 40 días y reporte retirado.
- Copia local anterior a la corrección; reloj fijado para el control de caducidad.

**Pasos del protocolo manual/dispositivo:**

1. Leer y almacenar reporte.
2. Corregirlo o retirarlo desde otra sesión autorizada; intentar modificarlo desde otra cuenta.
3. Recuperar red y actualizar el paquete local.
4. Consultar reportes vigentes y comparar fechas de observación y recepción.
5. En dos sesiones del autor, enviar correcciones sucesivas y comprobar el último estado aceptado.

**Resultado esperado:** La lectura actualizada usa la respuesta del servidor; no reaparecen retirados o vencidos; una cuenta ajena no modifica el reporte. Las correcciones sucesivas se representan con el último estado aceptado, sin atribuir una fusión de ediciones.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/trailRepository.test.ts — online report refresh replaces the offline copy, including withdrawals and corrections: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; backend/tests/privacyControls.test.js — reports omit author and distinguish old observations uploaded recently: **passed**. Evidencia: [backend-results.json](backend-results.json).
- integración; backend/tests/privacyControls.test.js — withdrawal, correction, blocking, flags and admin moderation enforce ownership: **passed**. Evidencia: [backend-results.json](backend-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Hay evidencia de actualización, caducidad y autorización. No se ejecutó una carrera de ediciones entre dos instalaciones; las pruebas seleccionadas no acreditan una resolución transaccional de versiones concurrentes.

## MF09 — GPS desactivado, permiso denegado y precisión insuficiente

**RF/RNF:** RF-06, RNF-06, RNF-07, RNF-10. **Prioridad:** alta.

**Objetivo:** Representar ubicación no disponible y descartar puntos inadecuados sin inventar coordenadas.

**Precondiciones:**

- Ruta local consultable.
- Control de permisos, proveedor GPS y muestras de ubicación.

**Datos:**

- Permiso denegado; excepción del proveedor; precisión nula o 80 m; posición con más de 30 s y fecha invertida.

**Pasos del protocolo manual/dispositivo:**

1. Denegar permiso y abrir recorrido.
2. Con permiso concedido, desactivar GPS en ajustes y volver.
3. Inyectar o registrar posiciones con precisión insuficiente y observar distancia y aviso.
4. Restablecer GPS y comprobar recuperación con una posición válida.

**Resultado esperado:** No se fabrican posiciones ni se suman puntos rechazados; la denegación no inicia lectura nativa; el mapa local continúa consultable.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- unitaria; services/__tests__/deviceLocation.test.ts — denial prevents both a GPS read and a location subscription: **passed**. Evidencia: [client-results.json](client-results.json).
- unitaria; services/__tests__/deviceLocation.test.ts — provider failure is not replaced with invented coordinates: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/coordinators.test.tsx — GPS writer rejects stale, inaccurate, reversed and implausibly fast fixes: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** El fallo del proveedor es un doble del límite nativo. No se acredita la detección del interruptor GPS de un modelo de teléfono concreto.

## MF10 — Descarga incompleta y almacenamiento insuficiente

**RF/RNF:** RF-03.1, RF-04.1, RNF-05, RNF-07. **Prioridad:** alta.

**Objetivo:** Impedir que una descarga parcial o un error de escritura habiliten un mapa aparentemente completo.

**Precondiciones:**

- Cuenta y ruta válida.
- Filesystem controlado o volumen de prueba limitado; no llenar el almacenamiento personal.

**Datos:**

- Error de descarga; tile corrupto; error ENOSPC; mapa previamente completo.

**Pasos del protocolo manual/dispositivo:**

1. Interrumpir descarga antes del último tile.
2. Intentar abrir el paquete.
3. Repetir con error de espacio y revisar estado persistido.
4. Liberar espacio de prueba, descargar nuevamente y verificar el paquete.

**Resultado esperado:** El paquete incompleto no se abre como disponible; el fallo es visible y permite recuperarse mediante nueva descarga.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/functionalResilience.test.ts — MF10 ENOSPC cannot advertise a downloaded map as usable: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/offlineElevation.test.ts — tile failure still preserves elevation, without marking the map complete: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/offlineDownloadAndElevation.test.tsx — download list verifies local files again before opening and offers redownload for a damaged map: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** ENOSPC se inyecta en el adaptador de descarga; se comprueba el estado real en SQLite. No se agotó un disco ni se ensayó el error nativo de Expo.

## MF11 — Batería baja y restricciones de segundo plano

**RF/RNF:** RNF-06, RNF-07, RNF-10. **Prioridad:** alta.

**Objetivo:** Presentar el nivel conocido y respetar el ciclo de vida sin suscripciones o puntos residuales.

**Precondiciones:**

- Recorrido en primer plano y batería consultable.
- Equipo de prueba con ahorro de energía y suspensión configurables.

**Datos:**

- Nivel 15%; lectura no disponible; fallo de consulta.
- Transiciones active → background → active.

**Pasos del protocolo manual/dispositivo:**

1. Abrir preparación con batería baja.
2. Repetir con lectura ausente o fallida.
3. Iniciar recorrido, enviar a segundo plano y bloquear pantalla.
4. Activar restricción de batería y volver a primer plano; observar estado y suscripciones.

**Resultado esperado:** La batería desconocida se muestra como no disponible; al pasar a segundo plano se retira el watcher según RNF-06. Volver no crea varios escritores ni transforma el intervalo sin medición en distancia recorrida.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; mobile/screens/__tests__/TrailStartTestingMode.test.tsx — MF11 battery reading 0.15 is explicit and preserves the route preparation screen: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/TrailStartTestingMode.test.tsx — MF11 battery reading -1 is explicit and preserves the route preparation screen: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/TrailStartTestingMode.test.tsx — MF11 battery reading null is explicit and preserves the route preparation screen: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/coordinators.test.tsx — backgrounding or switching account prevents further points from the old route: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Se prueban consultas y eventos controlados. No se mide autonomía, consumo, supervivencia al ahorro de energía ni tracking continuo en segundo plano. La checklist de batería es informativa; el umbral visual de 60% no bloquea por sí solo el inicio.

## MF12 — SOS sin cobertura y confirmaciones de envío

**RF/RNF:** RF-12, RF-12.1, RF-12.2, RNF-03, RNF-10. **Prioridad:** crítica.

**Objetivo:** Mantener un SOS pendiente y distinguir registro, apertura de canal y entrega al contacto.

**Precondiciones:**

- Instalación dedicada; contactos ficticios.
- Sin red IP y sin servicio celular; no efectuar llamadas o avisos a servicios de emergencia reales.

**Datos:**

- SOS sin GPS; última posición fechada; client_event_id constante.
- Adaptador SMS cancelado o no disponible y respuesta API registered.

**Pasos del protocolo manual/dispositivo:**

1. Sin cobertura, confirmar creación de SOS en entorno de prueba.
2. Consultar estado local y texto mostrado.
3. Cancelar compositor SMS; comprobar que abrirlo no declara entrega.
4. Restablecer sólo red IP y reintentar; comparar ID y estado de registro.

**Resultado esperado:** El evento se conserva pendiente sin inventar ubicación ni entrega. Un acuse HTTP se identifica como registro; reintentar conserva identidad.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/emergencyAlerts.test.ts — persists SOS without authentication or GPS and retries the same event without duplication: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; backend/tests/emergencyAlerts.test.js — emergency alerts accepts an SOS without GPS, ignores claimed delivery and deduplicates retries: **passed**. Evidencia: [backend-results.json](backend-results.json).
- integración; services/__tests__/simulatedSos.test.tsx — MF12 offline SOS with SMS result cancelled never confirms remote registration or delivery: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; services/__tests__/simulatedSos.test.tsx — MF12 offline SOS with SMS result sent never confirms remote registration or delivery: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Las pruebas ejecutadas no contactan personas ni servicios reales. La ausencia de señal celular y la interfaz nativa SMS requieren dispositivo y canal de ensayo dedicado.

## MF13 — Lecturas fisiológicas faltantes o incorrectas

**RF/RNF:** RF-19, RF-20, RNF-02.1, RNF-02.2, RNF-07. **Prioridad:** alta.

**Objetivo:** Conservar procedencia y antigüedad y abstenerse ante datos no evaluables.

**Precondiciones:**

- Consentimiento y permisos de salud configurables.
- Fuente de ensayo identificada; navegación local disponible.

**Datos:**

- SpO2 y velocidad nulas; pulso NaN; muestra con 301 s de antigüedad o 60 s futura.
- Dispositivo compatible sin registros o con permiso revocado.

**Pasos del protocolo manual/dispositivo:**

1. Consultar métricas sin lecturas.
2. Presentar muestras incompletas, caducas e inválidas.
3. Revocar permiso o desconectar la fuente y volver al recorrido.
4. Verificar texto, procedencia y ausencia de datos fabricados.

**Resultado esperado:** Se informa ausencia o análisis limitado; no se atribuye confianza ni medición válida a datos incorrectos; se conserva acceso al recorrido.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- unitaria; services/__tests__/wearableMetrics.test.ts — predictWearableHealth does not present missing oxygen or speed as stable measured values: **passed**. Evidencia: [client-results.json](client-results.json).
- unitaria; services/__tests__/wearableMetrics.test.ts — predictWearableHealth does not infer from stale, future, or invalid pulse readings: **passed**. Evidencia: [client-results.json](client-results.json).
- unitaria; services/__tests__/nativeWearablePlatforms.test.ts — missing or failed Android reads do not fabricate a pulse; oxygen-only samples retain their actual timestamp: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** Las muestras son fixtures; HealthKit y Health Connect se representan con dobles. No se compararon mediciones de wearables ni se validó una interpretación clínica.

## MF14 — Fallo de IA y continuidad de navegación básica

**RF/RNF:** RF-17, RF-20, RF-20.2, RNF-01, RNF-07. **Prioridad:** alta.

**Objetivo:** Mantener disponibles los servicios de navegación local cuando falla una recomendación o los datos no permiten inferir.

**Precondiciones:**

- Mapa verificado y cuenta de prueba.
- Servicio IA controlado con respuesta de error y modelo con política de habilitación.

**Datos:**

- Error AI provider unavailable; entrada NaN; modelo no aprobado.
- Ruta y punto GPS válidos.

**Pasos del protocolo manual/dispositivo:**

1. Provocar fallo de la recomendación.
2. Abrir el mapa local y persistir un punto de recorrido.
3. Consultar inferencia con entrada no válida y modelo no habilitado.
4. Volver a navegación y comprobar su estado.

**Resultado esperado:** Se informa el fallo o la abstención; mapa y persistencia GPS continúan disponibles y no se fabrica una recomendación.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/functionalResilience.test.ts — MF14 failed AI request leaves verified offline navigation and GPS persistence usable: **passed**. Evidencia: [client-results.json](client-results.json).
- unitaria; ai/__tests__/inferenceEngine.test.ts — public ground-truth deployment policy forests run only with deployment approval and complete inputs: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; mobile/screens/__tests__/DiscoverTrailScreen.test.tsx — loading blocks repeat submissions, then an offline error preserves answers for retry: **passed**. Evidencia: [client-results.json](client-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** La independencia se comprueba entre servicios y mediante pantallas aisladas. No se fuerza una excepción arbitraria dentro de un modelo mientras corre una build nativa ni se acredita exactitud predictiva.

## MF15 — Eliminación de cuenta y datos

**RF/RNF:** RF-14.1, RF-14.2, RNF-02, RNF-07. **Prioridad:** crítica.

**Objetivo:** Eliminar datos de la cuenta autorizada y evitar reenvíos con credenciales revocadas.

**Precondiciones:**

- Cuenta desechable A y cuenta de control B.
- Datos de actividad, reportes, contacto y cola asociados a A; contraseña conocida.

**Datos:**

- Contraseña incorrecta y correcta; dos tokens de A.
- Respuesta de eliminación perdida y posterior reintento.

**Pasos del protocolo manual/dispositivo:**

1. Solicitar baja con contraseña incorrecta y comprobar que la cuenta siga utilizable.
2. Solicitarla con contraseña válida; descartar el acuse y reintentar.
3. Comprobar datos locales/remotos y rechazos de credenciales anteriores.
4. Comprobar que B conserve sus datos y que la cola de A no vuelva a enviarse.

**Resultado esperado:** Sólo la baja autorizada elimina datos; una respuesta incierta suspende envíos de A; la confirmación limpia su información y las credenciales dejan de autorizar operaciones.

**Resultado obtenido — automatización:** Aprobado en el alcance automatizado.

- integración; services/__tests__/privacyControls.test.ts — a lost deletion response suspends all queue writes and retries; successful retry cleans only that owner: **passed**. Evidencia: [client-results.json](client-results.json).
- integración; backend/tests/privacyControls.test.js — deletion requires password and removes names, activities, contact copies, jobs and all installation credentials: **passed**. Evidencia: [backend-results.json](backend-results.json).

**Resultado obtenido — E2E, manual y dispositivo:** No ejecutados. Evidencia: ninguna.

**Estado:** Validación parcial por nivel.

**Observaciones:** La eliminación está implementada. Se vincula con autenticación y aislamiento; el catálogo RF no posee un identificador específico de baja. No se acredita eliminación física en backups o proveedores externos.
