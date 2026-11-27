<p align="center">
  <img src="./assets/misendero_logo.svg" alt="MiSendero" width="420" />
</p>

# MiSendero

**Aplicación inteligente de asistencia y seguridad para trekking.**

MiSendero es un prototipo móvil que apoya la orientación, el registro de actividad y la toma de decisiones durante salidas de trekking con baja o nula conectividad. Permite preparar rutas y mapas antes de salir, seguir el recorrido por GPS, registrar reportes del terreno y conservar operaciones para sincronizarlas al recuperar conexión.

El proyecto integra una app React Native/Expo, una API Node.js/Express con PostgreSQL desplegada en AWS y un módulo experimental de inteligencia artificial desarrollado en Python y scikit-learn.

## Proyecto académico

Proyecto Final de Ingeniería en Informática de la **Universidad Argentina de la Empresa (UADE)**.

- **Autoras:** Lara Trinidad Alonso y Bárbara Denise Gaito.
- **Tutor:** Andrés Damián Sacco.
- **Versión de la app:** 1.0.3.

## Funcionalidades

| Área | Comportamiento |
| --- | --- |
| Exploración | Catálogo de senderos y parques nacionales, búsqueda, filtros y favoritos por cuenta. Fichas con distancia, duración, dificultad, reportes, clima y elevación cuando existen datos. |
| Mapas offline | Paquetes con trazado, mapa básico de la zona y datos disponibles de la ruta. Verificación de archivos, inventario por cuenta, actualización y eliminación. |
| Navegación y actividad | Seguimiento GPS en primer plano, alerta visual de desvío a más de 120 m, pausa, reanudación, distancia, tiempo activo, ritmo, progreso y resumen final. |
| Reportes colaborativos | Registro georreferenciado del terreno, consulta de reportes vigentes, almacenamiento pendiente sin red y herramientas de denuncia, bloqueo y moderación. |
| Sincronización | Cola local por cuenta para reportes, actividades, eventos SOS, cierres de plan y decisiones de privacidad, con estados visibles, reintentos e identificadores idempotentes. |
| Preparación y ayuda | Contacto de emergencia, aviso de salida confirmado antes de iniciar un recorrido real, SOS con última ubicación disponible y apertura del compositor SMS o de la aplicación de llamadas. Detección de posible caída mediante el acelerómetro para abrir el flujo de ayuda. |
| Plan de regreso | Registro online de la hora prevista y del contacto; avisos de regreso no confirmado mediante un adaptador externo configurado en el backend. El cierre puede quedar pendiente sin conexión. |
| Wearables | Lectura consentida de métricas mediante Apple HealthKit o Android Health Connect, con procedencia y fecha. Avisos orientativos sobre lecturas recientes y simulador de desarrollo separado de los registros reales. |
| Descubrí tu sendero | Consulta de cuatro pasos —destino, paisaje, duración y dificultad— que utiliza la experiencia del perfil y selecciona una ruta mediante reglas explícitas sobre el catálogo. Requiere sesión y conexión. |
| Cuenta y privacidad | Registro, inicio y cierre de sesión, perfil de experiencia, consentimiento por finalidad, exportación y eliminación de datos de la cuenta. |

## Arquitectura y tecnologías

| Componente | Implementación |
| --- | --- |
| Cliente móvil | React Native 0.88, React 19.3, Expo SDK 58, Expo Router y TypeScript. |
| Persistencia local | SQLite con SQLCipher en builds nativas propias, archivos de mapas y SecureStore para credenciales y clave de cifrado. |
| API | Node.js, Express 5, JWT, bcrypt, validación con Zod, Helmet, límites de solicitudes y logging con Pino. |
| Base central | PostgreSQL; PostgreSQL 16 en Docker Compose para desarrollo. |
| Cartografía | Mapas vectoriales básicos preparados con datos de OpenStreetMap y proveedor raster opcional. Perfiles de elevación y datos meteorológicos según disponibilidad. |
| Investigación de IA | Python, scikit-learn, fuentes públicas auditadas y artefactos experimentales con métricas reproducibles. |
| Validación | Jest, React Test Renderer, Supertest, pg-mem, Babel/Istanbul, GitHub Actions y análisis SonarQube cuando está configurado. |

