# Cruce independiente de alertas GOES con focos FIRMS VIIRS (enero de 2026)

Se consultó VIIRS S-NPP, NOAA-20 y NOAA-21 Standard Processing solo para las rutas y fechas de los 8 episodios de alerta GOES de 1 h, con ventanas de ±24 h. La descarga obtuvo 1349 filas de focos en 8 días-ruta; son detecciones repetidas, no incendios independientes. Hubo 104 focos de confianza alta, 1209 nominales y 36 de confianza baja.

Desglose por sensor: VIIRS_NOAA20_SP: 482 filas (39 alta, 428 nominal, 15 baja); VIIRS_NOAA21_SP: 381 filas (34 alta, 331 nominal, 16 baja); VIIRS_SNPP_SP: 486 filas (31 alta, 450 nominal, 5 baja).

Con la regla espacial de 10 km fijada en el protocolo de eventos, 0/8 episodios tuvieron una detección FIRMS dentro de ±24 h. A 20 km, el cruce fue 7/8. La detección más cercana quedó a 12.547 km de una polilínea. Las coincidencias a 20 km son evidencia regional; no muestran fuego sobre el sendero.

Al cotejar los focos con los dos incidentes SNMF ya asociados a los episodios de Bosque Tallado: Primera Cantera Puerto Patriada (2026-01-04 a 2026-01-15): 1348 filas a ≤10 km del punto SNMF; foco FIRMS más cercano a 0.133 km; Barda de La Loma (2026-01-04 a 2026-01-09): 0 filas a ≤10 km del punto SNMF; foco FIRMS más cercano a 11.309 km. Esto indica que la señal FIRMS se concentra junto a Primera Cantera Puerto Patriada, reportado a 18,2 km del recorrido, y no corrobora un foco FIRMS cercano al sendero en el radio de 10 km.

El corte GOES fue diagnóstico y no superó el criterio de validación; FIRMS tampoco cubre todos los momentos y lugares. Por ello, las coincidencias no miden precisión y la ausencia de un foco FIRMS no cuenta como negativo. La ventana ±24 h tampoco demuestra adelanto respecto de la ignición. Esta prueba aporta corroboración satelital parcial, no valida el modelo para recomendaciones de seguridad.

Detalle por episodio, radios, sensores, hashes y límites: [JSON reproducible](fire-goes19-alert-firms-crosscheck-2026-jan.json). Datos privados originales y plan de consulta: `training/data/environmental/private/firms-goes19-alert-crosscheck-2026-jan/` y `training/data/environmental/private/firms-goes19-alert-crosscheck-noaa20-21-2026-jan/`. Reproducción: [`audit_goes19_alert_firms_crosscheck.py`](../../training/python/audit_goes19_alert_firms_crosscheck.py). Fuentes: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/), [evaluación GOES congelada](fire-goes19-short-lead-route-sector-evaluation.md).
