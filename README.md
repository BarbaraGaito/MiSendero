<p align="center">
  <img src="./assets/misendero_logo.svg" alt="MiSendero" width="420" />
</p>

# MiSendero

La funcionalidad **Descubrí tu sendero** incorpora una encuesta de cuatro pasos y una recomendación de trekking con IA. Configuración, pruebas y actualización de AWS: [guía de implementación](docs/trail-recommendation.md).

Aplicacion movil (Expo/React Native) de asistencia y seguridad para trekking, con backend
Node.js/Express + PostgreSQL, modulo de IA entrenado en Python/Scikit-learn, mapas y navegacion
offline, y sincronizacion diferida de reportes, actividad y alertas de emergencia.

## Arranque rapido con Docker

Para levantar PostgreSQL y el backend desde el codigo local:

```bash
cp .env.example .env
docker compose up --build
```

El backend queda disponible en `http://localhost:3001/api/health`. Al iniciar, aplica las
migraciones y siembra datos base de forma idempotente.

Tambien se incluye un compose para usar una imagen de backend ya publicada:

```bash
cp .env.example .env
# editar MISENDERO_BACKEND_IMAGE en .env, por ejemplo:
# ghcr.io/barbaragaito/misendero-backend:latest
docker compose -f docker-compose.images.yml up
```

Ese segundo archivo queda preparado para CI/CD o despliegues donde la imagen ya este subida
a un registry. El workflow `.github/workflows/docker-publish.yml` publica la imagen del
backend en GitHub Container Registry (`ghcr.io`) al pushear a `main`, crear un tag `v*` o
ejecutarlo manualmente.

## Arranque rapido manual

1. **Base de datos** (requiere Docker):
   ```bash
   docker compose up -d db
   ```
2. **Backend**:
   ```bash
   cd backend
   cp .env.example .env   # y generar un JWT_SECRET propio, ver el comentario en el archivo
   npm install
   npm run db:migrate
   npm run dev
   ```
   Health check: `curl http://localhost:3001/api/health`
3. **App movil** (en otra terminal, desde la raiz del repo):
   ```bash
   npm install
   npm start
   ```

## Tests

Los cambios de privacidad, baja de cuenta y moderación del 16/10/2026, junto con su evidencia
local y los pendientes operativos/jurídicos, están en
[implementacion-privacidad-2026-10-16.md](docs/implementacion-privacidad-2026-10-16.md).

```bash
npm test              # frontend: geoUtils, mapas offline, favoritos, tracking, cola offline e IA
cd backend && npm test # backend: auth, trails, activities, emergency-alerts, limpieza de
                       # reportes obsoletos, aplicacion de dificultad de ruta (via pg-mem, sin Docker)
```

La auditoría, el alcance completo, los resultados por componente y las brechas están en
[el informe de cobertura del 16/10/2026](docs/coverage-audit-2026-10-16/README.md).

```bash
npm ci --legacy-peer-deps --ignore-scripts
npm ci --prefix backend --ignore-scripts
npm run typecheck
npm run test:coverage
```

El primer comando conserva el grafo del lockfile sin resolver nuevamente los pares nativos
opcionales de Expo. No cambia versiones. CI usa Node 24.19.0, comprueba tipos y ejecuta las
pruebas de ambos componentes con instrumentación Babel/Istanbul. Falla si la cobertura conjunta
de líneas es menor al 85 %, hay archivos del inventario ausentes o hay pruebas fallidas u omitidas.
Conserva HTML, LCOV, JSON, CSV por archivo y hashes como artefacto incluso cuando falla.
Los mocks de SQLite usan `node:sqlite`; las pruebas nativas y de dispositivo se acreditan aparte.

La investigación Python tiene un informe independiente, sin sumarlo al porcentaje del producto:

```bash
.venv-ai/Scripts/python.exe -m pip install -r testing/requirements-coverage.txt
npm run test:coverage:python
```

## Trazabilidad contra el planteo del PFI