La app conserva localmente las rutas preparadas y las operaciones pendientes. La sincronización procesa únicamente los datos de la cuenta activa y mantiene la identidad de cada operación entre reintentos. El catálogo remoto, la autenticación inicial, el clima, las nuevas recomendaciones y la creación de planes de regreso dependen de conectividad.

El despliegue académico documentado utiliza una instancia **EC2 con Nginx y el servicio Node.js**, y **Amazon RDS para PostgreSQL**, en `us-east-2`. Docker Compose reproduce el entorno local. La publicación de imágenes en GitHub Container Registry y la actualización del servicio en AWS son operaciones distintas; el despliegue en AWS es manual.

### Estructura del repositorio

```text
app/           Rutas y entradas de Expo Router
mobile/        Pantallas, componentes y hooks de la app
services/      Navegación, mapas, sincronización, cuenta, emergencia y wearables
database/      Persistencia local, sesiones y almacenamiento protegido
ai/            Motor de inferencia, contratos y métricas de los modelos
assets/        Recursos visuales y mapas offline incluidos en la app
backend/       API Express, migraciones, catálogo y pruebas de integración
training/      Fuentes, preparación, entrenamiento y evaluación experimental
scripts/       Herramientas de preparación y validación
testing/       Pruebas funcionales y herramientas de cobertura
validation/    Evidencia de validaciones conservadas
docs/          Guías técnicas, auditorías y resultados
```

## Ejecución local

Los ejemplos usan PowerShell desde la raíz del repositorio. Se requiere Node.js **22.13 o posterior de la línea 22, 24.3 o posterior de la línea 24, o 26+**, npm y Docker con Compose para PostgreSQL. Python se necesita para la investigación de IA; el recomendador actual del catálogo funciona con Node.js.

### PostgreSQL y backend con Docker

En la primera configuración, copiá el archivo de ejemplo; si ya tenés `.env`, conservá sus valores y completá las variables que falten:

```powershell
Copy-Item .env.example .env
```

Antes de iniciar, completá `JWT_SECRET` y `POSTGRES_PASSWORD` con valores propios. Podés generar un valor aleatorio para cada uno con:

```powershell
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

El ejemplo configura `MISENDERO_BACKEND_NODE_ENV=development` para el entorno local. Con esa configuración, el servidor aplica migraciones y datos semilla al iniciar de forma idempotente.

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:3001/api/health
```

La API queda en `http://localhost:3001/api` y el health check devuelve `ok: true` y `service: misendero-backend`.

Para usar una imagen publicada, configurá `MISENDERO_BACKEND_IMAGE` en `.env` y ejecutá esta alternativa:

```powershell
docker compose -f docker-compose.images.yml up -d
```

El workflow [docker-publish.yml](.github/workflows/docker-publish.yml) publica la imagen del backend en GHCR al actualizar `main`, crear un tag `v*` o ejecutarlo manualmente.

### Backend sin contenedor

Con el `.env` de la raíz preparado, iniciá solo PostgreSQL:

```powershell
docker compose up -d db
Set-Location backend
Copy-Item .env.example .env
```

En `backend/.env`, configurá un `JWT_SECRET` propio y ajustá `DATABASE_URL` para que usuario, contraseña y base coincidan con PostgreSQL. Reemplazá la contraseña del ejemplo del backend por la elegida en el `.env` de la raíz.

```powershell
npm ci
npm run db:migrate
npm run dev
```

`npm run dev` compila los servicios TypeScript antes de iniciar el servidor. Para usar `npm start` directamente, ejecutá antes `npm run build`.

### App móvil

En otra terminal, desde la raíz:

```powershell
npm ci --legacy-peer-deps
npx expo start --go
```

Usá una versión de **Expo Go compatible con SDK 58** y conectá el teléfono y la computadora a la misma red. Si Expo pide iniciar sesión, ejecutá `npx expo login`; en iPhone, usá la misma cuenta en Expo Go y en la terminal. Después de actualizar el repositorio, repetí la instalación desde el lockfile; si Metro estaba abierto, reinicialo con `npx expo start --go --clear`.

