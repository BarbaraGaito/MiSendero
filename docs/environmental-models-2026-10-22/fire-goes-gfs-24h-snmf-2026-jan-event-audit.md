# Auditoria independiente SNMF del modelo GFS+GOES a 24 h

## Resultado

Se cruzo el conjunto de prueba temporal de enero de 2026 con los partes diarios oficiales SNMF. De 91 incidentes activos/controlados con fecha de inicio reportada en enero, cuatro quedaron a 10 km o menos de un centro de sector de trekking y tuvieron puntaje del modelo disponible. Los cuatro recibieron alerta al corte diagnostico 0.5: sensibilidad observada 4/4 (100 %; intervalo exacto binomial descriptivo del 95 %: 39.8-100 %). La persistencia satelital al emitir el pronostico no habia detectado esos fuegos (0/4).

| Incidente oficial | Ruta/sector usado | Distancia al centro | Score GFS+GOES |
|---|---|---:|---:|
| Barda de La Loma | Bosque Tallado | 6.290 km | 0.832 |
| Cantera Eva Peron | Refugio Frey | 9.708 km | 0.850 |
| Vertedero Municipal (registros agrupados) | Refugio Frey | 9.284 km | 0.811 |
| P.N. Lihue Calel | Sendero Namuncura | 1.615 km | 0.788 |

## Como interpretar el cruce

Es evidencia positiva e independiente de la etiqueta GOES usada para entrenar y evaluar el score: cuatro eventos SNMF cercanos a sectores cubiertos recibieron alerta. No basta para afirmar fiabilidad. El intervalo es amplio por el tamano de muestra; solo cuatro de los 91 incidentes entraron en la zona espacial y temporal con cobertura del modelo. Los registros SNMF no forman un censo exhaustivo de lugares y dias sin incendios, asi que este cruce no da precision, tasa de falsas alarmas ni calibracion. El corte 0.5 es diagnostico y no fue seleccionado por esta auditoria.

El parte solo da fecha de inicio, no hora. Por tanto, aunque el predictor usa un pronostico meteorologico emitido 24 h antes de la observacion GOES objetivo, este cruce no demuestra que la alerta antecediera la ignicion por 24 h. El radio de 10 km se mide desde centros de sectores, no desde cada tramo de la geometria del sendero ni desde infraestructura de seguridad; no es un radio validado para recomendar cancelar una salida. El archivo SNMF omitio una fecha del mes y los reportes faltantes no se trataron como negativos. Los registros del vertedero con coordenadas a menos de 1 km se agruparon para reducir alias/dobles conteos; esa regla tambien podria fusionar dos incendios vecinos.

## Reproduccion

`evaluate_goes_gfs_previous_runs.py` genera las metricas temporales, guarda 240 puntajes de ruta-sector-dia del test y crea el cruce de eventos. Datos extraidos, protocolo, fuentes y huellas: [`goes-gfs-24h-snmf-2026-jan-event-audit.json`](goes-gfs-24h-snmf-2026-jan-event-audit.json) y [`fire-goes-gfs-24h-evaluation.json`](fire-goes-gfs-24h-evaluation.json). La fuente primaria es el archivo de partes diarios SNMF procesado en [`snmf-2026-jan-daily-occurrence-events.json`](snmf-2026-jan-daily-occurrence-events.json).

Estado: resultado exploratorio prometedor para sensibilidad entre eventos cubiertos, insuficiente para fiabilidad general o uso en recomendaciones de seguridad. No se modifico el modelo de produccion ni se aprobo el despliegue.
