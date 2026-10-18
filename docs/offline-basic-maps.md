# Mapas básicos sin conexión

La descarga nueva guarda únicamente la capa raster `standard`, el trazado y los
datos disponibles del sendero/reportes. No consulta Open-Meteo, no descarga una
grilla DEM, no exige altimetría y no descarga terreno ni satélite. Conserva los
niveles de zoom del mapa base de descargas anteriores, con un máximo de 110
imágenes. Solo ofrece el paquete como disponible después de verificar los archivos.

En modo offline, el visor usa el mapa básico local y el trazado. No ofrece las
capas Terreno/Satélite/3D ni solicita imágenes remotas. La vista 3D online se
mantiene y no añade su grilla a los paquetes descargados. Los datos antiguos no
se borran por este cambio.

## Fuente pendiente para las pruebas reales

El código no contiene un juego de imágenes de mapas ni crea recursos en AWS.
Una configuración sin fuente válida sigue devolviendo `provider-not-configured`.
Quitar el relieve no crea las imágenes del mapa base.

La opción elegida para MiSendero es preparar imágenes estáticas a partir de datos
cartográficos reutilizables y alojarlas en AWS. No se debe copiar el servidor
público `tile.openstreetmap.org` para crear estos archivos:
https://operations.osmfoundation.org/policies/tiles/.

El trabajo pendiente consiste en:

1. Seleccionar los datos geográficos reales, su actualización y atribución.
2. Renderizar las zonas de los senderos como imágenes XYZ de 256 × 256 píxeles,
   en Web Mercator, con el norte arriba. Mantener la estructura `{z}/{x}/{y}.png`.
   Preparar los niveles que requieran las rutas, no todo el país. No hay relieve 3D.
3. Conservar fuente, versión/fecha y licencia junto a los archivos generados.
4. Publicar esos archivos estáticos en S3 y servirlos por HTTPS mediante CloudFront.
   No hace falta una segunda instancia EC2 para renderizar cada solicitud.
5. Configurar la URL real en Expo y verificar rutas de distintas zonas en modo avión.

La generación debe hacerse fuera del backend que atiende la app. No modifica RDS,
no requiere GPU y no ejecuta migraciones ni seeds. El almacenamiento y la entrega
son costos distintos de la preparación inicial; dimensionarlos con el tamaño real
de los archivos y el número de descargas. No se desplegó infraestructura con este cambio.

## Configuración del cliente

En el `.env` raíz, una vez publicadas las imágenes y la documentación de su fuente:

```dotenv
EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL=https://TU-DISTRIBUCION.cloudfront.net/mapas/v1/{z}/{x}/{y}.png
EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION=ATRIBUCION_REAL_DE_LOS_DATOS
EXPO_PUBLIC_OFFLINE_TILE_LICENSE_URL=https://TU-DOMINIO/fuentes-del-mapa
EXPO_PUBLIC_OFFLINE_TILE_LICENSE_CONFIRMED=true
```

Son ejemplos de formato: reemplazarlos por recursos existentes. No se necesita
`EXPO_PUBLIC_OFFLINE_TERRAIN_TILE_URL` para descargar. El booleano de revisión
no sustituye la existencia de los archivos ni la licencia de su fuente.

Reiniciar Metro con `npx expo start --clear`. Abrir Expo Go desde Android/iPhone;
la descarga actual utiliza archivos persistentes nativos y no está implementada
para Expo Web. Descargar con conexión, activar modo avión, volver a abrir MiSendero
y abrir el mapa desde Descargados. Verificar mapa, trazado y posición GPS; cancelar
una descarga debe impedir que aparezca como completa.