Para que un teléfono alcance el backend Docker local, configurá en el `.env` de la raíz:

```dotenv
MISENDERO_BACKEND_BIND=0.0.0.0
MISENDERO_BACKEND_NODE_ENV=development
# Ejemplo: reemplazar por la IP de la computadora en la red local.
EXPO_PUBLIC_API_URL=http://192.168.1.10:3001/api
```

Aplicá los cambios del backend con `docker compose up --build -d --no-deps backend` y reiniciá Expo. La URL debe incluir `/api`. En desarrollo, si `EXPO_PUBLIC_API_URL` queda vacía, la app intenta usar el host de Expo en el puerto 3001; las builds de distribución exigen una URL HTTPS.

**Expo Go y web usan una base temporal en memoria.** Los datos locales se reinician al recargar o cerrar completamente el proyecto. Para verificar persistencia cifrada, reapertura de mapas y módulos nativos de HealthKit/Health Connect se necesita una build propia.

### APK Android

El perfil `preview` de [eas.json](eas.json) genera una APK para instalación interna:

```powershell
npm run build:android:preview
```

Requiere acceso al proyecto de Expo/EAS y sus credenciales de compilación. La URL de la API se incorpora al compilar; revisá el perfil antes de generar una build. El perfil `production` genera un Android App Bundle. La corrección de arranque de la versión 1.0.3 está documentada en [apk-startup-fix.md](docs/apk-startup-fix.md).

## Mapas y funcionamiento sin conexión

La descarga predeterminada extrae al teléfono un **mapa vectorial básico 2D incluido en la app**, preparado con datos reales de OpenStreetMap para las zonas del catálogo. Muestra caminos, senderos, cursos de agua, lagos, bosques y referencias disponibles. El paquete conserva también el trazado y los datos disponibles de la ruta y sus reportes.

Los archivos y su correspondencia con la geometría se verifican al descargar y al abrir el paquete. Abrir una ruta desde **Mapas descargados** fuerza el mapa local 2D, incluso con Wi-Fi. El mapa offline no incluye imágenes satelitales ni relieve 3D; las rutas fuera de las zonas incluidas requieren preparar nuevos recursos y compilar una app actualizada.

Para comprobar los recursos incluidos y las pruebas del flujo:

```powershell
npm run prepare:offline-maps -- --verify
npm run validate:offline-maps
```

La preparación de nuevas zonas se realiza con `npm run prepare:offline-maps` y genera `assets/offline-maps/catalog.json`. La app no consulta Overpass como backend operativo. Los datos conservan atribución a OpenStreetMap y licencia ODbL, visibles también en la pantalla Fuentes y licencias.

Si se configura `EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL`, puede utilizarse el proveedor raster opcional con HTTPS, atribución y autorización de descarga offline. La vista 3D disponible en otras pantallas es una representación visual del terreno; su presencia no acredita un levantamiento topográfico de campo. Ver [guía de mapas offline](docs/offline-basic-maps.md) y [representación 3D](docs/realistic-terrain-3d.md).

## Inteligencia artificial y recomendación

### Evaluación experimental

El PFI documenta cuatro clasificadores Random Forest evaluados con **1030 observaciones públicas reales**:

| Tarea | Fuente y etiqueta |
| --- | --- |
| Fatiga percibida | Mediciones y respuestas Borg observadas en GeoFatigue. |
| Mal agudo de montaña (AMS) | Pulso y SpO₂ nocturnos de un estudio de hipoxia controlada con resultado AMS observado. |
| Dificultad técnica de tramos | Etiquetas `sac_scale` de OpenStreetMap y relieve del IGN de 30 m. |
| Dificultad de recorridos completos | Distancia, duración y dificultad oficial publicada por la Administración de Parques Nacionales. |

Las fuentes originales se fijan mediante hashes; las particiones separan participantes, regiones o parques, y la selección de parámetros utiliza validación cruzada dentro de entrenamiento. Se conservan procedencia, predicciones de prueba, métricas y limitaciones.

La aplicación incorpora además dos modelos locales del prototipo orientativo, preparados con mediciones y respuestas públicas reales. La ejecución `v1` conserva las 666 observaciones originales de fatiga y agrega una tarea independiente con 377 pares de visitas de trekking en Nepal. No se mezclan cuestionarios, escalas ni horizontes incompatibles.

