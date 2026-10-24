# Global Fire Atlas: igniciones diarias cerca de rutas argentinas

Se filtraron las capas anuales de puntos GFA para las temporadas locales 2022–2026, usando los puntos y fechas del propio shapefile. El ZIP se leyó directamente, sin extraer sus 8,65 GB de contenido. El buffer es de 10 km alrededor de las polilíneas completas revisadas.

El filtro encontró **20 registros evento-ruta** en **20 combinaciones ruta-incendio** y **17 fechas de inicio distintas**. Las capas examinadas contienen 3,281,923 puntos de ignición globales. No son observaciones independientes para una métrica de precisión.

## Cobertura por temporada de inicio

| Año de `start_date` | Registros evento-ruta |
|---:|---:|
| 2022 | 5 |
| 2023 | 11 |
| 2024 | 2 |
| 2025 | 2 |

## Interpretación

Este resultado agrega candidatos de eventos positivos basados en área quemada, independientes de los reportes administrativos. GFA deriva las igniciones y fechas de MCD64A1: la fecha tiene resolución diaria, no hora observada, y el producto puede omitir fuegos menores a aproximadamente un píxel MODIS. Por eso no valida predicciones con horizonte horario y no reemplaza la adjudicación de incidentes argentinos.

La lista solo contiene fuegos detectados. No ofrece días-ruta verificados sin fuego; por tanto, no permite calcular precisión, tasa de falsas alarmas ni una probabilidad. Se debe deduplicar y contrastar con SNMF, perímetros oficiales y detecciones de otros sensores antes de usar los puntos como positivos de prueba.

En el cruce positivo exploratorio (regla de ±2 días y 10 km no preregistrada), **16/20** registros tuvieron una detección INPE cercana y **2/20** coincidieron con el subconjunto SNMF georreferenciado. Son corroboraciones descriptivas; INPE puede compartir plataformas con MODIS y los reportes SNMF usados son seleccionados, por lo que estos conteos no miden precisión ni recall general.

Los años 2025 y 2026 corresponden a temporadas de fuego local y la versión 2026 advierte que las temporadas más recientes pueden estar incompletas.

La salida reproducible con todos los casos, tamaños, coordenadas, fechas y hashes está en el [JSON](fire-global-fire-atlas-route-ignitions-2022-2026.json). El archivo fuente original está bajo `training/data/environmental/private/` y no se incluye en la APK.

Fuente: [Global Fire Atlas 2026, Zenodo 17669692](https://zenodo.org/records/17669692); metodología: [Andela et al., 2019](https://doi.org/10.5194/essd-11-529-2019).
