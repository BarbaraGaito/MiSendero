# Cargar los 20 senderos en RDS desde EC2

> Este procedimiento describe la importación inicial. Si ya cargaste el lote, usar [la corrección de fotos y cartografía](MEDIA.md). Esa revisión retira Piedra Movediza por pedido de la propietaria y deja 51 fichas. No volver a subir el paquete inicial para corregir registros existentes: el importador omite duplicados.

La API pública consultada el 17/10/2026 devolvía 32 senderos y ninguno del lote nuevo. Los 52 registros de la auditoría correspondían al PostgreSQL local. Este procedimiento inserta únicamente las fichas faltantes del lote `catalog-2026-10-17`, conserva las anteriores y omite duplicados por clave/nombre/alias. No ejecuta seeds ni migraciones. No se ejecutó contra producción durante la preparación.

## Subir el paquete

El archivo `catalogo-rds-20261017.tar.gz` contiene solamente:

- `scripts/importCatalogExpansion.js`
- `src/data/catalogExpansion20261017.js`

Desde PowerShell, en la raíz de MiSendero, sustituir la ruta de la clave y el usuario por los usados habitualmente para acceder a EC2:

```powershell
scp -i "C:\RUTA\TU-CLAVE.pem" .\catalogo-rds-20261017.tar.gz USUARIO_EC2@18.218.87.168:~/
ssh -i "C:\RUTA\TU-CLAVE.pem" USUARIO_EC2@18.218.87.168
```

Si accedés desde EC2 Instance Connect o SFTP, podés subir el mismo archivo a la carpeta personal del usuario, sin cambiar claves ni abrir nuevos puertos de RDS.

## Preparar y revisar

En la terminal Linux de EC2, consultar la carpeta y la ubicación de configuración del servicio; este comando no muestra los valores de los secretos:

```bash
sudo systemctl show misendero.service -p WorkingDirectory -p EnvironmentFiles
```

Entrar en la carpeta real del **backend**, donde están `package.json`, `src/server.js` y `node_modules`. Si WorkingDirectory apunta a la raíz de MiSendero, entrar además en `backend`. Sustituir el marcador antes de ejecutar:

```bash
cd /RUTA/REAL/DEL/BACKEND
tar -xzf ~/catalogo-rds-20261017.tar.gz
NODE_ENV=production node scripts/importCatalogExpansion.js --remote --dry-run
```

El importador usa las variables ya presentes en el proceso y carga `backend/.env` sin reemplazarlas. No cambiar `DATABASE_URL`, PG*, SSL ni contraseñas. Si el servicio usa un EnvironmentFile externo en lugar de `backend/.env`, usar el mismo archivo para **ambos** comandos con Node >=22:

```bash
NODE_ENV=production node --env-file=/RUTA/REAL/DEL/ARCHIVO-DE-ENTORNO scripts/importCatalogExpansion.js --remote --dry-run
```

No copiar ni mostrar el contenido del archivo de entorno. El importador carga solamente `db.js`, no inicia el servidor ni requiere compilar TypeScript. Usa `pg`, `dotenv` y `zod`, dependencias ya presentes en el backend. Ante un módulo faltante, verificar que se está en el backend y que sus dependencias están instaladas; no reemplazar la instalación completa de producción para cargar dos archivos.

La salida incluye:

```json
{
  "target": "TU-ENDPOINT-RDS:5432/TU-BASE",
  "mode": "dry-run",
  "before": 32,
  "after": 32,
  "projectedAfter": 52,
  "pending": ["nombres de las fichas faltantes"],
  "skipped": []
}
```

`pending` debe contener 20 fichas si todavía no cargaste ninguna. Si hay duplicados, habrá menos inserciones y aparecerán en `skipped`. Revisar que `target` corresponda a la base RDS usada por MiSendero, no al PostgreSQL local. Si falta una columna como `provenance`, la carga falla y revierte; revisar el esquema por separado, sin habilitar migraciones automáticas.

## Aplicar y comprobar

Copiar exactamente el valor `target` de la vista previa:

```bash
NODE_ENV=production node scripts/importCatalogExpansion.js --remote --apply --confirm-target='TU-ENDPOINT-RDS:5432/TU-BASE'
```

Si usaste un archivo de entorno externo, conservar también `--env-file=/RUTA/REAL/DEL/ARCHIVO-DE-ENTORNO` antes de `scripts/importCatalogExpansion.js`.

La salida esperada para una base original sin duplicados es `before: 32`, `after: 52`, 20 elementos en `inserted` y `existingRowsPreserved: true`. Los IDs son los que asigna RDS, no los IDs locales. Una segunda ejecución omite las fichas ya presentes.

```bash
curl --fail --silent --show-error https://18-218-87-168.sslip.io/api/trails | node -e 'let s="";process.stdin.on("data",c=>s+=c);process.stdin.on("end",()=>{const rows=JSON.parse(s);if(!Array.isArray(rows))throw new Error("Respuesta de catálogo inválida");console.log("Rutas disponibles:",rows.length)})'
```

Volver a abrir Explorar rutas o recargar Expo y quitar filtros para ver el total. La API consulta el catálogo en cada petición; esta carga no necesita reiniciar `misendero.service`, Nginx ni cambiar la URL móvil. Si el conteo público no coincide con `after`, comprobar que el backend utiliza la misma base del `target` confirmado.

El paquete actualiza **los datos del catálogo**, no despliega los cambios del recomendador. Para estos últimos seguir [el procedimiento del backend](../trail-recommendation.md).

## Fallas

Un error antes del `COMMIT` revierte la transacción completa. No hay inserciones parciales; la secuencia de IDs puede dejar huecos, comportamiento normal de PostgreSQL. Un fallo de red durante la confirmación requiere ejecutar nuevamente la vista previa para comprobar el estado: las claves y los alias evitan duplicados al reintentar. Los registros existentes se comparan por hash antes de confirmar.

Una reversión después de una carga confirmada debe revisarse por separado con los IDs de `inserted`, sus referencias y el lote. No eliminar por rangos de IDs, no restaurar toda RDS ni ejecutar el seed general para deshacer este lote.