| Control del prototipo | Resultado reservado y comportamiento en la app |
| --- | --- |
| Esfuerzo Borg 0–10 | Error absoluto medio **0,464**, frente a **0,994** al repetir el Borg previo; 179 observaciones de 12 personas. Estima con un minuto completo de pulso real y autorreportes anteriores, separando **Declarado** de **Estimado**. |
| Altura, próxima etapa de ascenso | Average precision **0,296**, frente a **0,129** de referencia; Brier **0,107** frente a **0,115**; 139 observaciones de 30 personas. Solo ofrece una puntuación orientativa en un control matutino en reposo. El umbral fijado en entrenamiento produjo 18 verdaderos positivos y 121 falsos positivos: **no se habilitan clasificaciones binarias ni alertas de riesgo con ese umbral**. |

En el mapa y las pausas se puede declarar esfuerzo de forma opcional al inicio y cada diez minutos. No hay formularios que bloqueen la navegación. La estimación requiere un Borg anterior de al menos un minuto y entradas dentro de los rangos observados de entrenamiento; puede quedar pendiente entre registros. La ventana causal de búsqueda es de 15 minutos, pero el rango observado del Borg más reciente en `v1` llega hasta 6 minutos. No se usa la respuesta actual para predecirse a sí misma.

El control de altura está en preparación de salida y pausas: exige confirmar descanso nocturno, reposo actual y evaluación previa al próximo ascenso, entre las 5 y las 12; pulso y SpO₂ reales recientes; y altitud GPS absoluta con precisión vertical de hasta 50 m. El desnivel de la ruta no reemplaza esa altitud. Sin entradas compatibles, el control explica por qué no puede estimar. Las lecturas simuladas no alimentan estos modelos ni el historial real.

Estas son estimaciones de un **prototipo académico informativo**. Fatiga usa tareas con carga de GeoFatigue y reutiliza el test histórico; su mejora no demuestra transferencia general a trekking. Altura usa cuestionarios de la cohorte de Boos y no constituye diagnóstico ni probabilidad individual validada. Los resultados no autorizan un ascenso y no activan SOS. Los controles se guardan por cuenta en el almacenamiento protegido existente, requieren consentimiento de salud, se eliminan al revocarlo o borrar la cuenta y caducan a los siete días. No se envían al servidor.

El resumen operativo del reloj utiliza reglas explícitas sobre lecturas recientes, identificadas como **Avisos de lectura** y **Carga por pulso**. Esas reglas no producen una clasificación aprendida de fatiga ni un porcentaje de confianza del modelo. Ver [análisis de lecturas del wearable](docs/analisis-lecturas-wearable.md).

Para preparar el entorno de investigación en Windows y reproducir el pipeline:

```powershell
py -3 -m venv .venv-ai
.\.venv-ai\Scripts\python.exe -m pip install -r training/python/requirements-public.lock.txt
npm run fetch:ai-data
npm run prepare:ai-datasets
npm run train:ai
npm run validate:ai-data
npm run test:ai-data
```

Los originales descargados no se versionan; reproducir una evaluación exige los snapshots que coincidan con el lock de fuentes. `npm run evaluate:ai` actualiza comparaciones sobre las predicciones guardadas sin reentrenar. Ver [datasets y procedencia](ai/datasets/README.md), [auditoría de datos reales](docs/ai-real-data-audit.md) y [evaluación de modelos](docs/evaluacion-modelos-reales.md).

La nueva ejecución del prototipo se reproduce después de preparar esos originales:

```powershell
npm run ai:field -- prepare
npm run ai:field -- select
npm run ai:field -- evaluate
npm run ai:field -- validate
.\.venv-ai\Scripts\python.exe -m unittest discover -s training/python -p test_field_ai.py -v
```

