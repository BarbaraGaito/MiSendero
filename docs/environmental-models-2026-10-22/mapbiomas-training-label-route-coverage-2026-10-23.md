# Cobertura de etiquetas manuales de MapBiomas cerca de senderos

## Hallazgo

Se obtuvo el CSV público `polygons_data_merged.csv` del almacén de datos enlazado por el repositorio de MapBiomas Argentina. El archivo mide 2.875.469 bytes y contiene 6.831 objetos etiquetados como fuego (`class=1`) o no fuego (`class=0`), con geometría puntual o poligonal, año y atributos del objeto. El rango indicado va de 1998 a 2024. Se encontraron 26 filas con conflicto de clase; el análisis excluye esas filas al resumir clases.

El cruce exploratorio con centros de rutas, dentro de un radio aproximado de 10 km, encontró etiquetas de fuego cerca de cuatro de las ocho rutas: Frey (4 filas/4 OID, año 1998), Condorito (4 filas/1 OID, 2006), Namuncurá (1 fila/1 OID, 2017) y Cerro Ventana (7 filas/1 OID, 2017). **No encontró objetos etiquetados como no fuego en el radio de 10 km de ninguna ruta.** Las filas y OID repetidos no se cuentan como incendios independientes. La regla espacial usa el punto representativo que trae cada objeto, no toda la geometría ni el recorrido completo.

El resultado reproducible está en [`mapbiomas-training-label-route-coverage-2026-10-23.json`](mapbiomas-training-label-route-coverage-2026-10-23.json); el programa que lo genera es [`audit_mapbiomas_route_training_labels.py`](../../training/python/audit_mapbiomas_route_training_labels.py). Se guardó el CSV descargado en la carpeta privada de investigación y el informe incluye su SHA-256.

## Por qué no permite afirmar precisión

El propio repositorio identifica estos archivos como datos para construir y revisar la colección MapBiomas Fuego; los objetos son muestras seleccionadas, no un inventario completo ni una muestra aleatoria de ruta-días. Que no haya un objeto clase 0 cerca de una ruta no significa que no hubo fuego allí, y tampoco prueba una ventana sin incendio. El modelo de MapBiomas se basa en imágenes Landsat y tiene su propio proceso de clasificación. Esto puede aportar casos externos para revisar detecciones de otros sistemas, pero no mide falsos positivos, calibración o probabilidad de ignición. No se entrenó ni se ajustó ningún modelo con estos datos y no cambió ninguna métrica previa.

## Fuentes y reproducción

- [Repositorio público MapBiomas Argentina Fire](https://github.com/mapbiomas/argentina-fire): describe Collection 1 como colección en desarrollo y enlaza el almacén de datos compartido.
- [Carpeta pública de datos](https://drive.google.com/drive/folders/1hmWZWkX1iHcGAGvqtv-5JSynvLnPx7wX): incluye `collection-01/data/objects-labels/polygons_data_merged.csv`.
- [Descripción de la metodología de MapBiomas Fuego Argentina](https://argentina.mapbiomas.org/iniciativas-y-productos/fuego/): clasifica cicatrices con series Landsat y agrega los píxeles en objetos.

```powershell
.venv-ai\Scripts\python.exe training/python/audit_mapbiomas_route_training_labels.py
```

Para reproducir exactamente hacen falta el CSV público citado (descargado a `training/data/environmental/private/mapbiomas-polygons-data-merged.csv`) y la versión del catálogo de rutas cuyo hash se guarda en el JSON. El script no genera datos sintéticos.
