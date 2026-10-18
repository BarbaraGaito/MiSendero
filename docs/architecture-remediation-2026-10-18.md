# Correcciones arquitectónicas — 18/10/2026

Se corrigió el código local por pedido de la responsable. No se desplegó en AWS ni se migró una base remota.

## AWS

La responsable confirmó el uso de AWS. Las guías `catalog-expansion-2026-10-17/AWS.md` y `trail-recommendation.md` identifican EC2, systemd/Nginx y RDS. La IP documentada 18.218.87.168 tiene DNS inverso `ec2-18-218-87-168.us-east-2.compute.amazonaws.com`; una lectura HTTP respondió Nginx, pero la ruta `/api/health` por IP devolvió 404 y el puerto 3001 no respondió. Esto confirma la infraestructura EC2 documentada, no la salud de la API ni las propiedades de la base. No se accedió a la consola AWS. RDS es parte del despliegue informado; no se certifican clase, subredes, KMS, TLS, Multi-AZ o backups sin revisar esos recursos. La frase anterior que equiparaba ausencia de IaC con ausencia de uso de AWS fue corregida.

## Reportes

El formulario genera `client_event_id` UUID y persiste la operación en SQLite antes de cualquier HTTP. La cola conserva esa identidad al reintentar y asigna una a operaciones heredadas que no la tenían, antes de enviarlas. La migración 009 añade UUID, hash del pedido y unicidad `(reporter_user_id, client_event_id)`. El servidor retorna la observación original ante el mismo pedido; una identidad reutilizada con otro contenido devuelve 409 sin alterar datos. Clientes anteriores sin UUID mantienen compatibilidad, pero no obtienen esta garantía. No se fusionan duplicados históricos ni se puede identificar retrospectivamente el primer envío de una operación antigua que no llevaba UUID. El ámbito de deduplicación es la vida de la fila; el borrado definitivo/limpieza de un reporte elimina también su clave.

## Actividades y transacción local

Las sesiones nuevas tienen UUID persistido, independiente del autoincremento y de la instalación. Pausar y finalizar conservan esa identidad. El POST remoto deja de sobrescribir: devuelve la actividad original si el contenido coincide, o 409 ante otra actividad con la misma clave. La finalización del resumen, su outbox y el cierre de `route_runtime` se realizan en una misma transacción SQLite con conexión propia y `BEGIN IMMEDIATE`. El formulario ya no cierra el runtime antes de esa transacción. Fallar la outbox revierte los tres efectos. Las sesiones simuladas siguen fuera del almacenamiento y sincronización.

La migración recupera sesiones finalizadas antiguas sin outbox. Las identidades heredadas que pudieron llegar al servidor se conservan para evitar crear una copia: un conflicto antiguo requiere resolución explícita y no se sobrescribe. Operaciones nunca intentadas pueden pasar a UUID. Los estados agotados/descartados se preservan y no se reactivan automáticamente. La transacción no abarca archivos cartográficos ni PostgreSQL: el acuse remoto perdido se resuelve mediante idempotencia, no mediante una transacción distribuida.

## Almacenamiento y seguridad

La build nativa configura `expo-sqlite` con `useSQLCipher: true`. La base completa —contactos, puntos GPS, muestras, perfiles, sesión y cola— usa una clave aleatoria guardada en SecureStore con accesibilidad restringida al dispositivo desbloqueado. El JWT permanece en SecureStore. No se registra la clave ni se guarda en SQLite o en variables públicas.

Una instalación existente se migra mediante exportación a `trekking-secure-v1.db`, marcador de finalización, reapertura con clave y comprobaciones de integridad SQLite/SQLCipher. La copia anterior se retira solo después de validar la nueva; un error conserva los datos y bloquea la apertura insegura. La base nueva no se sobrescribe ni se elimina automáticamente para recuperarse de un fallo. No se permite continuar con SQLite nativo sin SQLCipher o sin almacén seguro. La previsualización web usa SQLite en memoria, sin persistencia de datos sensibles. El borrado de archivos no garantiza eliminación forense en almacenamiento flash.

Las imágenes públicas del mapa siguen en archivos normales; no contienen la traza GPS privada. La sincronización sigue siendo selectiva: no se añadieron cargas de salud o GPS. El cifrado por dispositivo complementa el filtrado por cuenta; no proporciona claves independientes para cada usuario. Android mantiene backup deshabilitado. La recuperación en otro dispositivo requiere evaluar la política de backups/claves y no está implementada por esta corrección.

## Aplicación y validación

1. Desplegar primero el backend actualizado y aplicar `backend/migrations/009_report_idempotency.sql` con el procedimiento habitual y respaldo de la base real. No ejecutar seeds para esta corrección.
2. Generar e instalar una nueva development/release build Android/iOS que incluya SQLCipher. Expo Go y una actualización solo de JavaScript no incorporan este módulo nativo.
3. Antes de distribuir, probar actualización desde una instalación con datos, modo avión, interrupción de migración, base ilegible sin clave, reapertura con clave, cola tras reinicio y dispositivo bloqueado. Las pruebas host no sustituyen estas comprobaciones.
4. Verificar HTTPS de la API, certificado y TLS del enlace PostgreSQL en AWS con la configuración efectiva; estas propiedades no se infieren del cifrado local.

Referencias de implementación: [Expo SQLite](https://docs.expo.dev/versions/latest/sdk/sqlite/), [migración SQLCipher](https://www.zetetic.net/sqlcipher/encrypting-plaintext-databases/), [SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/).