`training/data/field-ai/v1` conserva datasets, procedencia, protocolo fijado antes del test, 76 candidatos por tarea, predicciones OOF, elección, calibración y umbral, métricas, intervalos por participante y fixtures de paridad. `ai/models/field` contiene exactamente los artefactos evaluados. `validate` reconstruye fuentes, ajusta nuevamente los ganadores y verifica predicciones, métricas y bundle. Las etapas rechazan sobrescribir evidencia distinta; `--run otro_id` crea otra versión y no convierte un test ya observado en un test nuevo. El [catálogo de fuentes adicionales](docs/datasets-publicos-2026-11-27.json) documenta también los datasets descartados y sus motivos.

Las métricas científicas incluyen todas las filas reservadas. Al aplicar además los rangos de entrada de la app, quedan 177/179 controles de fatiga y 138/139 de altura; el resto se abstiene sin quitarlo del denominador. [delivery.json](training/data/field-ai/v1/delivery.json) conserva ese conteo, comprobado por las pruebas del motor móvil. No mide la disponibilidad de sensores en una caminata real. La integración nativa nueva requiere verificar una build propia con un reloj compatible; las pruebas automatizadas usan dobles de HealthKit/Health Connect.

### Descubrí tu sendero

El recomendador vigente selecciona un sendero de PostgreSQL según destino, experiencia del perfil, duración, dificultad y paisaje, y explica coincidencias y ajustes. Conserva los datos y avisos de la ficha, incluidos los atributos no documentados.

`POST /api/ai/recommend-trail` y `GET /api/ai/destinations` requieren autenticación. La respuesta identifica `ranking.method: catalog` y `modelVersion: null`: la selección actual utiliza reglas del producto y no ejecuta un modelo aprendido ni necesita claves de un proveedor generativo. El código de ranking previo en `backend/ml/` se conserva como material histórico desconectado de la API. Ver [contrato y reglas del recomendador](docs/trail-recommendation.md).

## Pruebas y validación

La medición del **19/11/2026**, recogida en el documento del PFI, informó:

| Componente | Suites | Casos aprobados | Líneas cubiertas |
| --- | ---: | ---: | ---: |
| Cliente | 71 | 628 | 6207/7033 · 88,25 % |
| Backend | 28 | 257 | 1819/2229 · 81,60 % |
| **Conjunto** | **99** | **885** | **8026/9262 · 86,66 %** |

Estos valores corresponden a esa ejecución documentada. La cobertura conjunta suma contadores de líneas ejecutables de ambos componentes; la meta de RNF-11 es **85 % de líneas**. Las pruebas de investigación Python se informan por separado.

El PFI registra además pruebas manuales de extremo a extremo en Android —Expo y APK 1.0.3—, iPhone con Expo Go, y lectura mediante Health Connect con relojes Wear OS y Garmin. La comprobación de persistencia y de módulos nativos debe realizarse con una build que incluya esas capacidades.

Para ejecutar pruebas unitarias y de integración desde la raíz:

```powershell
npm test -- --runInBand
npm --prefix backend test -- --runInBand
```

El backend utiliza `pg-mem`; estas pruebas no requieren Docker ni una base PostgreSQL activa. Para reproducir el procedimiento de tipos, compilación y cobertura de CI:

```powershell
npm ci --legacy-peer-deps --ignore-scripts
npm ci --prefix backend --ignore-scripts
npm run typecheck
npm --prefix backend run build
npm run test:coverage
```

[CI](.github/workflows/ci.yml) usa Node.js 24.19.0, verifica el inventario y el lockfile, y exige pruebas aprobadas sin omisiones y cobertura conjunta de líneas de al menos 85 %. Conserva reportes HTML, LCOV, JSON, CSV y hashes en los artefactos de cobertura. Los mocks de SQLite utilizan `node:sqlite`.

La cobertura Python se genera de forma independiente:

```powershell
.\.venv-ai\Scripts\python.exe -m pip install -r testing/requirements-coverage.txt
npm run test:coverage:python
```

La [auditoría del 16/10/2026](docs/coverage-audit-2026-10-16/README.md) y la [validación funcional del 17/10/2026](validation/functional/2026-10-17/README.md) conservan mediciones históricas y el detalle de sus respectivos alcances. Cada nueva ejecución genera su evidencia en `coverage/`.

## Trazabilidad con el PFI

