# MiSendero backend

API REST en Node.js + Express, persistida en PostgreSQL (ver ADR-03 del documento del
proyecto). Autenticacion con JWT, contrasenas con bcrypt, validacion de entrada con zod,
`helmet` y rate limiting en los endpoints de auth.

## Desarrollo local

```bash
docker compose up -d db      # desde la raiz del repo, levanta Postgres en localhost:5432
cp .env.example .env         # completar JWT_SECRET (ver comentario en el archivo)
npm install
npm run db:migrate           # aplica migrations/*.sql
npm run dev
```

`backend/data/` ya no almacena una base SQLite versionada: los datos viven en Postgres y se
siembran de forma idempotente al iniciar el servidor (`src/seed.js`).

## Endpoints principales

- `GET /api/health`
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/trails`, `GET /api/trails/:id`, `GET /api/trails/:id/weather`,
  `GET/POST /api/trails/:id/reports`, `POST /api/trails` (requiere rol `admin`)
- `GET/POST /api/activities` (requiere sesion)
- `GET/POST /api/emergency-alerts` (requiere sesion)

## Vigencia de reportes de terreno

Por la seccion 2.1.7.1 del documento del proyecto, los reportes obsoletos se descartan
automaticamente: `GET /:id/reports` excluye los mas viejos que `REPORT_STALE_AFTER_DAYS`
(default 30 dias, configurable por variable de entorno), y el servidor corre una limpieza
que los borra de la base cada 24hs (`src/cleanupStaleReports.js`), ademas de al iniciar.

## Aplicar dificultad de ruta entrenada

`training/route-difficulty/` (Python + Scikit-learn) genera predicciones de dificultad por
sendero en `training/route-difficulty/output/predictions.json`. Para llevarlas a la base:

```bash
npm run apply:route-difficulty
```

Es un script manual, no un endpoint HTTP: es una tarea de mantenimiento offline, no algo que
la app dispare en tiempo de ejecucion.

## Logging

El servidor usa `pino` (`src/logger.js`) para logs estructurados y `pino-http` para logging
de requests (desactivado en tests). Configurable con `LOG_LEVEL` (`info` por defecto).

## Tests

```bash
npm test
```

Los tests corren contra `pg-mem` (Postgres en memoria) en vez de una instancia real, por lo
que no requieren Docker ni una base de datos levantada.
