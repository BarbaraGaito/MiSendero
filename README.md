# MiSendero

Aplicacion movil (Expo/React Native) de asistencia y seguridad para trekking, con backend
Node.js/Express + PostgreSQL, modulo de IA entrenado en Python/Scikit-learn, mapas y navegacion
offline, y sincronizacion diferida de reportes, actividad y alertas de emergencia.

## Arranque rapido

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

```bash
npm test              # frontend: geoUtils, cola de sincronizacion offline, motor de IA
cd backend && npm test # backend: auth, trails, activities, emergency-alerts, limpieza de
                       # reportes obsoletos, aplicacion de dificultad de ruta (via pg-mem, sin Docker)
```

CI (`.github/workflows/ci.yml`) corre `npx tsc --noEmit` + `npm test` (frontend) y `npm test`
(backend) en cada push y pull request. Requiere Node 22+ (el mock de `expo-sqlite` usado en los
tests del frontend se apoya en `node:sqlite`).

## Modulo de IA (Python + Scikit-learn)

Los tres modelos (dificultad de ruta, fatiga, riesgo fisiologico) se entrenan con
RandomForest en `training/python/`. Para regenerar los artefactos que consume la app:

```bash
pip install -r training/python/requirements.txt
npm run train:ai
```

Ver `ai/datasets/README.md` y `training/route-difficulty/README.md` para el detalle del
pipeline y la limitacion documentada de datos sinteticos (los datasets de ejemplo son
pequenos; ver seccion 2.1.6.3 del documento del proyecto).

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
