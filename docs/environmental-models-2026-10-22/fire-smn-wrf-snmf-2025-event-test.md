# Prueba externa del modelo WRF con inicios SNMF de 2025

## Resultado

El modelo logístico WRF se entrenó con detecciones MODIS hasta 2022 y se evaluó temporalmente hasta diciembre de 2023. La validación no eligió un umbral: no se encontró ninguno con al menos cinco avisos y 90% de precisión proxy. Sin reajustarlo con estos eventos, se puntuaron los cuatro inicio de incendio SNMF de 2025 que estaban a menos de 10 km de un sector de ruta y tenían pronóstico WRF válido.

Con el corte diagnóstico fijo de 0,5, el modelo no alertó en ninguno: sensibilidad descriptiva 0/4. Los scores fueron 0,044 para Bosque Tallado el 8/10, 0,003 para Bosque Tallado el 17/11, 0,121 para Cerro Ventana el 11/12 y 0,437 para Quebrada del Condorito el 10/10. No se eligió este corte mirando los cuatro casos.

La cohorte no permite medir precisión: contiene positivos reportados pero no negativos verificados. Tampoco permite asegurar anticipación de 27 horas, porque SNMF da fecha de inicio pero no hora; el pronóstico es válido a las 15 UTC de esa fecha, y el incendio pudo haber comenzado antes.

## Calidad y alcance de los datos

Los pronósticos corresponden al archivo público WRF DET del SMN, emisión a las 12 UTC del día anterior y validez a las 15 UTC. El script verificó CRC64NVME de S3 y los tiempos internos de cada NetCDF. Esta sesión resetea las conexiones HTTPS a S3; la adquisición exploratoria se hizo por HTTP. El checksum detecta corrupción, pero por HTTP no autentica el origen frente a un intermediario; por eso esta cohorte debe volver a descargarse con HTTPS antes de citarla como evidencia final de tesis.

El inventario SNMF 2025 tiene solo cuatro ruta-días dentro de 10 km en las fechas con reportes extraídos y la serie WRF de este estudio termina en 2023. Los reportes oficiales mensuales anteriores, como julio-septiembre de 2020, sí incluyen listas por incendio con fecha de inicio y coordenadas ([julio](https://www.argentina.gob.ar/sites/default/files/ocurrencia_de_incendios_mes_de_julio_2020.pdf), [septiembre](https://www.argentina.gob.ar/sites/default/files/ocurrencia_de_incendios_mes_de_septiembre_2020.pdf)); ampliar eventos históricos puede validar coincidencia, pero no reemplaza negativos completos ni pronósticos archivados del mismo período.

## Próximos datos necesarios

Para probar precisión real de una alerta por ruta hace falta una cohorte temporal posterior con: pronósticos archivados WRF/GFS recuperados por HTTPS para días positivos y días sin incendio; registros SNMF/APN o provinciales con evento, coordenadas y hora de inicio; y confirmación de qué fechas/rutas tuvieron cobertura completa para construir negativos verificables. Hasta obtener ese cruce, el modelo WRF no debe usarse como probabilidad ni advertencia de seguridad.

Los cálculos y scores por evento están en [`fire-smn-wrf-snmf-2025-event-test.json`](fire-smn-wrf-snmf-2025-event-test.json), reproducibles con [`evaluate_smn_wrf_snmf_events.py`](../../training/python/evaluate_smn_wrf_snmf_events.py). El inventario oficial de eventos está en [`fire-snmf-route-event-coverage-2025.json`](fire-snmf-route-event-coverage-2025.json); la procedencia y checksums de los pronósticos, en `training/data/environmental/private/smnf-wrf-official-event-2025/manifest.json`.
