# Descubrí tu sendero: recomendador propio

Encuesta de cinco etapas → una recomendación de PostgreSQL → fin. No hay chat, consultas libres posteriores, historial ni proveedor generativo. Se reutilizan navegación Expo Router (`/descubri-tu-sendero`), colores/componentes verdes, sesión y servicio HTTP existentes.

## Estado real

La auditoría local encontró 52 senderos, 35 elegibles y **cero pares etiquetados de preferencias/elecciones**. Hay un baseline operativo y un pipeline supervisado de Random Forest completamente implementado, pero aún no un recomendador personalizado entrenado con evidencia real suficiente. El entrenamiento se niega a fabricar etiquetas y deja métricas nulas. [Datos disponibles y fuentes externas](trail-ranking-2026-10-17/README.md).

Flujo: React Native → Express autenticado → `trails` de PostgreSQL → verificación/filtros → baseline o inferencia privada Python → ID de candidato → explicación con plantillas → JSON Zod → tarjeta única. No se usan ni se necesitan `OPENAI_API_KEY`, `OPENAI_MODEL` o `AI_TIMEOUT_MS`. Las variables antiguas pueden retirarse del entorno del servidor cuando ya no se requiera volver a una versión anterior; no se editaron archivos de secretos automáticamente.

El modelo es ranking supervisado *pointwise*, mediante `RandomForestRegressor`, entrenado fuera del servidor. La [documentación del módulo](../backend/ml/README.md) describe elección, etiquetas, características, métricas, particiones, mínimos, artefactos y límites de las conclusiones académicas.

## Encuesta y restricciones

1. Buscar/seleccionar un destino obtenido del catálogo elegible.
2. Elegir uno o varios paisajes; «Cualquiera» es exclusivo.
3. Seleccionar duración total de caminata; ida y vuelta cuando corresponda.
4. Elegir dificultad.
5. Declarar experiencia: Principiante, Intermedio o Avanzado.

Las respuestas se conservan al retroceder, corregir errores o buscar otro sendero. La carga muestra «Buscando el sendero ideal para vos...». Sin resultados se permite modificar las respuestas. No se relajan filtros para entregar una ruta arbitraria. Las travesías advierten que el regreso no está incluido; los circuitos y rangos oficiales se conservan. El aviso de Internet se muestra solo cuando el dispositivo detecta falta de conexión. No se agregan solicitudes a la cola offline ni se modifican mapas descargados.

Se exige procedencia revisada, fuente admitida, nombre/ubicación, distancia, dificultad y duración con alcance conocido. Los paisajes se toman de metadatos documentados o de descripciones positivas del catálogo. Los valores faltantes permanecen desconocidos. No se hacen búsquedas geográficas abiertas, no se crean nombres/coordenadas y no se deduce seguridad o apertura actual. El detalle sin traza GPS verificada muestra la ficha y sus fuentes, sin ofrecer un mapa descargable inexistente.

## Contrato HTTP

`GET /api/ai/destinations`, con Bearer token, devuelve `{ "destinations": [ ... ] }`. La cobertura depende de los registros verificados de la base consultada, no de una cantidad fija o una lista de ciudades inventadas.

`POST /api/ai/recommend-trail`, con Bearer token, cuerpo estricto <=2 KB:

```json
{
  "destination": "Misiones",
  "trailTypes": ["cascadas"],
  "duration": "2-4",
  "difficulty": "moderada",
  "experience": "intermedio"
}
```

| Campo | Valores |
|---|---|
| destination | Lugar del catálogo, 2–120 caracteres |
| trailTypes | naturaleza, montaña, cascadas, lagos, bosques, miradores, cualquiera |
| duration | menos-1, 1-2, 2-4, 4-6, mas-6, cualquiera |
| difficulty | facil, moderada, dificil, cualquiera |
| experience | principiante, intermedio, avanzado |

Para compatibilidad, los clientes antiguos que omiten experiencia usan el límite conservador de principiante. El frontend actualizado siempre la envía. Las franjas comparten fronteras inclusivas: 60–120, 120–240 y 240–360 minutos; menos de 60 y más de 360. Un rango publicado debe caber completo en la franja solicitada.

