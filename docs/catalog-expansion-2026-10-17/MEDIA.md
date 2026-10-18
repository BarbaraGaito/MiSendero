# Corrección de fotos y cartografía del lote nuevo

Revisión del 17/10/2026. Se comprobó PostgreSQL **local**, sin conectar a RDS ni cambiar producción.

El problema era de datos: los 20 registros del lote `catalog-2026-10-17` tenían `image_url` y `route_coordinates` en NULL. Explorar y Detalle sustituían la imagen faltante por una foto de stock. No había una traza oculta que habilitar.

## Resultado local

- 19 fichas actualizadas con URL de imagen distinta, crédito, licencia, contexto y SHA-256 del archivo revisado.
- 19 geometrías con fuente, alcance y procedencia. No se interpolaron puntos para cerrar huecos ni se conectaron segmentos desconectados.
- Piedra Movediza, Lihué Calel, retirada a pedido de la propietaria porque no se encontró una traza digital verificable. Su definición permanece solo como antecedente de auditoría en `retiredDefinitions`; no vuelve a importarse.
- Total: **51 senderos = 32 anteriores + 19 del lote**. Se conservaron los IDs de los restantes y los 32 registros anteriores completos.
- Las fichas muestran la presentación habitual y el mapa disponible, sin un cartel de ruta incompleta. Los datos de procedencia conservan el alcance del archivo; una referencia parcial no se convierte en una traza completa por cambiar su presentación. El inicio de navegación continúa deshabilitado donde `mapping.navigation_ready` es `false`.

Las imágenes de APN son fotografías reales del parque correspondiente; varias representan el **entorno**, no el sendero exacto. La ficha lo identifica junto a la foto y conserva sus créditos. Cuatro selecciones provienen de Wikimedia Commons y documentan el lugar concreto. No se generaron imágenes con IA ni se atribuyó una foto de otro parque al sendero.

## Fuentes y límites

