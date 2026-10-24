# WRF contra eventos SNMF de 2023: sensibilidad espacial y días sin reporte

Se cruzaron los scores congelados del test WRF julio-diciembre de 2023 con los inicios reportados por SNMF. El corte 0,5 es diagnóstico y no fue seleccionado en validación.

## Eventos positivos reportados

| Radio del centro de ruta | Ruta-días SNMF | Con cobertura a 10 km del evento | Alertas | Coincidencia entre ruta-días cubiertos |
| ---: | ---: | ---: | ---: | ---: |
| 10 km, radio primario | 2 | 1 | 1 | 1/1 |
| 20 km, sensibilidad exploratoria | 15 | 9 | 6 | 6/9 (66,7%) |

El denominador de 10 km excluye un día sin cobertura WRF. El radio de 20 km agrega sectores vecinos y no reemplaza al primario; de los 15 ruta-días positivos, seis tampoco tuvieron cobertura local. Estos resultados son coincidencia/sensibilidad descriptiva, no precisión.

## Comprobaciones de no-reporte

- El parte SNMF del 20/12/2023 indicó que no había incendios reportados en el país. WRF tuvo filas en cinco sectores para esa fecha y no alertó en ninguno.
- El informe mensual de diciembre reportó cero incendios en Corrientes y Buenos Aires. En los sectores Sendero Che Roga y Cerro Ventana hubo 59 ruta-días con cobertura; WRF alertó en nueve (15,3%). En ninguno de esos 59 días MODIS marcó positivo en los pixeles evaluados.

Los días sin reporte y los ceros provinciales no son negativos físicos verificados: pueden omitir focos no reportados, sin coordenada, no observados por el satélite o fuera de su ventana. Estos conteos sirven para identificar que el corte 0,5 puede producir muchas advertencias donde SNMF no registró eventos; no son una matriz de confusión ni permiten calcular precisión real.

La fecha SNMF no incluye hora de ignición, así que el pronóstico WRF válido a las 15 UTC del día de inicio no demuestra anticipación. El modelo tampoco tiene un umbral aprobado ni produce probabilidades calibradas. No debe presentarse como alerta fiable de incendio.

El detalle por ruta-día, hashes y límites está en [`fire-smn-wrf-snmf-2023-radius-sensitivity.json`](fire-smn-wrf-snmf-2023-radius-sensitivity.json), reproducible con [`audit_smnf_wrf_event_radii_2023.py`](../../training/python/audit_smnf_wrf_event_radii_2023.py). Fuentes de los comparadores negativos: [parte SNMF del 20/12/2023](https://www.argentina.gob.ar/sites/default/files/2024/01/reporte_diario_20-12-2023.pdf) y [ocurrencia mensual de diciembre 2023](https://www.argentina.gob.ar/sites/default/files/2024/01/informe_ocurrencia_diciembre2023.pdf).