Respuesta 200: `{ "status": "ok", "message": "...", "recommendation": { ... }, "ranking": { "method": "baseline", "modelVersion": null } }`. Con un artefacto apto y disponible, `method` es `supervised` y contiene la versión. Esto identifica el método, no un porcentaje de confianza. `recommendation` es un solo objeto con el ID real, atributos, fuentes y 2–4 motivos basados en las coincidencias. No hay lista ni texto generado por un LLM.

`no_results`, `clarification` y `out_of_scope` devuelven `recommendation: null`. Una solicitud fuera de alcance recibe el mensaje restringido de MiSendero. Otros errores: 400 validación, 401 sesión, 413 tamaño, 429 límite, 503 saturación concurrente, 500 fallo de catálogo/servidor. Fallar el modelo no es un 500: se usa baseline.

Se mantienen 10 búsquedas por cuenta y 30 por IP cada 15 minutos, máximo cuatro concurrentes por proceso, plazo de lectura del catálogo de 5 segundos y respuestas `no-store`. Los límites están en memoria y requieren store compartido al escalar instancias. No se cambió `trust proxy`: verificar la configuración existente de Nginx; no habilitar confianza indiscriminada en encabezados de IP del cliente.

## Configuración y pruebas locales

Conservar `DATABASE_URL`/PG*, `JWT_SECRET`, `PORT`, CORS y el resto del entorno existente. No cambiar `EXPO_PUBLIC_API_URL` si la app debe seguir apuntando a AWS. En `backend/.env` solo son nuevas estas variables opcionales de servidor:

```dotenv
# Vacío: baseline, sin requerir Python ni artefacto.
TRAIL_ML_MODEL_DIR=
TRAIL_ML_PYTHON=python3
TRAIL_ML_TIMEOUT_MS=1500
```

Con modelo futuro: usar rutas absolutas al intérprete del venv y al directorio versionado del artefacto. Plazo de inferencia limitado a 100–5000 ms. Nunca poner estas rutas ni credenciales en variables `EXPO_PUBLIC_*`.

Desde la raíz:

```powershell
npm --prefix backend ci --ignore-scripts
npm --prefix backend run build
npm run typecheck
npm --prefix backend test -- --runInBand
npm test -- --runInBand
py -m unittest discover -s backend/ml/tests -v
```

El baseline no necesita instalar Python. Para entrenar o verificar el worker, crear el entorno indicado en [el módulo ML](../backend/ml/README.md). La auditoría `npm --prefix backend run ranking:prepare` es de lectura y no carga datos ni ejecuta migraciones.

También se puede ejecutar `npm --prefix backend run ranking:smoke`: usa HTTP local y PostgreSQL real local, firma un token efímero de una cuenta local existente y comprueba que la recomendación corresponda al mismo registro. No imprime el token ni escribe en la base. Rechaza destinos de base remotos y requiere que el catálogo local tenga la consulta de prueba documentada.

Si se inicia el backend local: `npm --prefix backend run dev`. Su comportamiento de desarrollo conserva las inicializaciones existentes; **no usarlo con RDS**. En producción `NODE_ENV=production` omite migraciones y seeds al arrancar. Para `npm start`, compilar previamente. No se añadió ninguna migración.

Expo contra AWS, después de actualizar el backend allí:

```powershell
npx expo start --go --lan --clear
```

Iniciar sesión → Inicio/Explorar → Descubrí tu sendero. Probar Misiones/Cascadas/2–4 h/Moderada/Intermedio. Con la ampliación de catálogo cargada en esa base también probar Corrientes/Lagos/2–4 h/Moderada/Intermedio o Neuquén/Montaña/>6 h/Difícil/Avanzado. Una base sin esos registros puede devolver sin resultados correctamente. Principiante con dificultad Difícil debe dar sin coincidencias, nunca sustituir por una ruta exigente. Probar destino cubierto, cambio de respuestas, resultado único, acceso al detalle, modo avión y reconexión.

## AWS EC2: actualización con systemd y Amazon RDS

