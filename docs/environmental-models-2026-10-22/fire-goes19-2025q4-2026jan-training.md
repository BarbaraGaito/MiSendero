# Evaluación exploratoria de detecciones GOES-19

Se incorporó una temporada de GOES-19, satélite operativo como GOES-East desde abril de 2025. El protocolo cubre del 1 de octubre de 2025 al 31 de enero de 2026 y usa 1.858 píxeles fijos de ocho sectores argentinos del catálogo de trekking. Las escenas originales proceden del bucket público de NOAA. No se generaron datos sintéticos.

La separación es temporal: objetivos anteriores al 1 de diciembre para entrenamiento, diciembre para validación y enero para prueba. El objetivo es la detección de fuego de alta calidad en el mismo píxel en una escena futura. No representa el inicio de un incendio, su propagación ni la seguridad de un sendero. Se excluyeron las clases con calidad dudosa y se dejaron faltantes las horas sin escena.

Se ajustó regresión logística con ponderación de clases y se comparó su área bajo la curva precisión-recall (AP) con una regla de persistencia: reutilizar el estado reciente del mismo píxel. Las métricas son sobre filas de píxeles y, por eso, cuentan repetidamente detecciones cercanas en el tiempo.

| Adelanto | AP modelo en enero | AP persistencia | Precisión modelo a 0,5 | Recall modelo a 0,5 | Positivos de prueba |
|---:|---:|---:|---:|---:|---:|
| 1 h | 0,3749 | 0,3706 | 70,27 % | 19,12 % | 136 |
| 2 h | 0,00015 | 0,1466 | 0 % | 0 % | 130 |
| 3 h | 0,00015 | 0,0747 | 0 % | 0 % | 128 |
| 6 h | 0,00017 | 0,0347 | 0 % | 0 % | 140 |
| 12 h | 0,00017 | 0,0142 | 0 % | 0 % | 130 |

Aunque el resultado de 1 hora apenas supera a persistencia en AP, su recall es 19 %. Los horizontes de 2, 3, 6 y 12 horas no superan a persistencia en AP; a umbral 0,5 no emiten detecciones. Los puntajes de este ajuste ponderado no son probabilidades calibradas, así que 0,5 no debe presentarse como “50 % de probabilidad”.

En enero, según el horizonte, hubo entre 23 y 25 combinaciones positivas de sector y día. No son 23–25 incendios independientes: un incendio puede abarcar varios sectores y varios días, y las detecciones repetidas comparten el mismo evento. Entrenamiento tuvo entre 18 y 29 filas positivas y validación entre 11 y 17. Por eso este experimento no permite afirmar una precisión generalizable ni elegir un adelanto para la app. El próximo paso científico sería validar contra perímetros/incidentes oficiales y evaluar separando incendios completos, no filas aleatorias de píxeles.

La generación del producto GOES-19 tuvo una demora mediana de 0,22 minutos desde el cierre de la escena; el percentil 95 fue 2,19 minutos. Esto mide generación del producto, no prueba el momento de su primera publicación pública. Veinte de las 2.952 horas esperadas no tuvieron escena y no se etiquetaron como ausencia de fuego.

Los artefactos ajustados y datos de observación están en la caché local ignorada por Git, bajo `training/data/environmental/private/`. Los 2.932 NetCDF originales suman 5,31 GB y no forman parte del APK. El protocolo, auditoría de fuente y reporte reproducible están en:

- `training/data/environmental/fire-goes19-2025q4-2026jan-protocol.json`
- [auditoría de fuente](fire-goes19-2025q4-2026jan-source-audit.json)
- [auditoría de disponibilidad](fire-goes19-2025q4-2026jan-availability-audit.json)
- [reporte de entrenamiento](fire-goes19-2025q4-2026jan-training-report.json)

El código deja el experimento fuera de inferencia de la app y registra `deployment_approved: false`.
