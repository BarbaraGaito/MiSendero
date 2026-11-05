# Ampliación de partes SNMF para evaluación de alertas cerca de senderos

## Qué se incorporó

Se descargaron partes diarios oficiales del SNMF disponibles entre el 1 de enero y el 19 de noviembre de 2024. Se revisaron 324 fechas: hay PDF válido para 277 y faltan 47 en las rutas públicas comprobadas. Los PDF ausentes permanecen como desconocidos. Un extractor por coordenadas produjo 3.450 filas de estado, deduplicadas en 1.835 incidentes; 44 filas de estado no tenían coordenadas y no se usaron para asociaciones espaciales.

Para ampliar la comprobación de reportes a lo largo del tiempo, se construyó un proxy diario por cada uno de los ocho centros de sector asociados a senderos. A 10 km, una etiqueta positiva significa que un parte del mismo día lista un incendio activo/no resuelto, o que un parte posterior documenta un inicio ocurrido ese día. Una etiqueta negativa significa únicamente que el parte disponible no lista un incidente cercano. No significa que se haya confirmado ausencia física de fuego. Si no existe el PDF de la fecha, el ejemplo es desconocido, salvo que un parte posterior documente un inicio cercano en esa fecha.

## Tamaño de la cohorte reportada

| Período | Partes disponibles | Días-sector con etiqueta a 10 km | Positivos reportados | Sin incidente cercano listado | Desconocidos por PDF faltante | Inicios SNMF cercanos: días-sector |
|---|---:|---:|---:|---:|---:|---:|
| Jul–dic 2023 | 119/184 | 952 | 5 | 947 | 520 | 2 |
| Ene–19 nov 2024 | 277/324 | 2.218 | 9 | 2.209 | 374 | 8 |
| 2025 | 207/365 | 1.656 | 25 | 1.631 | 1.264 | 4 |
| Ene 2026 | 30/31 | 240 | 31 | 209 | 8 | 6 |
| **Total** | **633/904** | **5.066** | **70** | **4.996** | **2.166** | **20** |

Los 70 positivos diarios no son 70 incendios independientes: varias filas corresponden al mismo incendio mientras siguió apareciendo en los partes. Los 20 inicios son días-sector, tampoco necesariamente 20 eventos únicos entre sectores. A 20 km aparecen 201 días-sector positivos, pero esa distancia excede la escala del sendero y aumenta el riesgo de atribuirle un incendio lejano. La métrica no se cambia a 20 km para mejorar artificialmente el conteo.

## Pronóstico GFS disponible para un ensayo

Se descargó el archivo público Open-Meteo Previous Runs para las ocho zonas entre el 1/1 y el 19/11/2024: 7.776 horas por zona para temperatura, humedad relativa, viento y precipitación pronosticados con 24 h de anticipación. En todas las variables faltan las primeras 444 horas (18,5 días), por lo que cualquier prueba tendría que excluirlas. El archivo comprimido ocupa 378.444 bytes y su respuesta original tiene SHA-256 `277f3e2fe1446043a3ba7103810d59d6f2d2e47a8f1c185bd883f5f13b517d76`. Está guardado en el directorio privado ignorado por Git, con parámetros y procedencia en el manifiesto correspondiente.

Este emparejamiento permite una prueba exploratoria del objetivo **“incidente reportado cerca del sendero”** con corte temporal. No autoriza a interpretar la puntuación como probabilidad de ignición, validar ausencia física de fuego ni afirmar precisión real: los negativos son ausencia de reporte local, la vigilancia jurisdiccional no es exhaustiva y la cohorte de inicios cercanos sigue siendo pequeña y agrupada.

## Comprobación externa del modelo GFS+GOES de 24 h

Se cruzó el proxy refinado de enero de 2026 con las predicciones de la prueba temporal ya congelada del modelo GFS+GOES. No se reajustó el modelo ni se movió el umbral diagnóstico 0,5. En 232 días-sector con parte y predicción, hubo 31 etiquetas positivas: 29 alertas coincidieron con un incidente reportado cercano y 2 no fueron alertadas; otras 104 alertas no coincidieron con un incendio listado. La precisión **frente al proxy** fue 21,8 % y el recall 93,5 %. Persistencia coincidió con 3 de 23 alertas (13,0 %) y tuvo recall 9,7 % en esta misma comparación.

Al agrupar días consecutivos por sector, 4 de 22 rachas de alertas del modelo coincidieron con al menos un día positivo del proxy (18,2 %); persistencia coincidió en 1 de 8 rachas (12,5 %). Esto sugiere una mejor captura de reportes que persistencia en esta cohorte, pero el modelo aún produce muchas alertas sin incendio reportado cerca. Como no todos esos avisos son falsos incendios confirmados, no se interpreta el 21,8 % como precisión física. Tampoco alcanza una precisión fiable para avisar al usuario de que habrá fuego. La salida reproducible está en [`fire-goes-gfs-snmf-route-day-proxy-2026-jan.json`](fire-goes-gfs-snmf-route-day-proxy-2026-jan.json) y se calcula con [`evaluate_goes_gfs_snmf_route_day_proxy.py`](../../training/python/evaluate_goes_gfs_snmf_route_day_proxy.py).