Procedimiento **para ejecutar manualmente tras revisar las rutas del servidor**. Esta implementación no se conectó a EC2/RDS, no desplegó ni modificó producción. No ejecutar migraciones o seeds durante estos pasos. La ampliación local de senderos es independiente; no se copia una base local encima de RDS.

Inspeccionar primero:

```bash
sudo systemctl cat misendero.service
sudo systemctl show misendero.service -p User -p WorkingDirectory -p ExecStart -p EnvironmentFiles
command -v node
python3 --version
```

Conservar el EnvironmentFile que ya contiene la conexión RDS y los secretos; no imprimirlo ni reemplazarlo por ejemplos. Anotar release/revisión anterior, usuario del servicio, ruta real de Node y archivo de configuración vigente. Si se va a instalar Python para inferencia, usar 3.11 o 3.12 con venv; los paquetes concretos del sistema dependen de la distribución. No es necesario instalarlo para activar inicialmente el baseline.

Preparar un checkout separado del release, sin cambiar los archivos que está ejecutando el servicio. Ejemplo, reemplazando rutas/revisión por las reales y usando una ruta de candidato nueva:

```bash
git -C /ruta/repositorio fetch origin
git -C /ruta/repositorio worktree add --detach /ruta/releases/recomendador-v1 REVISION_REVISADA
cd /ruta/releases/recomendador-v1/backend
npm ci --ignore-scripts
npm run build
npm test -- --runInBand
```

Las pruebas usan pg-mem con `NODE_ENV=test`; no realizan cambios en RDS. No iniciar el candidato con `npm run dev`. Publicar previamente estos cambios en la revisión revisada; este trabajo no hizo commits ni pushes automáticos.

Para el futuro artefacto apto, instalar dependencias en un venv del release con el mismo Python menor y versiones de entrenamiento:

```bash
python3.12 -m venv /ruta/releases/recomendador-v1/.venv-trail-ranking
/ruta/releases/recomendador-v1/.venv-trail-ranking/bin/python -m pip install -r /ruta/releases/recomendador-v1/backend/ml/requirements.lock.txt
/ruta/releases/recomendador-v1/.venv-trail-ranking/bin/python /ruta/releases/recomendador-v1/backend/ml/inspect_artifact.py /ruta/modelos/VERSION_REVISADA
```

Usar `python3.11` si esa fue la versión de entrenamiento. Copiar únicamente artefactos propios revisados a un directorio versionado legible por el usuario del servicio. El inspector debe dar `ready` antes de configurar `TRAIL_ML_MODEL_DIR`. Hoy, sin etiquetas, dejarlo vacío. No desplegar las fixtures sintéticas ni un modelo `deployable: false`.

Para conmutar el servicio, crear un drop-in específico. Si ya existe ese nombre, respaldarlo y revisarlo antes de editar. Conservar el usuario, dependencias, límites y EnvironmentFile existentes:

```bash
sudo install -d /etc/systemd/system/misendero.service.d
sudoedit /etc/systemd/system/misendero.service.d/50-trail-ranker.conf
```

Contenido orientativo con **rutas reales absolutas** y la conexión/secretos existentes conservados:

```ini
[Service]
WorkingDirectory=/ruta/releases/recomendador-v1/backend
# Añadir esta línea solo si el servicio anterior cargaba .env exclusivamente con dotenv:
# EnvironmentFile=/ruta/anterior/backend/.env
ExecStart=
ExecStart=/usr/bin/env NODE_ENV=production /ruta/absoluta/node /ruta/releases/recomendador-v1/backend/src/server.js
Environment=TRAIL_ML_MODEL_DIR=
Environment=TRAIL_ML_TIMEOUT_MS=1500
# Solo cuando exista un artefacto apto:
# Environment=TRAIL_ML_PYTHON=/ruta/releases/recomendador-v1/.venv-trail-ranking/bin/python
# Environment=TRAIL_ML_MODEL_DIR=/ruta/modelos/VERSION_REVISADA
```

