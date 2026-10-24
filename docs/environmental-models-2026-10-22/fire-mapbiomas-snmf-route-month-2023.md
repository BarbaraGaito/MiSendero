# Cruce MapBiomas Fuego–SNMF cerca de rutas, 2023

## Alcance y fuente

La ficha actual de MapBiomas Fuego resume el producto mensual como 2013–2024, pero el anuncio oficial de lanzamiento de la primera Colección Fuego informa mapas mensuales y anuales para 1999–2025; la auditoría del bucket público encontró los 27 GeoTIFF mensuales hasta 2025. Por eso el raster mensual 2023 sí forma parte de la colección publicada. La cartografía se deriva de observaciones Landsat y representa cicatrices retrospectivas, no pronósticos. [Ficha de Fuego](https://argentina.mapbiomas.org/iniciativas-y-productos/fuego/) y [anuncio de la colección nacional](https://argentina.mapbiomas.org/2026/10/05/argentina-tiene-mas-superficie-agropecuaria-que-bosques-los-nuevos-datos-de-mapbiomas-muestran-como-cambio-el-territorio-desde-1985/).

El inventario SNMF de 2023 contiene 1.195 incidentes deduplicados. Al cruzar sus coordenadas de inicio reportado contra los ocho centros de sectores de trekking de `training/data/environmental/geography.json`, se encuentran solo dos días-sector a menos de 10 km: Río de la Suela–Quebrada del Condorito (06/10/2023, 8,936 km) y Quema Golondrinas–Bosque Tallado (19/12/2023, 5,601 km). El inventario advierte que 65 de 184 fechas revisadas entre julio y diciembre no tenían un PDF en las ubicaciones consultadas; esas fechas son desconocidas, no días sin incendios.

## Resultado del cruce

En esta ejecución se descargó el GeoTIFF mensual 2023 desde el bucket público y se verificó el MD5 publicado. De los dos días-sector SNMF a menos de 10 km de una ruta, uno (Río de la Suela, 06/10/2023) tenía área quemada MapBiomas del mismo mes dentro del buffer de 10 km; el otro (Quema Golondrinas, 19/12/2023) no.

Al asociar las dos coordenadas de incidentes en vez de usar el centro de ruta, Río de la Suela tuvo píxeles quemados del mismo mes a 250 m y radios mayores, pero no a 100 m. Quema Golondrinas no tuvo píxeles del mes informado hasta 2 km; sí aparecieron píxeles quemados de otros meses en 2 km. El cálculo exacto y los hashes están en el [JSON reproducible](fire-mapbiomas-snmf-route-month-2023.json); el [script](../../training/python/evaluate_mapbiomas_fire_2023_snmf_coincidence.py) descarga el raster temporalmente y elimina la copia.

Este es un cruce retrospectivo de cicatrices mensuales, no una evaluación de pronóstico. La fecha cartográfica no fija la hora de inicio, los incidentes SNMF tienen cobertura incompleta y una no coincidencia no se clasifica como falso positivo o falso negativo confirmado.

El análisis previo WRF–SNMF de 2023 también tuvo solo dos días-sector reportados a menos de 10 km; solo uno tenía filas de predicción del modelo. En ese único día hubo una alerta al corte diagnóstico de 0,5. Ese corte se eligió exploratoriamente tras ver los datos, y no estima precisión generalizable. Ver [sensibilidad por radio](fire-smn-wrf-snmf-2023-radius-sensitivity.md).

Este conjunto no alcanza para medir precisión fiable: faltan suficientes incidentes independientes y negativos verificados, y MapBiomas mensual no da hora de ignición. El cruce sirve para auditar cobertura espacial de las etiquetas y su desfase, no para probar anticipación ni calcular precisión del pronóstico.

## Reproducción

```powershell
.venv-ai\Scripts\python.exe training/python/evaluate_mapbiomas_fire_2023_snmf_coincidence.py
```

La ejecución completa escribirá `fire-mapbiomas-snmf-route-month-2023.json` junto a este reporte. No se generaron datos sintéticos ni se modificó el modelo de la app.
