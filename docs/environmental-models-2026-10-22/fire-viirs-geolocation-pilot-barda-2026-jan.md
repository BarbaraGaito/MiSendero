# Piloto VIIRS con geolocalización completa: Barda de La Loma

Se emparejaron los productos NASA VNP14IMG y VNP03IMG de la pasada del 7 de enero de 2026 a las 04:24 UTC. Ambos gránulos tienen la misma grilla de 6464 × 6400 píxeles y se verificaron contra sus manifiestos SHA-256.

En el radio de 10 km alrededor de la polilínea Bosque Tallado se identificaron 676 píxeles de tierra con geolocalización válida y QA aceptable, de los cuales 637 fueron clase 5 (tierra despejada sin fuego detectado en este paso) y 0 clase 7–9 (fuego detectado).

Este paso demuestra que las granulas compañeras permiten distinguir una observación válida sin detección de una zona no observada. La clase 5 no prueba ausencia física de fuego entre pasadas ni sirve por sí sola para medir precisión; se necesita una cohorte de rutas, ventanas y pronósticos históricos congelados.

Los dos NetCDF y sus manifiestos permanecen en `training/data/environmental/private/`, excluidos de Git. El [JSON reproducible](fire-viirs-geolocation-pilot-barda-2026-jan.json) contiene conteos, reglas y hashes. Reproducción: [`audit_viirs_geolocation_pilot.py`](../../training/python/audit_viirs_geolocation_pilot.py).
