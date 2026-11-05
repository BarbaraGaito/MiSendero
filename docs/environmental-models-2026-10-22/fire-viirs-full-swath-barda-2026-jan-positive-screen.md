# VIIRS Collection 2: detecciones alrededor de Barda de La Loma

Se descargaron y verificaron 61 granulas (96.47 MB) de S-NPP, NOAA-20 y NOAA-21 para siete días alrededor del parte SNMF de Barda de La Loma. La búsqueda encontró 10070 registros de fuego en las granulas completas; son detecciones repetidas por paso, no incendios independientes.

Dentro de 10 km de la polilínea Bosque Tallado hubo 0 registros clase 7–9 y 0 tras el filtro de QA; dentro de 10 km de la coordenada SNMF hubo 0 y 0, respectivamente. Las detecciones QA válidas más cercanas quedaron a 12.615 km del sendero y 11.309 km del punto SNMF. El conteo detallado y hashes están en el [JSON reproducible](fire-viirs-full-swath-barda-2026-jan-positive-screen.json).

Este cruce permite afirmar si el producto registró un foco cercano en un paso; no permite afirmar que no hubo fuego cuando no hay un FP, porque la geolocalización completa de todos los píxeles se distribuye en otro producto. Tampoco fija el orden entre la pasada y el inicio informado por SNMF. Por eso no mide la precisión de una predicción ni transforma ausencias en negativos.

La máscara clasifica 7/8/9 como fuego de confianza baja/nominal/alta. El filtro QA exige bits de calidad de entrada 0–6 en cero y excluye los indicadores de anomalía del Atlántico Sur, fuego sobre agua y bowtie residual, según la [guía oficial NASA VIIRS Collection 2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf). El producto y la geolocalización completa corresponden a fuentes distintas: [VNP14IMG en LAADS](https://ladsweb.modaps.eosdis.nasa.gov/filespec/VIIRS/1/VNP14IMG).

Reproducción: [`audit_viirs_full_swath_barda_2026_jan.py`](../../training/python/audit_viirs_full_swath_barda_2026_jan.py). Los 61 NetCDF descargados y el manifiesto permanecen en `training/data/environmental/private/viirs-full-swath-barda-2026-jan/`, excluidos de Git.
