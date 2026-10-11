# Altimetria de rutas

La app consulta alturas del terreno en Open-Meteo Elevation API, basadas en
Copernicus DEM 2021 GLO-90 (resolucion horizontal de 90 m, cobertura mundial).
No usa alturas aleatorias, geometria 3D procedural ni altitud GPS para completar
el perfil. La resolucion horizontal no equivale a precision vertical de 90 m.

## Datos y calculo

- Se recorre la polilinea `route_coordinates` en el orden almacenado y se
  muestrean coordenadas sobre sus segmentos a intervalos de hasta 90 m.
- Se consultan las alturas de esas coordenadas, en lotes de hasta 100 puntos.
  Las coordenadas entre vertices se interpolan para consultar el terreno; las
  alturas siempre proceden del proveedor.
- En rutas muy largas se limita el perfil a 500 puntos y se informa la
  separacion efectiva en `sample_spacing_m`.
- La distancia del perfil usa Haversine sobre el trazado. Puede diferir de la
  distancia publicada en el catalogo, especialmente si esta incluye el regreso
  y la geometria almacenada solamente representa la ida. No se inventa un
  tramo de regreso: las metricas y el grafico corresponden al trazado del mapa.
- Subida y bajada acumuladas usan un ancla movil con umbral de 5 m para reducir
  pequenas fluctuaciones del DEM. Los cambios pequenos sostenidos se acumulan
  hasta superar el umbral y el extremo final se incluye. Las alturas originales
  se conservan en el perfil; el umbral no modifica la curva ni sus extremos.
- Alturas nulas, no numericas o respuestas incompletas invalidan toda la
  consulta. Un valor real de 0 m es valido. Los errores no se reemplazan por
  alturas de ejemplo.

## Persistencia

`005_trail_elevation.sql` agrega `trails.elevation` (JSONB). El perfil incluye
coordenadas, alturas, distancias acumuladas, subida/bajada, extremos, fuente,
resolucion, fecha y SHA-256 de la geometria. El backend reutiliza el perfil
cuando coincide su geometria; si cambia el trazado, obtiene uno nuevo al abrir
el detalle. Un fallo del proveedor deja la ruta accesible con altimetria no
disponible, con reintentos limitados durante un minuto.

La descarga guarda el perfil dentro de `offline_maps.trail_json` en SQLite.
Las nuevas descargas necesitan altimetria y tiles verificados para declararse
completas. El perfil se conserva aun si luego falla la descarga de tiles.
Los mapas antiguos incorporan la altimetria al consultar el detalle con
conexion, siempre que su geometria siga coincidiendo. Sin conexion se utiliza
la copia descargada y no se consulta al proveedor.

## Preparar el catalogo

Desde `backend`, con PostgreSQL disponible y el `.env` habitual:

```powershell
npm run db:elevation
```

El comando aplica la migracion y carga las rutas existentes. Es idempotente:
reutiliza perfiles de la misma geometria y termina con codigo 1 si alguna ruta
no se pudo completar. Las rutas nuevas consultan su perfil al abrir el detalle.
Reiniciar el backend aplica los cambios de codigo y la nueva migracion.

El endpoint por defecto funciona sin clave para el uso no comercial del PFI.
Se pueden configurar `ELEVATION_API_URL` y `ELEVATION_API_KEY` en el backend
para el endpoint comercial de Open-Meteo. La clave nunca se envia al telefono.

## Alcance y verificacion

El detalle contiene una entrada "Altimetria" despues de "Antes de salir".
Al abrirla, una pantalla dedicada presenta el perfil consultable por punto,
subida, bajada, altura minima y maxima, distancia del trazado y atribucion a
Copernicus/Open-Meteo. Las estadisticas iniciales conservan el desnivel positivo;
el grafico y las metricas completas se muestran al abrir esta seccion.
Son estimaciones de un modelo del terreno, no mediciones topograficas del
sendero ni del desnivel realmente recorrido por una persona. Un DEM de 90 m
puede omitir escalones, curvas pequenas y detalles en laderas abruptas.

Las pruebas cubren muestreo, extremos, ruido, alturas faltantes, lotes,
persistencia, errores del proveedor, cambio de geometria, consultas simultaneas
y lectura/actualizacion de rutas descargadas.

Fuente y atribucion: https://open-meteo.com/en/docs/elevation-api
Copernicus DEM: https://doi.org/10.5270/ESA-c5d3d65
