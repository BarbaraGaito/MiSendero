# Incorporación de fuentes argentinas — 14/10/2026

Se incorporaron **52 recorridos completos con dificultad publicada por APN** y **288 tramos con sac_scale publicado por OSM y relieve del IGN**. Son dos tareas distintas; no se suman como 340 senderos independientes ni se convierten sus etiquetas entre escalas. Las cuatro evaluaciones públicas del proyecto contienen 1030 filas base, sin filas generadas ni augmentation en esta corrida.

## APN: dificultad de recorridos completos

| Fuente oficial | Recorridos admitidos | Uso |
| --- | ---: | --- |
| [Tierra del Fuego](https://www.argentina.gob.ar/parquesnacionales/patagonia-austral/senderos-del-parque-nacional-tierra-del-fuego) | 13 | Test reservado completo |
| [Los Alerces](https://www.argentina.gob.ar/node/276965) | 22 | Entrenamiento y validación por parque |
| [Calilegua, Jujuy](https://www.argentina.gob.ar/parquesnacionales/region-noroeste/parque-nacional-calilegua/actividades) | 11 | Entrenamiento y validación por parque |
| [Quebrada del Condorito, Córdoba](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-quebrada-del-condorito/actividades) | 5 | Entrenamiento y validación por parque |
| [El Leoncito, San Juan](https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-el-leoncito/actividades) | 1 | Entrenamiento y validación por parque |

Se conservan baja, media, alta y la categoría compuesta media-alta. Solo se normalizan mayúsculas y el separador de media/alta; el texto original queda registrado. No se calcula la dificultad desde la distancia, duración o pendiente.

Los predictores son **distancia y duración estimadas por APN**, con indicadores separados de ida, ida y vuelta, total o sentido sin especificar. Son datos publicados reales, no mediciones de tiempos individuales ni una precisión garantizada del recorrido. No se duplica una distancia de ida ni se supone el sentido que falta. Los nombres, parques y extractos de evidencia quedan fuera de las variables del modelo.

Se registraron ocho exclusiones de fichas: dos entradas de Las Palanganas con distancias contradictorias; dos recorridos del Condorito con alcance/clasificación conflictivos; una duración a caballo; dos fichas sin duración; una con alternativas de distancia. La página de Nahuel Huapi revisada no aporta fichas individuales completas y explícitamente etiquetadas para caminar; sus etiquetas de ciclismo no se reutilizan. No se completan los faltantes con valores supuestos.

La atribución de APN y sus páginas originales queda en `source_catalog.json` y `provenance.json`. Los [términos de Argentina.gob.ar](https://www.argentina.gob.ar/terminos-y-condiciones) indican CC BY 4.0 salvo indicación contraria.

## OSM + IGN: dificultad técnica de tramos

| Zona consultada | Tramos admitidos | Uso |
| --- | ---: | --- |
| Bariloche | 36 | Train/CV |
| El Bolsón | 4 | Train/CV |
| El Chaltén | 190 | Train/CV |
| Calilegua | 9 | Train/CV |
| Ushuaia / Tierra del Fuego | 48 | Test reservado |
| Mendoza / Vallecitos | 1 | Test reservado |
| Quebrada del Condorito | 0 | Sin sac_scale publicado en el recorte; no se inventa etiqueta |

Se ampliaron los snapshots originales de la [API de OpenStreetMap](https://wiki.openstreetmap.org/wiki/API_v0.6) y se mantienen las seis clases nativas [sac_scale](https://wiki.openstreetmap.org/wiki/Key:sac_scale). Solo se admiten geometrías completas con etiqueta explícita. Se retienen ID y versión de cada camino para la auditoría. Atribución: [OpenStreetMap contributors, ODbL](https://www.openstreetmap.org/copyright).

Se descargaron **11 teselas originales MDE-Ar v2.1 de 30 m del IGN**, en ZIP/HFA, enlazadas por su [visor oficial](https://dnsg.ign.gob.ar/apps/mapas-geodesia/mde_mapa_geoserver.php) y el índice WFS de la capa `mde_v2_30m`. El IGN describe la [distribución libre y gratuita](https://www.ign.gob.ar/NuestrasActividades/Geodesia/ModeloDigitalElevaciones/Introduccion); no se atribuye una licencia específica de tesela que no esté publicada.

La geometría aporta distancia y sinuosidad. Del raster se extraen elevaciones, ascenso, descenso y pendientes absolutas aproximadas: celda original más cercana, muestreo uniforme del recorrido a intervalos de hasta 60 m y filtro de mediana de tres puntos. Son transformaciones declaradas de datos públicos, no nuevas observaciones etiquetadas. La resolución limita la representación de rocas, escalones y otros obstáculos pequeños. Se excluyó un tramo por celdas sin elevación válida; no se imputaron alturas ni se usaron mapas de colores como elevaciones.

Los parques APN no se emparejan por nombre con caminos OSM: las fichas no aportan una geometría inequívoca para todas las rutas. El IGN complementa el benchmark OSM; APN permanece como tarea separada de recorridos completos.

## Evaluación obtenida

Las particiones geográficas quedaron declaradas en el catálogo antes del ajuste. APN entrena con 39 recorridos de cuatro parques y prueba los 13 de Tierra del Fuego. OSM entrena con 239 tramos de cuatro regiones y prueba 49 de Ushuaia/Mendoza. Cada validación cruzada retiene parques/regiones completos y solo usa entrenamiento. Nombres, relaciones y redes conectadas no pueden cruzar particiones. No hubo búsqueda de semillas ni selección de particiones por resultados.

| Tarea | Test | Aciertos | Accuracy | F1 macro | Referencia de frecuencia de train |
| --- | ---: | ---: | ---: | ---: | ---: |
| APN | 13 recorridos / 1 parque | 10 | 76,92% | 0,542 | 23,08–61,54% por empate |
| OSM + IGN | 49 tramos / 2 regiones | 47 | 95,92% | 0,276 | 93,88% |

En APN, baja y media empatan con 15 ejemplos de entrenamiento. El baseline previo conserva media por orden de aparición, que acierta 3/13; baja acertaría 8/13. Se publican ambas referencias sin elegir según el test. En OSM, 46 de los 49 ejemplos del test son hiking: el modelo aporta **un acierto adicional** sobre predecir siempre hiking. La CV F1 macro media fue 0,222 en APN y 0,106 en OSM. Los F1 macro de test consideran las cuatro y seis clases nativas respectivamente, incluyendo clases ausentes del test.

No se puede atribuir la diferencia con la evaluación OSM anterior al IGN: cambiaron datos, predictores y partición. No es una comparación controlada. Las regiones y clases raras siguen insuficientemente representadas, en particular Mendoza tiene un solo tramo etiquetado en el recorte. Los modelos conservan `deployment_approved: false` y el panel los identifica como investigación.

## Reproducción y evidencia

- `npm run train:apn-difficulty` y `npm run train:route-difficulty` reproducen las dos tareas.
- `npm run fetch:ai-data -- --model apn_route_difficulty --model route_difficulty` descarga originales que deben coincidir con el lock.
- `npm run validate:ai-data` reconstruye las mediciones/etiquetas desde los originales, verifica los parques/regiones fijados y recalcula métricas y baselines.
- `npm run test:ai-data` prueba fuentes, unidades, faltantes, etiquetas, grupos y que los ajustes usan solo filas observadas.

`training/data/public/sources.lock.json` fija SHA-256 de 31 archivos originales. En `apn_route_difficulty/` y `route_difficulty/` quedan CSV, procedencia por fila, predicciones reservadas, métricas y bosques experimentales. Los originales están en `training/data/raw/public_audit/`, excluidos de Git. APN, el índice IGN y OSM son fuentes dinámicas: conservar los snapshots, porque una nueva respuesta con otro hash se rechaza y requiere auditoría explícita. El lock no se actualiza automáticamente.

No se aplicó augmentation. Desde el 15/10/2026 el pipeline no admite datos sintéticos en ninguna tarea: se eliminó la opción `--augment`.
