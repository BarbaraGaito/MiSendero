# MiSendero backend

API REST en Node.js + Express, persistida en PostgreSQL (ver ADR-03 del documento del
proyecto). Autenticacion con JWT, contrasenas con bcrypt, validacion de entrada con zod,
`helmet` y rate limiting en los endpoints de auth.

El asistente **Descubrí tu sendero** utiliza una encuesta de cuatro pasos y devuelve
un sendero verificado mediante `POST /api/ai/recommend-trail` (requiere sesión).
Configurar `OPENAI_API_KEY`, `OPENAI_MODEL` y, opcionalmente, `AI_TIMEOUT_MS` únicamente
en el servidor. Ver la [guía de configuración, pruebas y AWS](../docs/trail-recommendation.md).
El servicio nuevo está escrito en TypeScript: `npm run dev` lo compila automáticamente;
antes de ejecutar `npm start` manualmente, ejecutar `npm run build`. Docker ya lo compila.

## Desarrollo local

Con Docker, desde la raiz del repositorio:

```bash
cp .env.example .env
docker compose up --build
```

Esto levanta PostgreSQL y el backend. El servidor aplica migraciones y seed al iniciar, y
queda disponible en `http://localhost:3001/api/health`.

Para usar una imagen ya publicada del backend en lugar de construir desde codigo local:

```bash
cp .env.example .env
# editar MISENDERO_BACKEND_IMAGE en .env, por ejemplo:
# ghcr.io/barbaragaito/misendero-backend:latest
docker compose -f docker-compose.images.yml up
```

Para desarrollo manual:

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

## Logging

El servidor usa `pino` (`src/logger.js`) para logs estructurados y `pino-http` para logging
de requests (desactivado en tests). Configurable con `LOG_LEVEL` (`info` por defecto).
Los logs HTTP omiten URL, IP, headers y cuerpo; los errores omiten detalles SQL y existe
redacción adicional de credenciales, contactos y coordenadas. Revisar también el recolector
y su conservación: esta configuración no demuestra el estado de la infraestructura publicada.

## Cuenta, privacidad y moderación

`DELETE /api/auth/me` exige sesión y contraseña actual en JSON. Elimina la cuenta y sus
datos asociados, incluidos reportes con textos/nombres, actividades, planes y avisos pendientes.
Cada solicitud autenticada consulta la existencia y el rol actual de la cuenta.

`GET /api/auth/me/data` exporta datos remotos del titular; `PATCH /api/auth/me` permite
actualizar el nombre. `POST /api/auth/me/privacy-decisions` registra decisiones versionadas
por finalidad con fecha del cliente y recepción del servidor.

El recurso `/account-deletion` permite estas acciones desde la web. Configurar
`PRIVACY_CONTACT_URL` con el canal atendido del responsable para otros derechos y contactos.
Un administrador autenticado puede revisar denuncias y ocultar/restaurar reportes desde
esa misma página. Su rol se comprueba en la base de datos.

`POST /api/reports/:id/flag`, `POST /api/reports/:id/block-author`,
`DELETE /api/reports/:id`, `PATCH /api/reports/:id`, `GET /api/reports/moderation` y
`POST /api/reports/:id/moderate` gestionan denuncias, bloqueo, retiro, corrección y moderación.
La lista pública omite datos del autor y distingue observación, recepción, corrección y
vencimiento; con sesión informa `is_mine` y aplica los bloqueos del titular.

Ver [evidencia y pendientes](../docs/implementacion-privacidad-2026-10-16.md) antes de
dar por cerrado cualquier requisito legal o de distribución. No se ensayaron aquí
infraestructura publicada ni restauración de respaldos.

## Tests

```bash
npm test
```

Los tests corren contra `pg-mem` (Postgres en memoria) en vez de una instancia real, por lo
que no requieren Docker ni una base de datos levantada.
