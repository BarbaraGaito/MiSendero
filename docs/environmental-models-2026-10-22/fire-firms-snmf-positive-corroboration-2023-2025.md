# Corroboración de eventos SNMF con detecciones FIRMS (2023–2025)

Se consultó VIIRS SNPP en ventanas de hasta cinco días seleccionadas alrededor de fechas positivas SNMF y se filtraron focos a 20 km de las polilíneas de los senderos. El resultado es una auditoría de coincidencias positivas; no mide precisión del modelo.

| Año | Días-ruta SNMF seleccionados | Bloques FIRMS | Detecciones | Días-ruta con detección FIRMS | Coincidencia exacta | Coincidencia ±1 día |
|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 40 | 20 | 462 | 18 | 11 (27.5%) | 18 |
| 2024 | 84 | 34 | 64 | 8 | 6 (7.1%) | 8 |
| 2025 | 60 | 28 | 488 | 11 | 10 (16.7%) | 11 |

Las coincidencias son descriptivas: la cohorte se eligió desde los positivos SNMF, la fecha diaria no ordena el hotspot respecto de la emisión del pronóstico y la proximidad no prueba que ambos registros sean el mismo incendio. La ausencia de una detección FIRMS no se convierte en negativo. Por estas razones, estos datos no estiman precisión ni permiten afirmar una predicción fiable.

No se crearon etiquetas sintéticas ni negativas. Los CSV de respuesta y geometrías se guardan en directorios privados locales; el resumen registra sus hashes, bloques consultados y limitaciones en el [JSON](fire-firms-snmf-positive-corroboration-2023-2025.json).

Fuentes: [informes diarios SNMF](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego), [API histórica FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/). Reproducción: [`plan_firms_snmf_event_windows.py`](../../training/python/plan_firms_snmf_event_windows.py) y [`audit_firms_snmf_positive_corroboration.py`](../../training/python/audit_firms_snmf_positive_corroboration.py).
