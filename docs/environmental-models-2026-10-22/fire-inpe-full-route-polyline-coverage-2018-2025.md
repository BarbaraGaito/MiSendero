# Detecciones INPE sobre trazados completos (2018–2025)

Se compararon las detecciones del satélite de referencia AMS de INPE con las ocho polilíneas completas de los senderos argentinos de MiSendero. La distancia se calculó en un plano local por ruta; se analizaron buffers de 2, 5, 10 y 20 km. Los ZIP anuales, sus hashes, la geometría, los conteos por sendero y las secuencias temporales están en el [JSON reproducible](fire-inpe-full-route-polyline-coverage-2018-2025.json). El análisis se reproduce con [`audit_inpe_reference_detections_route_polylines.py`](../../training/python/audit_inpe_reference_detections_route_polylines.py).

A 5 km se encontraron 27 días-sector con detecciones en los ocho años: 6 en 2018, 0 en 2019, 4 en 2020, 6 en 2021, 2 en 2022, 2 en 2023, 1 en 2024 y 6 en 2025. Al agrupar días-sector detectados en fechas consecutivas, quedan 21 secuencias temporales; no se puede asegurar que cada secuencia sea un incendio único. En 2025, cinco detecciones diarias consecutivas cerca de Quebrada del Condorito forman una sola secuencia, y una detección cercana a Frey forma otra.

El aumento del radio eleva la cobertura positiva (86 días-sector a 10 km y 310 a 20 km), pero amplía la zona que ya no representa el entorno inmediato del sendero y no crea observaciones negativas. El satélite de referencia puede omitir incendios por horario de pasada, nubes, tamaño o cobertura del terreno; además, una detección activa no distingue por sí sola un incendio forestal de una quema controlada.

Este conjunto sirve para ubicar y corroborar algunos positivos. No contiene días despejados observados ni todos los incendios, así que no permite calcular precisión, elegir un umbral fiable ni afirmar rendimiento predictivo. Tampoco corresponde contar cada día consecutivo como un caso independiente. El resultado no valida ni reemplaza los modelos actuales.

El MAP_KEY de FIRMS no se utilizó en esta auditoría. La búsqueda de detecciones INPE usa los archivos públicos descargados previamente y es independiente de la clave NASA.
