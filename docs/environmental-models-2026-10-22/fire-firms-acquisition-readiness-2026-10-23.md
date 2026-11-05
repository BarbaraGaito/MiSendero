# Adquisición de detecciones históricas NASA FIRMS

La API Area de NASA FIRMS permite consultar detecciones activas VIIRS en producto Standard Processing, con rangos de hasta cinco días y disponibilidad por sensor. Se realizaron consultas autenticadas usando `NASA_FIRMS_MAP_KEY` desde el `.env` local ignorado por Git. El `.env.example` conserva `NASA_FIRMS_MAP_KEY=` vacío como plantilla; no se debe copiar la clave al repositorio.

Se descargó VIIRS S-NPP para ventanas seleccionadas alrededor de días-ruta positivos de informes SNMF, con un radio de 20 km a las polilíneas de senderos: 20 bloques de consulta en 2023, 34 en 2024 y 28 en 2025. Las respuestas y metadatos detallados quedan en el directorio privado local `training/data/environmental/private/`; cada archivo registra hashes de respuestas, geometría y disponibilidad. El resumen y sus límites están en [la auditoría de corroboración 2023–2025](fire-firms-snmf-positive-corroboration-2023-2025.md) y su [JSON](fire-firms-snmf-positive-corroboration-2023-2025.json).

El capturador [`acquire_firms_route_detections.py`](../../training/python/acquire_firms_route_detections.py) lee la clave desde el entorno del proceso, consulta disponibilidad antes de descargar, filtra contra las polilíneas y no guarda ni imprime la clave. Para reproducir una consulta, carga la variable desde el gestor de secretos local y ejecuta, por ejemplo:

```powershell
.venv-ai\Scripts\python.exe training/python/acquire_firms_route_detections.py --start 2024-01-01 --end 2024-12-31 --sensor VIIRS_SNPP_SP --date-windows-json training/data/environmental/private/firms-route-detections/event-windows-2024.json --output-dir training/data/environmental/private/firms-route-detections-snmf-events-2024
```

Los días consultados fueron seleccionados por tener reportes SNMF positivos, por eso esta descarga solo corrobora candidatos. Una ausencia en FIRMS no equivale a una observación sin fuego: puede deberse al horario de pasada, nubes, humo, dosel o cobertura incompleta. Estos datos no crean negativos ni permiten estimar precisión. Para evaluar precisión todavía hacen falta cohortes de alertas elegidas sin conocer el resultado y etiquetas independientes con cobertura y tiempo verificables.

Fuentes: [API Area FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/), [disponibilidad por sensor](https://firms.modaps.eosdis.nasa.gov/api/data_availability/), [registro MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/map_key/), [informes SNMF](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego).
