# Prueba GFS+GOES con validacion octubre-diciembre y test enero

## Protocolo

Se entreno el clasificador con datos anteriores al 1 de octubre de 2025, se reservo octubre-diciembre de 2025 para validacion y se mantuvo enero de 2026 como periodo posterior. Para seleccionar el umbral contra partes independientes, se exigio 90 % de precision de coincidencia con el parte y al menos cinco avisos. El corte 0.5 se muestra solo como comparacion diagnostica. El periodo de prueba de enero ya habia sido inspeccionado en analisis exploratorios previos, por lo que esta repeticion no es un test virgen.

La etiqueta SNMF se define como incidente ACTIVO, CONTENIDO o CONTROLADO listado a 10 km de un centro de sector en el parte del dia. Los dias sin PDF, sin filas extraidas o con cualquier incidente sin coordenadas se excluyen. La ausencia de un incidente listado no prueba que no hubiera fuego fisico.

## Resultado de validacion

El archivo oficial aporto 84 partes descargados entre el 2 de octubre y el 31 de diciembre. Siete fechas no tuvieron parte en las rutas revisadas, dos partes no produjeron filas parseadas y ocho fechas tenian al menos un incidente sin coordenadas. Con cobertura del modelo quedaron 516 ruta-dias etiquetables y 15 positivos de reporte.

Al umbral diagnostico 0.5, el modelo emitio cuatro alertas; ninguna coincidio con un incidente activo reportado y omitio los 15 positivos. El mayor valor de precision proxy entre umbrales con cinco o mas alertas fue 15/454 = 3.30 %. Ningun corte cumplio la meta del 90 %, por lo que no se selecciono ni se evaluo umbral en enero.

## Test posterior de enero

El corte diagnostico no seleccionado 0.5 obtuvo 25 coincidencias en 102 alertas (24.5 % de precision proxy), con 4 positivos de reporte omitidos y 77 alertas sin coincidencia oficial. En el cruce de inicios de incendio, cuatro eventos cerca de rutas con cobertura fueron alertados al mismo corte, con scores entre 0.569 y 0.747. Estos resultados distintos reflejan unidades diferentes: route-sector-day de parte diario frente a episodio agrupado por fecha de inicio. Ambos son limitados por la cobertura espacial, el registro de negativos y la falta de hora exacta de ignicion.

## Conclusion

Ampliar la validacion a tres meses dio mas casos (15 positivos) que usar diciembre solo, pero no produjo un umbral con alta precision proxy. Cambiar el corte no resuelve la falta de ordenamiento: en Q4 el mejor corte con cinco alertas o mas tuvo 3.3 % de coincidencia. Enero tampoco permite afirmar precision fiable porque sus negativos son solo ausencia de registro en un parte y el periodo ya se habia observado exploratoriamente. El candidato sigue sin aprobarse para produccion.

La ejecucion reproducible esta en [`evaluate_goes_gfs_previous_runs.py`](../../training/python/evaluate_goes_gfs_previous_runs.py) con `--validation-start 2025-10-01 --run-name q4-validation`, y el corte externo en [`tune_goes_gfs_against_snmf_report_proxy.py`](../../training/python/tune_goes_gfs_against_snmf_report_proxy.py). Resultados completos: [`fire-goes-gfs-snmf-proxy-threshold-evaluation-q4.json`](fire-goes-gfs-snmf-proxy-threshold-evaluation-q4.json), [`fire-goes-gfs-24h-evaluation-q4-validation.json`](fire-goes-gfs-24h-evaluation-q4-validation.json) y [`goes-gfs-24h-snmf-2026-jan-event-audit-q4-validation.json`](goes-gfs-24h-snmf-2026-jan-event-audit-q4-validation.json).
