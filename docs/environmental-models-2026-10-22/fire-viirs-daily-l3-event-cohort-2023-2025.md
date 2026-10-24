# Cohorte de eventos SNMF para piloto VIIRS diario

Esta auditoria selecciona eventos oficiales SNMF 2023–2025 con coordenadas a menos de 10 km de las ocho rutas argentinas mapeadas. Los compuestos diarios VIIRS de la cohorte fueron descargados y auditados; el cruce es de corroboración de positivos y no calcula métricas de precisión del modelo.

Se encontraron **20 registros fuente** dentro del buffer y se agruparon en **16 eventos por ruta y fecha de inicio** (4 registros con nombres repetidos colapsados). El plan inicial tiene 15 fechas, 15 combinaciones fecha-tile de las rutas involucradas y un máximo de 45 granulos para los tres productos diarios.

| Fecha de inicio SNMF | Ruta | Incidente reportado | Provincia | Distancia a ruta | Estado en parte |
|---|---|---|---|---:|---|
| 2023-10-06 | Quebrada del Condorito - Balcon Norte | RIO DE LA SUELA | CÓRDOBA | 7.4 km | CONTENIDO |
| 2023-12-19 | Bosque Tallado desde la plataforma del Piltriquitron | Quema golondrinas | Chubut | 5.2 km | EXTINGUIDO |
| 2024-01-06 | Bosque Tallado desde la plataforma del Piltriquitron | El Eden (Las Golondrinas) | Chubut | 7.2 km | EXTINGUIDO |
| 2024-01-26 | Bosque Tallado desde la plataforma del Piltriquitron | Callejon Los Lupinos | Chubut | 8.6 km | EXTINGUIDO |
| 2024-01-30 | Sendero Namuncura | Tranquerón | La Pampa | 4.6 km | CONTENIDO |
| 2024-02-03 | Cerro Ventana - Hueco de la Ventana | Parque Provincial Ernesto | Buenos Aires | 8.0 km | EXTINGUIDO |
| 2024-03-07 | Bosque Tallado desde la plataforma del Piltriquitron | Lote 1 campo INTA | Chubut | 5.2 km | EXTINGUIDO |
| 2024-04-16 | Bosque Tallado desde la plataforma del Piltriquitron | Camping | Chubut | 9.0 km | EXTINGUIDO |
| 2024-09-15 | Bosque Tallado desde la plataforma del Piltriquitron | Golondrinas RN 40 | Chubut | 5.4 km | EXTINGUIDO |
| 2024-10-16 | Refugio Frey desde Villa Catedral | Dos Valles | Río Negro | 8.0 km | CONTROLADO |
| 2025-10-08 | Bosque Tallado desde la plataforma del Piltriquitron | Ruta 40 Control Policial | Chubut | 4.3 km | EXTINGUIDO |
| 2025-10-08 | Bosque Tallado desde la plataforma del Piltriquitron | Cerro Radal | Chubut | 9.5 km | EXTINGUIDO |
| 2025-10-10 | Quebrada del Condorito - Balcon Norte | Parque Nacional Quebrada del, Parque Nacional Quebrada del Condorito, ex, Parque Nacional Quebrada del Condorito, ex La, Parque Nacional Quebrada del Condorito, ex La Pampilla | Córdoba | 3.5 km | ACTIVO |
| 2025-11-17 | Bosque Tallado desde la plataforma del Piltriquitron | Ternero Los fuegos | Río Negro | 7.2 km | EXTINGUIDO |
| 2025-11-26 | Refugio Frey desde Villa Catedral | Ladera Norte Cerro, Ladera Norte Cerro Otto | Río Negro | 8.1 km | CONTROLADO |
| 2025-12-11 | Cerro Ventana - Hueco de la Ventana | CERRO NAPOSTA /CERRO | Buenos Aires | 8.4 km | CONTENIDO |

La fecha es la fecha de inicio informada por SNMF, no una hora de ignición comprobada. La proximidad de un punto del parte a una ruta tampoco confirma que el sendero estuviera afectado. Esta cohorte contiene positivos candidatos, sin negativos: no permite afirmar precisión, especificidad ni tasa de falsas alarmas.

Como control de factibilidad, se cruzaron los 6 eventos seleccionados de 2025 con la auditoria de pasadas VIIRS E-FIRE de 375 m ya disponible: {"clear_land_without_detection_at_overpass": 1, "no_matched_overpass_in_downloaded_cohort": 3, "unknown_quality_or_nonland": 2}. Los pasos sobre nubes y la falta de pasada coincidente quedan como desconocidos; incluso una clase de tierra despejada sin deteccion solo describe el instante del paso y no fija si el incendio estaba activo en ese momento.

La adquisición usa como máximo 45 granulos de `VNP14A1.002`, `VJ114A1.002` y `VJ214A1.002`; el manifiesto privado registra 45 descargados/presentes. La auditoria separada comprueba sus bytes y SHA-256. Los compuestos clase 5 solo representan tierra despejada sin detección asignada en ese producto; no demuestran ausencia física de fuego.

Fuentes privadas locales (no incluidas en Git): geometría `training/data/environmental/private/fire-route-geometries.json` y reportes SNMF 2023–2025. Hashes y cohorte reproducible en [fire-viirs-daily-l3-event-cohort-2023-2025.json](fire-viirs-daily-l3-event-cohort-2023-2025.json). Reproducción: [`audit_viirs_daily_l3_event_cohort.py`](../../training/python/audit_viirs_daily_l3_event_cohort.py).
