# Catálogo público y revisión de tiempos — 12/11/2026

La URL de los perfiles EAS de la app devolvió **HTTP 200, 51 fichas, 19 del lote de octubre y ninguna del lote para principiantes**. Se guardaron los campos públicos necesarios en [catalogo-publico.json](catalogo-publico.json), obtenidos el 12/11 a las 14:04 (Argentina). Las diez fichas originales seguían sin procedencia publicada. No hubo conexión de escritura a RDS: la carga queda pendiente hasta recuperar el acceso a EC2.

## Tiempos revisados

| Ficha | Resultado de la revisión |
| --- | --- |
| Lahuán Solitario | **1 h 30 min ida y vuelta** según [APN](https://www.argentina.gob.ar/node/276965). La cifra ya estaba en la app; faltaba asociar la fuente y el alcance. |
| Cerro Morado | **3 h para el recorrido completo**, incluida la permanencia en la cima, según el [administrador de Ischigualasto](https://www.ischigualasto.gob.ar/?page_id=1823). No se infiere un circuito circular. |
| Cerro Leoncito | **3–4 h ida y vuelta**: las dos [referencias de APN](../catalogo-principiantes-2026-11-12.md) describen los mismos 8 km y publican tiempos distintos. |
| Rincón de las Aves | La [traza publicada por Turismo Esquel](https://es.wikiloc.com/rutas-senderismo/recorre-esquel-en-zapatillas-sendero-rincon-de-las-aves-59935218) registra **21 min solo de ida**. La ficha muestra **42 min estimados** para volver por el mismo camino; no se midió el regreso. |
| Sendero El Bosque, Puerto Canoa | **30 min de referencia para el circuito completo** en el [relevamiento de campo de la UNCo](https://rdi.uncoma.edu.ar/bitstream/handle/uncomaid/17926/importancia_del_sistema_de_informaci%C3%B3n_a_visitantes_en_areas_protegidas_sanchez-pascal%20-%20rdi.pdf?isAllowed=y&sequence=1), p. 101. Se muestra como estimación histórica; la ficha actual del parque no publica el tiempo. |
| Sendero a Confluencia | El regreso está incluido en el itinerario publicado. La [provincia](https://www.mendoza.gov.ar/prensa/mas-de-300-personas-visitaron-el-aconcagua-en-diez-dias/) y [Turismo Nación](https://www.argentina.gob.ar/node/465038) difieren en duración. Se conserva la advertencia y la ficha queda fuera de coincidencias de tiempo. |
| Laguna del Tesoro | [La Ruta Natural](https://larutanatural.gob.ar/es/imperdible/154/parque-nacional-aconquija) confirma **6 h de ida**. No respalda un tiempo de regreso; tampoco coincide con la distancia total inferida del dato de Tucumán Turismo. No se modifican distancia, dificultad ni duración del registro. |

Quedan sin una cifra de regreso respaldada seis fichas antiguas adicionales (Base–BIM del Lanín, Garganta del Diablo de Tilcara, Garganta del Diablo de Cafayate, El Mollar, Cerro Tres Picos y Campo de Piedra Pómez), Miradores de Sierra de las Quijadas y cuatro fichas nuevas (Cascada El Rincón, Mirador Lago Volcán, San Bernardo–Ala Delta y El Funicular). Sus tiempos faltantes o ambiguos no cuentan como coincidencia con un rango. Para cerrarlos hace falta que el administrador publique el alcance o que haya una medición comparable del itinerario exacto.

## Carga en EC2 cuando vuelva el acceso

El [paquete del lote](../../artifacts/catalogo-principiantes-20261112.tar.gz) contiene solo el importador, sus datos y el código para reutilizar la conexión del backend. Se descomprime en una carpeta nueva **dentro** del backend, de modo que pueda usar `node_modules` sin sobrescribir el código en ejecución. Usar la configuración de entorno que ya usa el servicio. El importador no ejecuta seeds ni migraciones.

SHA-256 del paquete: `142fdbbe50726fd2b3292ad90055a4bfeae4e97c3b5bd50ad2e25ece5120d514`.

Si el archivo no está en otro checkout, regenerarlo desde la raíz del repositorio:

```powershell
tar.exe -czf artifacts/catalogo-principiantes-20261112.tar.gz -C backend scripts/catalogImportRuntime.js scripts/importBeginnerCatalog.js src/data/beginnerCatalog20261112.js src/data/catalogDurationReviews20261112.js src/data/reviewedTrailFacts20261021.json
```

```bash
cd /RUTA/DEL/BACKEND
stage="$(mktemp -d "$PWD/.catalog-20261112.XXXXXX")"
tar -xzf ~/catalogo-principiantes-20261112.tar.gz -C "$stage"
export MISENDERO_CATALOG_BACKEND_ROOT="$PWD"
NODE_ENV=production node "$stage/scripts/importBeginnerCatalog.js" --remote --dry-run
```

Si el servicio usa un `EnvironmentFile` externo, añadir `--env-file=/RUTA/DEL/ARCHIVO` antes del nombre del script en ambos comandos. La vista previa en RDS es de solo lectura. Comparar el `target` con el del servicio y revisar las filas de `pending` y `durationReviews`. Si sigue igual que la copia pública, la proyección muestra **11 altas, 11 revisiones de duración o procedencia y 62 fichas**. El importador solo anota una ficha antigua si coinciden su nombre, ubicación, distancia y duración iniciales y no tiene procedencia propia.

```bash
NODE_ENV=production node "$stage/scripts/importBeginnerCatalog.js" --remote --apply --confirm-target='HOST:PUERTO/BASE'
NODE_ENV=production node "$stage/scripts/importBeginnerCatalog.js" --remote --dry-run
```

La segunda vista previa debe mostrar cero altas y cero revisiones pendientes. Verificar después `GET /api/trails`: comprobar el total, las claves del lote y que Lahuán Solitario y Cerro Morado devuelvan la procedencia prevista. La carga de datos no despliega por sí sola el código de recomendación ni actualiza el cliente móvil.

## Reproducir la auditoría

```powershell
npm.cmd --prefix backend run build
node backend/scripts/auditCatalogRecommendationFit.js --snapshot docs/catalogo-produccion-2026-11-12/catalogo-publico.json
node backend/scripts/auditCatalogRecommendationFit.js --snapshot docs/catalogo-produccion-2026-11-12/catalogo-publico.json --project
```

Se ejecutan las reglas del repositorio sobre los datos públicos congelados y, por separado, sobre la proyección del importador. Es una prueba de cobertura con búsquedas de igual peso. No invoca recomendaciones autenticadas en producción, ni mide demanda, satisfacción o precisión de un modelo.

| Indicador sobre las mismas 19.152 consultas | [Catálogo público](actual.json) | [Proyección del lote](proyeccion.json) |
| --- | ---: | ---: |
| Fichas | 51 | 62 |
| Ubicaciones sin opción para principiantes | 21/38 | 9/38 |
| Coincidencia con todas las preferencias | 1.410 (7,4 %) | 1.825 (9,5 %) |
| Duración fuera de rango o sin alcance suficiente | 11.984 (62,6 %) | 11.788 (61,5 %) |
| Fichas con tiempo total documentado, incluidas estimaciones identificadas | 36 | 44 |
| Fichas con tiempo explícito solo de ida | 4 | 5 |
| Fichas con tiempo no publicado, ambiguo o en conflicto | 11 | 13 |
| Resultados fuera del destino | 0 | 0 |

La cobertura temporal mejora en la grilla aunque queden dos fichas más pendientes en números absolutos: el lote agrega opciones de nivel bajo sin atribuirles tiempos que la fuente no publicó. Pasaron 103 pruebas de backend, 68 de app y servicios, compilación del backend y chequeo TypeScript. Se comprobó que el paquete extraído reproduce la proyección y que el importador rechaza una escritura remota sin confirmación exacta del destino.