| Requisito | Implementacion principal | Evidencia de validacion |
| --- | --- | --- |
| RF-01/RF-02 exploracion y favoritos | `mobile/screens/ExploreRoutesScreen.tsx`, `mobile/screens/TrailDetail.tsx`, `services/favoriteTrails.ts` | Busqueda/filtros por dificultad y distancia, rutas favoritas persistidas en SQLite |
| RF-02 informacion previa | `mobile/screens/TrailDetail.tsx`, `mobile/components/TrailMap.tsx`, `mobile/components/Terrain3DScene.tsx`, `backend/src/routes/trails.routes.js` | Distancia, duracion, dificultad, clima, reportes, disponibilidad offline, desnivel aproximado y vista 2D/3D del terreno |
| RF-03/RNF-01 mapas offline | `services/offlineMaps.ts`, `services/mapTileCache.ts`, `mobile/components/TrailMap.tsx`, pantallas `offline-*` | Descarga real de tiles, copia local de ruta/reportes, verificacion, reintento, eliminacion de mapas almacenados y capas visuales locales compatibles offline |
| RF-05/RF-06/RF-18 tracking real | `mobile/screens/RouteMap.tsx`, `services/routeTracking.ts`, `database/sessionsRepository.ts` | Puntos GPS persistidos, distancia acumulada y test `routeTracking.test.ts` |
| RF-07 alertas de desvio | `mobile/screens/RouteMap.tsx`, `mobile/screens/AlertRouteScreen.tsx`, `services/geoUtils.ts` | Tests de distancia/progreso de ruta en `geoUtils.test.ts` |
| RF-08/RF-09 reportes colaborativos | `mobile/screens/ReportTerrainScreen.tsx`, `backend/src/routes/trails.routes.js` | Reportes con latitud, longitud, precision y progreso de ruta en tests backend |
| RF-10/RF-11 sincronizacion diferida | `services/syncQueue.ts`, tarjeta de sincronizacion en `ProfileScreen.tsx` | Estados pending/synced/failed/abandoned y reintentos testeados |
| RF-12/RF-13 emergencia | `services/emergencyAlerts.ts`, `ConfirmSosScreen.tsx`, `backend/src/routes/emergencyAlerts.routes.js` | Mensaje SOS preparado, contacto, ultima ubicacion conocida y cola offline |
| RF-17/RF-19/RF-20 IA y wearables | `ai/inferenceEngine.ts`, `services/wearableMetrics.ts`, `services/experienceProfile.ts` | Tests de inferencia local y explicacion visible de recomendaciones |
| RNF-02 privacidad | `services/privacyConsent.ts`, `ProfileScreen.tsx` | Consentimiento explicito y borrado local de datos fisiologicos al revocar permiso |

## Mapas, terreno y modo offline

La descarga actual guarda solo un mapa básico 2D y el trazado; no necesita
altimetría ni descarga relieve 3D. La fuente de imágenes debe estar publicada y
configurada antes de probar una descarga real. Ver [configuración y preparación
de mapas estáticos propios en AWS](docs/offline-basic-maps.md).

La app combina tiles reales con capas locales para que el recorrido se entienda aun sin
conexion. `services/mapTileCache.ts` resuelve las URLs remotas por capa (`Mapa`, `Terreno`,
`Satelite`), guarda los tiles descargados y permite que `TrailMap` use primero el archivo
local cuando existe. La descarga offline se blinda desde `services/offlineMaps.ts` con
verificacion de cobertura, estados de progreso, cancelacion, reintentos y eliminacion de
mapas almacenados.

Sobre esos tiles, `mobile/components/TrailMap.tsx` agrega informacion visual generada en
la app: ruta principal continua con halo de alto contraste, curvas de nivel, trazas secundarias,
arroyo/valle de referencia y etiquetas de terreno. Estas capas no reemplazan los tiles ni
requieren red, por lo que siguen visibles sobre mapas descargados.

La vista 3D de `mobile/components/Terrain3DScene.tsx` genera un modelo de terreno a partir
de la ruta y el centro del sendero. El relieve usa variacion por altura, pendiente y ruido
procedural para diferenciar valle, bosque, roca, claros/nieve, crestas, curvas de nivel,
senderos laterales y la ruta destacada en naranja.

## Modulo de IA (Python + Scikit-learn)

La evaluación vigente usa únicamente fuentes públicas con etiquetas independientes:
respuestas Borg de GeoFatigue, AMS observado en un estudio de hipoxia controlada y
`sac_scale` publicado en OpenStreetMap y dificultad oficial de recorridos APN. El relieve
de 30 m del IGN complementa los predictores de OSM. Las particiones separan participantes,
parques o regiones; el test queda fuera del entrenamiento y la validación cruzada. No se
generan datos sintéticos: los datasets, entrenadores y modelos históricos con contexto
inventado o etiquetas por reglas fueron eliminados del repositorio.
Para reproducir los artefactos de investigación con el entorno `.venv-ai` preparado:

```bash
npm run train:ai
npm run validate:ai-data
npm run test:ai-data
```

Estos resultados no aprueban uso en campo: la app no incluye ningún modelo aprobado y su
motor de inferencia devuelve `sin_datos`. Los nuevos bosques mantienen sus etiquetas nativas
y alcance de investigación. Ver `ai/datasets/README.md` para instalación y descarga, y
`docs/ai-real-data-audit.md` para resultados y fuentes.

## Desviaciones conscientes respecto del documento del proyecto

- **TensorFlow Lite**: los modelos se exportan a un JSON portatil (arboles de un
  RandomForest) evaluado en TypeScript puro, no a `.tflite`. No hay una libreria de
  inferencia nativa en las dependencias de la app; agregarla implicaria un modulo nativo
  adicional fuera del alcance actual.
- **BLE nativo**: la integracion con wearables usa Apple HealthKit / Android Health
  Connect (APIs del sistema operativo) mas un simulador de desarrollo, no un
  emparejamiento BLE directo a dispositivo.
- **Infraestructura AWS real**: el codigo y `docker-compose.yml` reproducen la arquitectura
  de Amazon RDS (PostgreSQL) para desarrollo local; no hay una instancia de RDS desplegada
  como parte de este repositorio.
- **Emergencia**: el modo SOS persiste y sincroniza la alerta (ubicacion, hora, contacto),
  pero no dispara un envio real de SMS/telefonia — el propio documento excluye la
  automatizacion de respuesta de emergencia por organismos externos del alcance del
  prototipo.
