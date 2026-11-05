# Captura prospectiva de Risco de Fogo INPE sobre senderos argentinos

## Resultado de esta captura

Se descargó el GeoTIFF público `RF.PREV.T1.tif` desde el servidor oficial del INPE. La respuesta tuvo 19.062.007 bytes y `Last-Modified: Thu, 22 Oct 2026 09:27:37 GMT`. El archivo declara una corrida inicializada el **22/10/2026 00:00 UTC**, emitida a las 09:23 UTC, y validez el **23/10/2026 18:00 UTC**. Para esa validez, el anticipo es de 42 horas desde el ciclo inicial, no una etiqueta genérica de “24 h”.

Una nueva consulta el 23/10/2026 a las 05:51 UTC revisó los cuatro horizontes T0–T3. El SHA-256, corrida, validez y metadatos no indicaron una nueva emisión; el capturador omitió correctamente una segunda copia idéntica. Por ello todavía no hay una nueva observación prospectiva que evaluar.

La grilla es EPSG:4326, 0,01° y cubre las ocho coordenadas de senderos argentinos del catálogo. Se muestreó el píxel en el centro de cada sendero y se resumieron píxeles dentro de radios aproximados de 5 y 10 km. Los centros y radios son aproximaciones geográficas: no son líneas completas de los recorridos ni representan automáticamente el área que transitará una persona.

| Sendero | Puntual | Mediana a 5 km | P90 a 5 km | Máximo a 5 km |
|---|---:|---:|---:|---:|
| Macuco – Salto Arrechea | 0,00 | 0,00 | 0,00 | 0,00 |
| Refugio Frey desde Villa Catedral | 0,00 | 0,00 | 0,00 | 0,00 |
| Quebrada del Condorito – Balcón Norte | 0,95 | 0,94 | 0,94 | 0,95 |
| Sendero Namuncurá | 0,67 | 0,66 | 0,83 | 0,90 |
| Cerro Ventana – Hueco de la Ventana | 0,84 | 0,85 | 0,86 | 0,87 |
| Bosque Tallado – plataforma del Piltriquitrón | 0,00 | 0,00 | 0,00 | 0,00 |
| Che Roga – Mburucuyá | 0,57 | 0,47 | 0,81 | 0,82 |
| La Chuña – El Rey | 0,81 | 0,81 | 0,83 | 0,84 |

Los ceros son valores contenidos en el raster, no faltantes. En un radio de 10 km aparecen máximos de hasta 1,00 en algunas zonas; ese máximo espacial no debe confundirse con el valor de todo el sendero. La tabla prueba que se puede recuperar y asociar un **score espacial de peligro** actual a los puntos del catálogo. No prueba que el score anticipe correctamente un incendio.

## Qué hace falta para hablar de precisión

El INPE publica en esa carpeta las corridas vigentes T0–T3 y no se encontró un archivo abierto de emisiones anteriores. Por ello no se puede reconstruir ahora qué score estaba disponible antes de los incendios históricos. Un snapshot sin observaciones posteriores tampoco permite calcular precisión, sensibilidad, falsas alarmas ni calibración. Además, el producto declara un score de peligro, no una probabilidad de ignición calibrada para Argentina.

El INPE sí conserva mapas diarios del **Risco de Fogo observado** en anuarios retrospectivos, por ejemplo 2024. Su propia metodología indica que ese cálculo observado se corrige usando focos detectados en los tres días anteriores. Sirve como serie de peligro observado para asociaciones descriptivas, pero no sustituye el archivo de las emisiones T0–T3: evaluarlo como si fuera el pronóstico que se conocía antes del evento mezclaría información observada con el resultado. La metodología y la distinción entre observado y previsto están en el [Anuário Risco de Fogo 2024](https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/anuario_risco_de_fogo/anuario_risco_de_fogo_2024.pdf) y el [portal de datos abiertos](https://data.inpe.br/queimadas/dados-abertos/).

Se agregó un capturador prospectivo que guarda únicamente JSON compacto por corrida; descarga temporalmente los GeoTIFF y los elimina al terminar. Para reunir evidencia deben ejecutarse capturas diarias durante una temporada completa como mínimo, con fecha/hora de emisión y validez. Luego hay que enlazarlas con inicios de incendio confirmados y con negativos de vigilancia conocida, agrupar detecciones repetidas por episodio y evaluar los umbrales en una temporada que no se haya usado para seleccionarlos. Los partes incompletos no deben convertirse en negativos.

La descarga del snapshot actual se conserva como evidencia pequeña en [`capture_20261023T040732Z.json`](../../training/data/environmental/inpe_fire_forecasts/capture_20261023T040732Z.json). La fuente original fue `https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/previsto/risco_fogo/RF.PREV.T1.tif`; su SHA-256 es `8a10ff44819c957f5776465747e6eb637b5997c0b7d0e5147cbe708e14f0ee5f`. El hash del catálogo geográfico usado es `7e475b478db7bb678cc0a1539fdf484e0c8de0a9baa98916fb90f652f75ff834`.

Para iniciar el archivo diario con Python del entorno del proyecto:

```powershell
.venv-ai\Scripts\python.exe training/python/archive_inpe_fire_forecast_routes.py
```

Esto guarda una captura JSON de los archivos vigentes T0–T3 en `training/data/environmental/inpe_fire_forecasts/`. El capturador es de investigación; no modifica la app, no activa alertas y no declara aprobado ningún modelo. Las condiciones de redistribución del producto deben verificarse antes de publicar los archivos derivados.

## Límites de resolución

Aunque el GeoTIFF tiene píxeles de 0,01° (cerca de 1 km), las variables GFS que alimentan el producto tienen una escala aproximada de 50 km. El detalle aparente del raster no equivale a meteorología pronosticada independientemente en cada kilómetro. Los radios sirven para describir variación local del score y cobertura; no constituyen una evaluación a nivel de segmento de sendero.

Fuentes técnicas y antecedentes: [datos abiertos de Queimadas/INPE](https://data.inpe.br/queimadas/dados-abertos/), [directorio público de GeoTIFF previstos](https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/previsto/risco_fogo/) y [auditoría de fuentes históricas de índices de peligro](fire-historical-danger-index-source-audit.md).
