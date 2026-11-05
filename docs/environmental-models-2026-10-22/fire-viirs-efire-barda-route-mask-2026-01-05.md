# NOAA VIIRS E-FIRE: píxeles observados cerca de Barda, 5/1/2026

Se descargaron desde el bucket público NOAA NODD y se verificaron con SHA-256 dos máscaras E-FIRE I-band v1r3 y sus geolocalizaciones completas GITCO (193,5 MB en total). Los pasos ocurrieron a las 04:31:17 UTC (NOAA-21) y 05:01:10 UTC (S-NPP).

En ambos pasos, el píxel más cercano a la coordenada del parte SNMF de Barda de La Loma quedó a menos de 200 m y fue clase 5, con DQF 1: tierra despejada procesada con calidad y sin fuego detectado en ese instante. Sobre 103 vértices muestreados de Bosque Tallado, NOAA-21 resolvió 103 como tierra despejada; S-NPP resolvió 44 como tierra despejada y 59 como bowtie eliminado. Ninguno de esos vértices muestreados tuvo clase de fuego 7–9.

La evidencia es útil para construir etiquetas de observación: clase 5 + DQF 1 es una no-detección válida en ese píxel y momento. No demuestra que el incendio reportado no existiera; el parte da fecha y estado, pero no hora exacta de inicio, y los sensores pueden omitir focos pequeños u ocultos. Dos pasos de un evento no estiman la precisión de una predicción ni justifican avisos de seguridad.

La semántica DQF se tomó de la [guía técnica oficial NOAA E-FIRE v1.3, sección 5.2](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EFIRE_v1.3.pdf); NOAA describe E-FIRE VIIRS como producto de 375 m por granula en su [página del producto](https://www.ospo.noaa.gov/products/land/efire.html). Resultados por vértice, geometría y hashes: [JSON reproducible](fire-viirs-efire-barda-route-mask-2026-01-05.json). Auditoría de las máscaras: [NOAA-21](fire-viirs-efire-route-mask-barda-2026-01-05-n21.json), [S-NPP](fire-viirs-efire-route-mask-barda-2026-01-05-npp.json), [punto SNMF NOAA-21](fire-viirs-efire-barda-point-2026-01-05-n21.json) y [punto SNMF S-NPP](fire-viirs-efire-barda-point-2026-01-05-npp.json).

Reproducción: [`audit_viirs_efire_route_mask_pilot.py`](../../training/python/audit_viirs_efire_route_mask_pilot.py) seguido de [`audit_viirs_efire_barda_route_passes.py`](../../training/python/audit_viirs_efire_barda_route_passes.py). Los archivos binarios quedan privados y excluidos de Git.