- [Mapas de áreas protegidas de APN](https://www.argentina.gob.ar/parquesnacionales): capas vectoriales publicadas en los mapas institucionales, con enlaces directos en `provenance.mapping`. Los datos vectoriales no equivalen a un GPS relevado por MiSendero.
- [Circuitos de Península Belgrano](https://trekkingperitomoreno.com/sendero-peninsulabelgrano/): GPX oficiales de los circuitos Chico y Grande. Se conservaron sus cabeceras originales; no se dibujó un cierre recto.
- [OpenStreetMap](https://www.openstreetmap.org/copyright): Che Roga, Laguna Escondida, variante Villa Tacul y etapa Rosales–San Martín, sobre nodos conectados. Se excluyó la senda cerrada por revegetación de Laguna Escondida y el miembro desconectado de la relación Rosales.
- Fotografías: páginas institucionales APN y páginas de archivo de Commons. Crédito, licencia y fuente están en `catalogExpansionPhotos20261017.json`. Para el contenido institucional se documenta la [Disposición 14/2018](https://www.argentina.gob.ar/normativa/nacional/disposici%C3%B3n-14-2018-313616/texto), respetando las licencias particulares de Commons.

Las distancias de las fichas conservan lo publicado por las fuentes; `mapping.distance_km` mide exclusivamente la geometría dibujada. No se alteró una cifra oficial para hacerla coincidir con el mapa. No se generaron desniveles acumulados ni datos actuales de seguridad. La página de actividades de Los Alerces consultada informaba un cierre de Cerro Cocinero por incendio; se conservó esa observación fechada y su fuente, sin afirmar que esté abierto.

La revisión diferencia 11 itinerarios continuos y 8 referencias cuyo alcance completo no se pudo confirmar: Tapé Porá, Patitos, Farallones, Leoncito, Alto El Petiso, Arroyo del Hacha, Cocinero y Rosales. Los metadatos detallan el motivo por registro. No se deben presentar estos ocho como recorridos GPS completos verificados en evaluaciones de la tesis.

## Archivos

- `backend/src/data/catalogExpansion20261017.js`: datos de las fichas, exclusión y unión con imágenes/geometrías.
- `catalogExpansionPhotos20261017.json`: selección fotográfica y atribución.
- `catalogExpansionRoutes20261017.json`: geometrías, fuentes y alcance.
- `catalogExpansionEvidence20261017.json`: selección de las geometrías originales utilizadas, sin identificadores personales de colaboradores OSM. Conserva los hashes de las descargas originales.
- `backend/scripts/buildExpansionRoutes.js`: reconstrucción reproducible desde esa evidencia, sin Internet ni generación de coordenadas.
- `backend/scripts/updateCatalogExpansionMedia.js`: corrección transaccional del lote existente y retirada de la única ficha solicitada.

## Verificación

Desde la raíz:

```powershell
node backend/scripts/buildExpansionRoutes.js --verify
npm --prefix backend test -- --runInBand catalogExpansion
npm test -- --runInBand catalogueScreens routeAndReportScreens TrailStartTestingMode
npm run typecheck
```

El corrector conserva los hechos nativos, los datos de entrenamiento y metadatos ajenos a la revisión. Valida identidad por lote, clave y nombre; no depende de IDs locales. Antes de retirar la ficha consulta todas las claves foráneas y rechaza la operación si hay actividades, reportes u otros datos relacionados. No ejecuta DELETE en cascada ni borra datos de usuarios. Una ejecución repetida no actualiza nuevamente las fichas.

El respaldo anterior y el informe de aplicación local están en `tmp/expansion-review/`, excluidos de Git. Esos archivos contienen solamente registros del catálogo, no credenciales.

La [verificación local conservada](LOCAL-VERIFICATION.json) compara los 32 registros originales por SHA-256 antes y después, documenta 52 → 51 y confirma 19 URLs distintas y 19 geometrías. Las pruebas de esta revisión pasaron: backend completo, 20 suites y 216 pruebas; pantallas de catálogo, mapa e inicio, 29 pruebas; verificación TypeScript de la aplicación y compilación del backend.

## Actualizar AWS

El archivo **`correccion-senderos-20261017.tar.gz`** contiene los dos scripts del corrector/importador y los tres archivos de datos que requieren en ejecución. No contiene `.env`, claves, dependencias, servidor ni cambios de configuración.

Desde PowerShell:

```powershell
scp -i "C:\RUTA\TU-CLAVE.pem" .\correccion-senderos-20261017.tar.gz USUARIO_EC2@18.218.87.168:~/
ssh -i "C:\RUTA\TU-CLAVE.pem" USUARIO_EC2@18.218.87.168
```

En EC2, identificar la carpeta del backend y su archivo de entorno, sin mostrar secretos:

```bash
sudo systemctl show misendero.service -p WorkingDirectory -p EnvironmentFiles
cd /RUTA/REAL/DEL/BACKEND
```

Antes de actualizar, guardar una copia de esos cinco archivos y un respaldo del catálogo con las herramientas habituales de RDS/PostgreSQL. No restaurar toda la base para revertir solo este lote.

```bash
tar -czf ~/catalogo-archivos-antes-media.tar.gz scripts/importCatalogExpansion.js src/data/catalogExpansion20261017.js
tar -xzf ~/correccion-senderos-20261017.tar.gz
NODE_ENV=production node scripts/updateCatalogExpansionMedia.js --remote --dry-run
```

Si el servicio usa un archivo de entorno externo, usar **el mismo** antes del nombre del script, tanto para vista previa como para aplicar:

```bash
NODE_ENV=production node --env-file=/RUTA/REAL/ENTORNO scripts/updateCatalogExpansionMedia.js --remote --dry-run
```

No cambiar `DATABASE_URL`, las variables `PG*` ni SSL. El corrector usa la conexión ya configurada. La salida no muestra usuarios ni contraseñas. Debe mostrar la base RDS esperada, 19 actualizaciones, la retirada exclusiva de Piedra Movediza y `projectedAfter: 51` si la base contiene los 52 registros originales. Si esa ficha tiene datos relacionados, la operación se cancela para preservarlos; no forzar su borrado.

Copiar el valor **exacto** de `target` en la aplicación:

```bash
NODE_ENV=production node scripts/updateCatalogExpansionMedia.js --remote --apply --confirm-target='TU-ENDPOINT-RDS:5432/TU-BASE'
NODE_ENV=production node scripts/updateCatalogExpansionMedia.js --remote --dry-run
```

Conservar también `--env-file` en ambos comandos si se utilizó. El resultado debe mostrar 51 registros, 19 imágenes y 19 geometrías para el lote, y `otherRowsPreserved: true`. La segunda vista previa debe tener `updated: []` y `withdrawn: []`.

Verificación pública:

```bash
curl --fail --silent --show-error https://18-218-87-168.sslip.io/api/trails | node -e 'let s="";process.stdin.on("data",c=>s+=c);process.stdin.on("end",()=>{const rows=JSON.parse(s);const batch=rows.filter(t=>t.provenance?.catalog_batch==="catalog-2026-10-17");console.log({total:rows.length,lote:batch.length,fotos:batch.filter(t=>t.image_url).length,mapas:batch.filter(t=>t.route_coordinates&&JSON.parse(t.route_coordinates).length>1).length})})'
```

No es necesario reiniciar Nginx, el servicio Node ni ejecutar seeds o migraciones para corregir estos datos. Para mostrar los cambios de interfaz, recargar Expo desde el código actualizado:

```powershell
npx expo start --clear
```

La app sigue usando su URL de AWS. Los mapas descargados previamente conservan su copia offline; estos 19 antes no tenían mapas descargables. No se borran descargas existentes.

## Reversión

Un error antes de COMMIT revierte la transacción completa. Si se interrumpe la conexión durante la confirmación, repetir la vista previa antes de reintentar: el proceso es idempotente. Para una reversión posterior, restaurar **solo** los campos de imágenes, cartografía y procedencia de las fichas del lote desde el respaldo previo, y revisar la restitución de Piedra Movediza por clave, no por rango de IDs. Conservar actividades, reportes, usuarios y las otras 32 rutas. La copia de archivos anterior no revierte datos; tampoco reinstalar el seed general.
