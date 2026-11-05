# VIIRS: observaciones por pasada junto a Bosque Tallado

Se emparejaron y verificaron 61 máscaras VIIRS con sus granulas de geolocalización completa para 61 tiempos de sobrepaso entre el 4 y el 10 de enero de 2026.

En el buffer de 10 km del sendero hubo 95334 píxeles clase 5 (tierra despejada sin detección en esa pasada) y 0 detecciones clase 7–9 tras el filtro de QA. 60 de 61 pasadas tuvieron al menos un píxel clase 5; 0 tuvieron una detección clase 7–9.

Estos son conteos de observación por pasada, no incendios ni episodios de alerta independientes. Una clase 5 solo respalda una no-detección durante esa observación; las nubes, clases no clasificadas, píxeles inválidos y ventanas sin cobertura permanecen desconocidos. No se estima precisión del modelo.

El [JSON reproducible con resultados por pasada, reglas y hashes](fire-viirs-full-swath-route-observations-barda-2026-jan.json) se generó con [`audit_viirs_full_swath_route_observations.py`](../../training/python/audit_viirs_full_swath_route_observations.py). Los archivos VIIRS permanecen en un directorio privado ignorado por Git.
