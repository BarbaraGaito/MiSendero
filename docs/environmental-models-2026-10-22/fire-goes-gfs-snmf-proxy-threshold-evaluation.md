# Umbral GFS+GOES evaluado contra partes SNMF diarios

## Protocolo temporal

Se uso diciembre de 2025 solo para seleccionar un corte y enero de 2026 como prueba posterior. El objetivo proxy es que el reporte diario SNMF liste un incendio ACTIVO, CONTENIDO o CONTROLADO a 10 km de un centro de sector de trekking. Los dias sin un reporte archivado, sin filas extraidas o con algun incidente sin coordenadas se excluyen; nunca se convierten en negativos. Un dia-sector sin incidente listado se interpreta solo como ausencia de registro cercano en ese parte, no como prueba de ausencia de fuego.

El criterio de seleccion fue al menos 90 % de precision proxy con un minimo de cinco alertas, maximizando luego el recall proxy. La regla usa el umbral de puntaje para el modelo GFS+GOES de 24 h. Los partes son independientes de las etiquetas GOES del modelo, pero no son un censo exhaustivo de fuego.

## Resultado

En diciembre hubo 31 partes publicados. Dos fechas se excluyeron porque habia incidentes sin coordenadas; despues de aplicar tambien la cobertura del modelo quedaron 209 ruta-dias etiquetables, con solo tres positivos de reporte. Al score diagnostico 0.5 el modelo coincidi? con los tres, pero produjo 105 alertas mas sin incidente activo listado: 3/108 = 2.78 % de precision proxy.

El mejor umbral de validacion manteniendo al menos cinco alertas fue 0.6326: coincidio con 3 de 3 dias positivos, pero emitio 80 alertas, 77 sin coincidencia oficial. Precision proxy: 3.75 %. Ningun umbral cumplio la meta del 90 %, por lo que no se eligio ni se transfirio un corte al test.

En enero, como descripcion del corte diagnostico 0.5 no seleccionado, hubo 232 ruta-dias etiquetables: 29 positivos de reporte, 27 coincidencias y 106 alertas sin incidente activo listado (precision proxy 20.3 %, recall proxy 93.1 %). Esta cifra no es una estimacion de precision frente a todos los fuegos fisicos. La persistencia produjo 2 coincidencias de reporte en 23 alertas, pero menor sensibilidad; ambas reglas muestran el intercambio entre cobertura y desacuerdos con el parte.

## Conclusion

El cruce externo aporta una evaluacion mas util que medir solo etiquetas satelitales, pero rechaza la hipotesis de que basta subir el umbral del modelo actual para obtener alta precision. Diciembre no permitio seleccionar un umbral fiable, y la representacion de SNMF en lugares sin incidente no es lo bastante exhaustiva para llamar fisicamente falsas a todas las alertas sin coincidencia. Se necesitan tanto mas eventos independientes como ventanas de vigilancia confirmadas sin fuego y datos meteorologicos archivados para muchas mas temporadas y rutas. No hay evidencia para presentar el score como probabilidad ni para recomendaciones automaticas de seguridad.

La evaluacion reproducible esta en [`fire-goes-gfs-snmf-proxy-threshold-evaluation.json`](fire-goes-gfs-snmf-proxy-threshold-evaluation.json). Se genera con [`tune_goes_gfs_against_snmf_report_proxy.py`](../../training/python/tune_goes_gfs_against_snmf_report_proxy.py), usando las predicciones guardadas en [`fire-goes-gfs-24h-evaluation.json`](fire-goes-gfs-24h-evaluation.json) y los archivos diarios oficiales SNMF de 2025 y enero de 2026. Los modelos siguen sin aprobacion para produccion.
