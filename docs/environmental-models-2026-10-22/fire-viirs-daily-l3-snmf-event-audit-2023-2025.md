# VIIRS diario frente a eventos SNMF cercanos a senderos (2023–2025)

Se verificaron por SHA-256 **45 granulos** (9.28 MB) de VNP14A1, VJ114A1 y VJ214A1 para **16 clusters reportados** en 15 fechas-ruta y 15 fechas distintas.

La máscara 7–9 se conserva como detección térmica VIIRS; la clase 5 con QA de tierra es una celda terrestre observada sin detección en el compuesto diario. Nubes, agua, clases no procesadas o desconocidas siguen siendo desconocidas.

| Sensor | Eventos con clase 5 en celda de coordenada | Celda de coordenada con fuego | Eventos con fuego a 10 km de coordenada | Buffers de ruta con fuego | Buffers con clase 5 |
|---|---:|---:|---:|---:|---:|
| Suomi-NPP | 16 | 0 | 2 | 2 | 16 |
| NOAA-20 | 16 | 0 | 1 | 1 | 16 |
| NOAA-21 | 16 | 0 | 1 | 1 | 16 |

Agrupando los dos clusters del mismo día y ruta, hubo detecciones VIIRS clase 7–9 a menos de 10 km de la coordenada reportada en **2/15 fechas-ruta** (13.3% de coincidencia descriptiva). Las celdas exactas de las coordenadas reportadas fueron clase 5 terrestre en los tres sensores en las 15 fechas-ruta. Esto muestra que la coordenada del parte no coincide necesariamente con el píxel de fuego y que el radio de búsqueda importa.

La cohorte solo contiene positivos candidatos del SNMF; por eso esta fracción no es precisión, sensibilidad frente a todos los incendios, tasa de falsas alarmas ni desempeño predictivo. Las fechas sin detección cercana siguen siendo desconocidas, aunque la celda reportada haya sido clase 5. Los compuestos diarios no identifican hora de ignición, y varios sensores o reportes pueden corresponder al mismo incendio. No se crearon datos sintéticos ni etiquetas negativas.

Definiciones del producto: [guía oficial NASA VIIRS](https://viirsland.gsfc.nasa.gov/PDF/VIIRS_activefire_User_Guide.pdf) y [especificación HDF5 NASA LAADS](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14A1).

Resultados reproducibles: [fire-viirs-daily-l3-snmf-event-audit-2023-2025.json](fire-viirs-daily-l3-snmf-event-audit-2023-2025.json); [manifiesto de adquisición con hashes](fire-viirs-daily-l3-acquisition-manifest-2023-2025.json); auditor: [`audit_viirs_daily_l3_snmf_route_events.py`](../../training/python/audit_viirs_daily_l3_snmf_route_events.py).