## Índices oficiales de peligro

La [página oficial del SNMF](https://www.argentina.gob.ar/seguridad/servicio-nacional-de-manejo-del-fuego/evaluacion-de-peligro-y-alerta-temprana/mapa-de) describe un índice meteorológico calculado con estaciones del SMN y GFS y publica estimaciones a +24, +48 y +72 horas. Eso es peligro meteorológico, no una probabilidad de que se inicie un incendio. La [página oficial de CONAE](https://www.argentina.gob.ar/node/87226) describe el FFDI operacional como dato descargable; sin embargo, el visor de CAEARTE agotó el tiempo de espera en esta sesión. La página de pronóstico FWI del SMN respondió 403 al acceso automatizado; sí se pudo consultar su PDF metodológico. No se encontró un archivo histórico público de mapas nacionales de peligro con fecha de emisión y validez.

El [histórico de índices de peligro de CEMS](https://ewds.climate.copernicus.eu/datasets/cems-fire-historical-v1) ofrece reanálisis diarios, pero requiere iniciar sesión y aceptar la licencia. Un reanálisis describe condiciones meteorológicas retrospectivas; no sustituye las emisiones de pronóstico que habrían estado disponibles antes del incendio.

## Resultado para la tesis

La ampliación documenta 20 inicios reportados en días-sector a 10 km en los cuatro tramos disponibles, además de reportes de incendios en curso. La evidencia todavía no alcanza una evaluación independiente y suficientemente grande para afirmar una precisión fiable del modelo. El modelo GFS+GOES previamente evaluado en enero de 2026 tampoco superó persistencia en precisión de avisos: 24/136 frente a 16/23, y solo cuatro de 91 incidentes nacionales quedaron cubiertos por la regla espacial usada en la comparación oficial.

Se debe mantener el detector como experimental. La siguiente prueba podrá comparar el GFS de 24 h con esta etiqueta administrativa, agrupando por episodio y reservando el período final; sus resultados deben nombrarse como precisión respecto de **incendios reportados**, no de todos los incendios reales. Para afirmar precisión de seguridad por sendero siguen faltando partes exhaustivos o ventanas de vigilancia con cobertura confirmada, hora de inicio suficientemente precisa y más episodios independientes.

## Candidato meteorológico separado

Se entrenó una regresión logística con siete resúmenes diarios del pronóstico GFS y una categoría por sector. El corte temporal fue 2024-01-20–2025-11-30 para entrenamiento, diciembre de 2025 para validación y enero de 2026 para prueba. El entrenamiento tuvo 3.490 días-sector y 29 positivos; la validación tuvo 248/4 y la prueba 240/31. Ningún umbral de validación alcanzó 80 % de precisión proxy con al menos cinco alertas. En la prueba, el corte diagnóstico fijo 0,5 dio 16/109 coincidencias (14,7 %), recall proxy 51,6 % y average precision 0,160 frente a prevalencia 0,129; Brier 0,284 fue peor que el baseline de prevalencia constante (0,127). Solo seis días-sector de inicio de incendio estaban representados en el test. No es una predicción fiable y el resultado no se utiliza en la app. El JSON reproducible es [`fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json`](fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json); el script es [`train_snmf_report_proxy_gfs_model.py`](../../training/python/train_snmf_report_proxy_gfs_model.py).

## Reproducción

```powershell
.venv-ai\Scripts\python.exe training/python/acquire_snmf_daily_reports_2024.py
.venv-ai\Scripts\python.exe training/python/extract_snmf_daily_events.py --source-dir training/data/environmental/private/snmf-daily-occurrence-2024 --output docs/environmental-models-2026-10-22/snmf-2024-daily-occurrence-events.json
.venv-ai\Scripts\python.exe training/python/audit_snmf_route_event_coverage.py --year 2024
.venv-ai\Scripts\python.exe training/python/audit_snmf_report_day_proxy.py --year 2024
```

Los reportes legibles por máquina son [`snmf-2024-daily-occurrence-events.json`](snmf-2024-daily-occurrence-events.json), [`fire-snmf-route-event-coverage-2024.json`](fire-snmf-route-event-coverage-2024.json), [`snmf-2024-route-day-report-proxy.json`](snmf-2024-route-day-report-proxy.json), [`fire-goes-gfs-snmf-route-day-proxy-2026-jan.json`](fire-goes-gfs-snmf-route-day-proxy-2026-jan.json), [`fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json`](fire-gfs-snmf-report-proxy-temporal-evaluation-2026-jan.json) y el manifiesto privado de adquisición.
