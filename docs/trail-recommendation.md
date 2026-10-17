# Descubrí tu sendero

Implementación de encuesta de cuatro etapas con **una única recomendación**. No hay chat, historial, campos de consultas ni endpoint de conversación. Accesos: Inicio → Descubrí tu sendero, o Explorar → Descubrí tu sendero. Ruta Expo Router: `/descubri-tu-sendero`.

## Arquitectura y datos

React Native → `services/trailAssistant.ts` → API autenticada `POST /api/ai/recommend-trail` → catálogo PostgreSQL → filtros verificables → OpenAI Responses API con JSON Schema estricto → validación Zod → tarjeta única.

El catálogo proviene de `trails`, cargado por el seed existente desde `backend/src/data/additionalTrailDefinitions.js`, `additionalTrails.js` y las trazas de OpenStreetMap documentadas en `additionalTrailRoutes.json`. Se exige `provenance`, fecha de revisión, fuentes HTTPS de los organismos/operadores admitidos, distancia positiva y una base explícita para la duración total. Se excluyen los registros antiguos sin procedencia, las estimaciones de planificación sin referencia oficial de duración y los registros incompletos. La clasificación de paisajes se deriva de los nombres y las descripciones positivas del catálogo; no se consideran las variantes que la descripción excluye.

Se filtra primero por el lugar y sus alias locales documentados (por ejemplo, Bariloche → Refugio Frey; Ushuaia → los recorridos registrados de Tierra del Fuego), después por al menos una experiencia seleccionada, duración total y dificultad. Las preferencias explícitas son obligatorias: no se relajan silenciosamente. La IA elige un ID entre los candidatos con mayor coincidencia de experiencias. Una duración de ida y vuelta no se vuelve a duplicar. En recorridos que terminan en otro punto se aclara que la duración cubre solo la ida y que hay que coordinar transporte.

No se hacen búsquedas geográficas abiertas ni se completan coordenadas. Los destinos desconocidos devuelven `no_results`; destinos demasiado amplios como “Patagonia” devuelven `clarification` y permiten editar la misma pregunta. La cobertura depende del catálogo, no de los conocimientos generales del modelo. Por ejemplo, **Bariloche + lagos + 2–4 h + fácil actualmente puede devolver sin resultados**; no se sustituye por Frey, cuya duración y dificultad no coinciden.

La IA genera la explicación mediante un plan estructurado de motivos (`destination`, `landscape`, `duration`, `difficulty`). El servidor convierte ese plan en oraciones naturales con los valores del sendero y los filtros del usuario. Esta restricción evita publicar texto libre que contenga afirmaciones inventadas: nombres, tiempos, dificultad, distancia, imagen y enlace salen exclusivamente del registro real. La selección y el orden de los motivos sí los procesa el modelo. Se usa `store: false` y no se envían tokens de sesión, correos ni otros datos de la cuenta al proveedor.