Los identificadores corresponden a las tablas de requerimientos del documento académico. La tabla ubica los componentes que permiten revisar cada área; la evidencia y los límites de validación se describen en el PFI y en las guías técnicas.

| Requerimientos | Implementación principal |
| --- | --- |
| RF-01, RF-02, RF-16 y RF-21: catálogo, detalle, clima y favoritos | `mobile/screens/ExploreRoutesScreen.tsx`, `mobile/screens/TrailDetail.tsx`, `services/favoriteTrails.ts`, `backend/src/routes/trails.routes.js`. |
| RF-03, RF-04 y RNF-01: paquetes y consulta offline | `services/offlineMaps.ts`, `services/basicOfflineMap.ts`, `mobile/screens/OfflineMapsScreen.tsx`, `assets/offline-maps/`. |
| RF-05, RF-06, RF-07 y RF-18: sesión, GPS, desvío y métricas | `mobile/screens/RouteMap.tsx`, `services/routeTracking.ts`, `services/geoUtils.ts`, `database/sessionsRepository.ts`. |
| RF-05.4 y RF-12 a RF-13: aviso de salida, SOS y contacto | `services/departureMessages.ts`, `services/emergencyAlerts.ts`, `services/fallDetection.ts`, `mobile/screens/ConfirmSosScreen.tsx`. |
| RF-08 a RF-11: reportes y sincronización | `mobile/screens/ReportTerrainScreen.tsx`, `services/syncQueue.ts`, `backend/src/routes/trails.routes.js`. |
| RF-14 y RF-15: cuenta y perfil | `services/authSession.ts`, `services/experienceProfile.ts`, `backend/src/routes/auth.routes.js`. |
| RF-17 y RF-17.1: dificultad experimental y recomendación | `training/python/train_public.py`, `ai/models/`, `backend/src/ai/`. El recomendador actual utiliza reglas del catálogo; el requisito de un modelo aprendido aprobado no queda acreditado por ese flujo. |
| RF-19 y RF-20: wearables, inferencia y habilitación | `services/nativeWearableBridge.ts`, `services/wearableMetrics.ts`, `ai/inferenceEngine.ts`. |
| RNF-02 y derivados: aislamiento, consentimiento y credenciales | `services/accountContext.ts`, `services/privacyConsent.ts`, `database/protectedStorage.ts`, `services/authSession.ts`. |
| RNF-05 y RNF-09: durabilidad, idempotencia y configuración segura | `database/activityOutbox.ts`, `services/syncQueue.ts`, `backend/src/securityConfig.js`, `app.config.js`. |
| RNF-11: cobertura automatizada | `testing/run-coverage.cjs`, `.github/workflows/ci.yml`. |

## Alcance y límites del prototipo

- **Operación offline:** cubre contenido preparado y registros locales. El GPS se sigue en primer plano; la app libera su suscripción al pasar a segundo plano.
- **Emergencias:** guardar un SOS o recibir confirmación de la API no confirma entrega al contacto. El SMS y la llamada utilizan las aplicaciones del teléfono y dependen del canal disponible. El aviso automático de regreso requiere `ALERT_WEBHOOK_URL`, `ALERT_WEBHOOK_TOKEN` y un receptor que gestione entrega y deduplicación.
- **IA:** los modelos son experimentales y la habilitación es específica por versión y uso. La inferencia de árboles utiliza JSON y TypeScript; el proyecto no incorpora TensorFlow Lite. Las reglas del catálogo y los avisos del reloj tienen sus propios alcances.
- **Wearables:** la integración se realiza mediante las plataformas de salud del teléfono; no existe emparejamiento BLE directo con cada reloj. El simulador sirve para desarrollo y conserva los datos de prueba separados.
- **Despliegue:** en producción, el backend omite migraciones y carga de datos al arrancar. Exige `JWT_SECRET` robusto, `PRIVACY_CONTACT_URL` y `PGSSLROOTCERT` para verificar TLS de PostgreSQL; los cambios de esquema y catálogo se ejecutan como acciones explícitas del operador.
- **Validación académica:** el alcance comprende un prototipo funcional y su evaluación técnica. No incluye alta disponibilidad, operación comercial a escala, certificación médica o de rescate ni respuesta automática de organismos externos.
