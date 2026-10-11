# Catalogo de senderos verificados

Ampliacion del 11/10/2026: 12 recorridos nuevos, 22 en total, en 17 provincias.
Las condiciones de apertura, tarifas y horarios pueden cambiar: no se certifican
como vigentes por tener una ficha en la aplicacion.

## Recorridos agregados

| Provincia | Recorridos |
| --- | --- |
| Misiones | Macuco - Salto Arrechea |
| Rio Negro | Refugio Frey desde Villa Catedral |
| Cordoba | Quebrada del Condorito - Balcon Norte |
| Tierra del Fuego | Laguna Esmeralda; Senda Costera; Lago Acigami - Hito XXIV |
| La Pampa | Namuncura; Cerro Alto desde Namuncura |
| San Luis | Miradores; Guanacos de Sierra de las Quijadas |
| Santa Cruz | Mirador de los Condores; Mirador de las Aguilas |

## Procedencia y alcance

- Las fichas y requisitos provienen de APN, La Ruta Natural y Turismo de Bariloche.
  Cada entrada conserva sus enlaces en `provenance.sources` y los muestra en el detalle.
- `distance_km` es la longitud del trazado OSM, incluyendo el regreso cuando
  corresponde. `official_distance_km` conserva la referencia publicada: puede
  diferir por el acceso, la variante y la cartografia. No se ajustan coordenadas
  para forzar la coincidencia con una distancia oficial.
- Frey, Condores y Aguilas duplican el tiempo oficial de ida para planificar la
  salida completa. Cerro Alto tiene un tiempo orientativo de 2 h, expresamente
  identificado como estimacion: APN no publica su duracion en la ficha consultada.
- Miradores de Quijadas sigue la senda principal de ida y vuelta y conserva como
  referencia el tiempo de la ficha oficial, que describe un recorrido de 2,23 km.
- Senda Costera es solo ida. Su distancia y duracion no incluyen regresar al inicio.
- Los trazados unen exclusivamente vias peatonales OSM revisadas que comparten
  nodos. Se conservan sus IDs, versiones y fechas. No hay segmentos inventados.
  OSM es una referencia cartografica, no un relevamiento GPS propio.
- Las fotos reales de Wikimedia Commons conservan autor, pagina de origen y
  licencia. Cuando representan el parque y no la senda precisa, se aclara en la ficha.
- La altimetria usa Copernicus DEM GLO-90 mediante Open-Meteo. Es un modelo de
  terreno de resolucion aproximada de 90 m, no una medicion GPS de precision.
  El perfil queda almacenado en PostgreSQL y en las descargas offline.
- Los nuevos senderos no tienen reportes de estado ni valoraciones simuladas.

## Actualizacion reproducible

Los datos editables y los IDs de vias estan en
`backend/src/data/additionalTrailDefinitions.js`. Las trazas y fotos resueltas
se distribuyen en archivos JSON, por lo que iniciar el backend no necesita OSM
ni Wikimedia. La migracion `006_trail_provenance.sql` agrega un campo opcional;
el seed es idempotente y conserva IDs, favoritos y actividades existentes.

Para revisar y regenerar cartografia desde la raiz del proyecto:

```powershell
node backend/scripts/catalogGeometry.js --discover
node backend/scripts/catalogGeometry.js --inspect iguazu Macuco
node backend/scripts/catalogGeometry.js --build
node backend/scripts/catalogPhotos.js
docker compose up -d --build backend
docker compose exec -T backend npm run db:elevation
```

La descarga de elevacion puede requerir un segundo intento despues de que venza
un limite temporal del proveedor. Los perfiles ya obtenidos se reutilizan.
El cache temporal de OSM se escribe en `tmp/catalog-osm` y no debe distribuirse
con el catalogo. Los JSON publicados solo incluyen coordenadas y metadatos de
procedencia de las vias. Los datos cartograficos se atribuyen a OpenStreetMap
contributors, bajo [ODbL 1.0](https://www.openstreetmap.org/copyright).

El progreso de ida y vuelta utiliza la distancia GPS registrada para distinguir
ambas pasadas por la misma ubicacion. Los recorridos anteriores sin esta modalidad
explicita mantienen su comportamiento original.