La integración sigue la [documentación oficial de Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Se llama a OpenAI desde el servidor mediante `fetch`, sin SDK adicional. El modelo se configura explícitamente; el ejemplo usa `gpt-4o-mini`, y puede reemplazarse por otro compatible con Responses y JSON Schema estricto que esté habilitado para la cuenta.

## Configuración local

En `backend/.env` para el servidor local, o en `.env` de la raíz para Docker Compose:

```dotenv
OPENAI_API_KEY=tu_clave_privada_del_servidor
OPENAI_MODEL=gpt-4o-mini
AI_TIMEOUT_MS=12000
```

No colocar la clave en variables `EXPO_PUBLIC_*`, código móvil, repositorio, imágenes Docker ni logs. Conservar `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGIN` y demás configuración existente. El timeout se limita al intervalo 1–20 segundos; el cliente espera hasta 25 segundos. Si no se configura la IA, el endpoint devuelve 503 al intentar generar una coincidencia; nunca simula una respuesta de IA.

Desde la raíz, para desarrollo local (abrir Docker Desktop y esperar a que su motor esté iniciado antes de levantar PostgreSQL):

```powershell
npm ci --legacy-peer-deps --ignore-scripts
npm --prefix backend ci --ignore-scripts
docker compose up -d db
npm --prefix backend run db:migrate
npm --prefix backend run db:seed
npm --prefix backend run dev
```

`dev` compila el servicio TypeScript antes de iniciar el servidor existente. Al editar los archivos `backend/src/ai/*.ts`, volver a ejecutar `npm --prefix backend run build` y reiniciar el backend. Para ejecutar directamente `npm --prefix backend start`, compilar primero con ese mismo comando. No se agregaron migraciones de base de datos.

En otra terminal, con `EXPO_PUBLIC_API_URL` apuntando al backend (incluye `/api`; usar la IP LAN de la computadora cuando se prueba en teléfono):

```powershell
npx expo start --go --lan
```

Si `.env` apunta a AWS y se quiere probar el backend local, crear `.env.development.local` en la raíz con `EXPO_PUBLIC_API_URL=http://IP_LAN_DE_LA_PC:3001/api`. Ese archivo está ignorado por Git y solo se aplica al entorno de desarrollo. Reiniciar Expo con `npx expo start --go --lan --clear` después de cambiar la URL. Para probar contra AWS, quitar esa configuración local y actualizar primero el backend desplegado. Una versión anterior del servidor devuelve 404 para el endpoint de IA; eso no indica que no existan senderos.

Usar un único backend en el puerto 3001: si Docker ya lo ocupa, reconstruirlo con `docker compose up -d --build backend`; no iniciar simultáneamente `npm --prefix backend run dev` en ese puerto. Las claves de `.env` raíz se aplican al contenedor, mientras que el inicio manual usa `backend/.env`.

Iniciar sesión, abrir Inicio o Explorar y completar la encuesta. Ejemplo con coincidencia actual: **El Chaltén → Lagos o lagunas → Entre 1 y 2 horas → Fácil**, que puede elegir Mirador de las Águilas. Otro ejemplo: **Misiones → Cascadas → Entre 2 y 4 horas → Moderada**, para Macuco. Comprobar que “Ver sendero” abre el registro real y “Buscar otro sendero” permite revisar las respuestas guardadas durante esa visita. No hay persistencia de conversaciones ni de encuestas.

El aviso de conexión aparece únicamente cuando el dispositivo detecta que no tiene Internet y desaparece al reconectarse. Con modo avión, el envío informa que hace falta Internet, conserva las respuestas en pantalla y permite reintentar; no se agrega a la cola offline. Los mapas descargados y demás funciones offline conservan sus flujos existentes.

## Contrato HTTP

Requiere `Authorization: Bearer <token de sesión>`. El cuerpo es estricto, máximo 2 KB, con destino de 2–120 caracteres:

```json
{
  "destination": "El Chaltén",
  "trailTypes": ["lagos"],
  "duration": "1-2",
  "difficulty": "facil"
}
```

Valores admitidos:

| Campo | Valores |
| --- | --- |
| trailTypes | naturaleza, montaña, cascadas, lagos, bosques, miradores, cualquiera |
| duration | menos-1, 1-2, 2-4, 4-6, mas-6, cualquiera |
| difficulty | facil, moderada, dificil, cualquiera |

`cualquiera` en tipos es exclusivo. Las franjas de tiempo usan minutos totales: menos de 60; 60–120; 120–240; 240–360; más de 360. Las fronteras compartidas son inclusivas.

Respuesta `200`: `{ "status": "ok", "message": "¡Encontramos un sendero para vos!", "recommendation": { ... } }`. Contiene un objeto, nunca un listado. Estados `no_results`, `clarification` y `out_of_scope` incluyen un mensaje y `recommendation: null`. Errores: 400 validación/JSON incorrecto, 401 sesión ausente o inválida, 413 cuerpo extenso, 429 límite de búsquedas, 503 proveedor ocupado/no configurado/timeout/respuesta inválida. La respuesta del proveedor no se reenvía al cliente.

Se aplican 10 solicitudes por cuenta y 30 por IP cada 15 minutos, y hasta cuatro búsquedas concurrentes por proceso. Estos límites usan memoria del proceso; al escalar a varias instancias, configurar además un límite compartido en la infraestructura o un store centralizado. No se habilita confianza indiscriminada en `X-Forwarded-For`: detrás de un proxy las IP pueden compartir el presupuesto, mientras que cada cuenta mantiene su límite individual. No hay configuración nueva de proxy/puertos/CORS.

El destino admite nombres de lugares, no instrucciones: longitud, caracteres, número de palabras y patrones de cambio de rol se validan antes del proveedor. Además, únicamente se envían candidatos que ya coinciden con el destino; el modelo no tiene herramientas ni recibe un historial. La salida debe tener un ID admisible y un plan de motivos enumerados, sin texto libre ni campos adicionales.

## Pruebas

```powershell
npm run typecheck
npm --prefix backend run build
npm test -- --runInBand
npm --prefix backend test -- --runInBand
```

Las pruebas agregadas cubren selección desde registros reales del seed, cambios de respuestas, restricciones temáticas/inyección, destino sin datos, ambigüedad, incompatibilidad de filtros, ida y vuelta/solo ida, validación de entrada y salida, claves ausentes, timeout, errores del proveedor, sesión, rate limiting, progreso, edición, carga, navegación real e imagen fallida. El proveedor de IA está simulado en las pruebas: no se consumen créditos ni se requieren claves reales. La integración real con OpenAI y la instalación móvil requieren configurar la clave y ejecutar la prueba manual indicada.

## AWS y Docker

Se mantiene el despliegue existente. `docker-compose.yml` y `docker-compose.images.yml` ya pasan `.env` mediante `env_file`; las tres variables nuevas llegan al contenedor sin modificar puertos, base de datos o infraestructura. El Dockerfile agrega una etapa de compilación TypeScript y copia `dist/ai` a la imagen final, que mantiene dependencias de producción y usuario `node`.

En el servidor que construye desde código:

```powershell
docker compose up -d --build backend
```

Si AWS usa la imagen publicada por el flujo existente de GitHub, publicar primero una nueva versión con estos cambios y en el host:

```powershell
docker compose -f docker-compose.images.yml pull backend
docker compose -f docker-compose.images.yml up -d backend
```

Configurar la clave únicamente en el entorno del servidor/servicio (o mecanismo de secretos ya utilizado), acceso saliente HTTPS a `api.openai.com`, y `OPENAI_MODEL` habilitado en esa cuenta. El arranque existente ejecuta migraciones y seed. No cambiar ni reemplazar la base de datos. Comprobar `/api/health` y después realizar una encuesta autenticada desde Expo contra la URL HTTPS de AWS. Para una instalación sin Docker: `npm ci --ignore-scripts`, `npm run build`, reiniciar con el comando de servicio existente que ejecuta `npm start`.

Esta implementación no despliega recursos ni modifica secretos de AWS automáticamente.

## Archivos

- Encuesta y tarjeta: `app/descubri-tu-sendero.tsx`, `mobile/screens/DiscoverTrailScreen.tsx`, `mobile/components/TrailRecommendationCard.tsx`.
- Navegación: `app/_layout.tsx`, `mobile/screens/HomeScreen.tsx`, `mobile/screens/ExploreRoutesScreen.tsx`.
- Cliente y contrato compartido: `services/api.ts`, `services/trailAssistant.ts`, `backend/src/ai/contracts.ts` (importación de tipos solamente en Expo).
- Servidor: `backend/src/routes/ai.routes.js`, `backend/src/server.js`, `backend/src/ai/{schemas,catalog,model,assistant}.ts`.
- Compilación y pruebas: `backend/tsconfig.ai.json`, `backend/package.json`, `backend/package-lock.json`, `backend/Dockerfile`, `backend/jest.config.js`, `backend/tests/typescriptTransformer.cjs`.
- Casos de prueba: `backend/tests/aiRecommendations.test.js`, `services/__tests__/trailAssistant.test.ts`, `mobile/screens/__tests__/DiscoverTrailScreen.test.tsx`.
- Configuración y guía: `.env.example`, `backend/.env.example`, `docs/trail-recommendation.md`.
- Referencias desde el proyecto: `README.md`, `backend/README.md`.