Si el comando actual contiene flags o un wrapper necesario, preservarlos al adaptar `ExecStart`. Las variables de un EnvironmentFile pueden prevalecer sobre `Environment`: evitar definiciones duplicadas de `TRAIL_ML_*` en la configuración activa. `NODE_ENV=production` se fija al invocar Node para impedir inicializaciones de desarrollo, incluso si el archivo antiguo tenía otro valor. No tocar `DATABASE_URL` ni sustituirlo por localhost.

```bash
sudo systemctl daemon-reload
sudo systemctl restart misendero.service
sudo systemctl status misendero.service --no-pager
sudo journalctl -u misendero.service -n 50 --no-pager
curl --fail http://127.0.0.1:3001/api/health
```

Adaptar el puerto al ya configurado. Nginx mantiene el proxy existente a Express: no hay puerto Python nuevo ni cambio de dominio. Verificar también `/api/health` por la URL HTTPS pública y una encuesta autenticada. Si `destinations` o `recommend-trail` dan 404, la revisión nueva no está atendiendo esa URL; no es ausencia de senderos.

Prueba HTTP manual con un token de una cuenta de prueba y la URL real:

```bash
API_BASE='https://DOMINIO_EXISTENTE/api'
TOKEN='TOKEN_DE_SESION_DE_PRUEBA'
curl --fail "$API_BASE/ai/destinations" -H "Authorization: Bearer $TOKEN"
curl --fail "$API_BASE/ai/recommend-trail" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' --data '{"destination":"Misiones","trailTypes":["cascadas"],"duration":"2-4","difficulty":"moderada","experience":"intermedio"}'
```

Un `no_results` puede ser correcto si RDS no tiene candidatos compatibles/documentados. No sincronizarla mediante el seed general para resolverlo. El backend siempre lee su catálogo real.

## Reversión

Para desactivar solo ML y conservar la nueva encuesta, dejar `TRAIL_ML_MODEL_DIR` vacío en la configuración efectiva y reiniciar. La API queda con baseline, sin cambiar la base.

Para volver al release anterior, retirar únicamente el drop-in nuevo (o restaurar su respaldo si existía) y reiniciar. Si el archivo fue creado en este despliegue:

```bash
sudo mv /etc/systemd/system/misendero.service.d/50-trail-ranker.conf /etc/systemd/system/misendero.service.d/50-trail-ranker.conf.disabled
sudo systemctl daemon-reload
sudo systemctl restart misendero.service
sudo systemctl status misendero.service --no-pager
```

Conservar el checkout y el entorno anteriores hasta validar el nuevo release. No hay rollback SQL, borrado de tablas ni cambio de credenciales porque esta implementación no cambia el esquema o los datos de producción. Un frontend nuevo requiere `/ai/destinations`; al volver a un backend anterior revertir también la versión móvil correspondiente.

## Docker opcional

El Dockerfile conserva una imagen por defecto con Node y baseline. Copia el código del worker pero no exige Python. Para una imagen con inferencia CPU instalar explícitamente las dependencias: `docker build --build-arg INSTALL_TRAIL_ML=true -t misendero-backend:ranking backend`. Montar un artefacto propio revisado como solo lectura y configurar `TRAIL_ML_MODEL_DIR`; el Python del venv está en `/opt/trail-ml/bin/python`. No se construyó ni publicó esa imagen en esta sesión.

## Archivos principales

- `backend/src/ai/{contracts,schemas,catalog,features,assistant,model}.ts` y `featureSpec.json`: contrato, catálogo, filtros, vectores, baseline, explicación y control del worker.
- `backend/src/routes/ai.routes.js`, `backend/src/server.js`: endpoints, límites, lectura con plazo y arranque sin seed/migraciones en producción.
- `backend/ml/{ranking,train,serve,inspect_artifact}.py`, lock de dependencias y pruebas: ML offline, evaluación, artefactos e inferencia.
- `backend/scripts/prepareTrailRanking.js`: dataset basado en catálogo y etiquetas revisadas; sin escrituras en PostgreSQL.
- `mobile/screens/DiscoverTrailScreen.tsx`, `services/{api,trailAssistant}.ts`: cinco preguntas, destinos cubiertos y envío de experiencia.
- Tests de recomendación, worker, servicios y encuesta; ejemplos de entorno y soporte opcional Docker.
