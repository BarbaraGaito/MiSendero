# UCD: ventanas cortas y control de diferencias de grabación

Fecha: 22 de octubre de 2026. Fuente: [señales originales de UCD en Zenodo](https://zenodo.org/records/11114096), licencia CC BY 4.0. Esta evaluación continúa [la prueba con zancadas procesadas](ucd-running.md). No activa inferencia en MiSendero.

## Resultado y decisión

El clasificador de aceleración obtuvo **66,49 % de acierto** en ventanas cortas y **62,94 %** al repetir la prueba con ventanas con movimiento suficiente y personas con ambas condiciones. Sin embargo, un control que **solo recibe cantidad de muestras e intervalo de muestreo**, sin aceleración, obtuvo **80,41 %**. La forma de registrar/exportar la señal está fuertemente asociada con la etiqueta del protocolo. El 80,41 % no representa detección fisiológica de fatiga, aunque se hayan separado personas.

El resultado de aceleración tampoco demuestra transferencia a trekking. Los datos son de carrera en pista exterior, sensor lumbar, sin pulso, con etiquetas de condición antes/después de un beep test. No hay referencia continua del momento de aparición de fatiga. El resultado moderado, los registros con poco movimiento y el desempeño del control de muestreo impiden presentar esta fuente como validación suficiente de alertas en un reloj/celular durante trekking.

## Integridad, tiempo y cobertura

Se descargaron las **38 grabaciones `F`/`NF` de 19 personas**, 294.465.611 bytes y 1.312.530 filas de mediciones. Se verificaron tamaño y MD5 contra los metadatos oficiales; el [informe reproducible](ucd-windows-results.json) conserva además SHA-256 por archivo. Los originales y la copia de metadatos quedan en `training/data/raw/ucd-running/raw/`, excluidos de Git. No se usaron los archivos `BeepTest`, porque no proporcionan una referencia temporal verificada de fatiga durante la transición.

Aunque la descripción del depósito declara 256 Hz, los intervalos exportados corresponden aproximadamente a **150,31 Hz en 6 archivos, 256 Hz en 28 y 51,2 Hz en 4**, interpretando `Timestamp` como milisegundos. El [controlador oficial de Shimmer](https://github.com/ShimmerResearch/Shimmer-Java-Android-API/blob/13614c6cb1bd30070260617b3adb376e4fb8b0c4/ShimmerDriver/src/main/java/com/shimmerresearch/driver/ShimmerObject.java#L2870) convierte el timestamp calibrado a milisegundos y declara esa unidad. Los CSV depositados omiten las cabeceras de unidades: la interpretación temporal sigue condicionada a que sean exportaciones calibradas. No se fuerza artificialmente la frecuencia declarada ni se confunden 1.280 muestras con cinco segundos en todos los archivos.

También hay diferencias de precisión de exportación. Por ejemplo, `004_F.csv` empieza con `1718405.304`, `1718411.957`, `1718418.61`, mientras `004_NF.csv` empieza con `159021.3928`, `159028.0457`, `159034.6985`. El control de muestreo comprueba una asociación instrumental con la condición; no identifica por sí solo qué proporción de su acierto procede de redondeo, pérdidas de paquetes u otra diferencia del registro.

Se construyen ventanas consecutivas **sin superposición de 5.000 unidades de `Timestamp`**, aproximadamente cinco segundos bajo la interpretación anterior. Solo se usan mediciones contenidas antes del final de cada ventana; no hay voto de la grabación completa, interpolación ni remuestreo. Se exige tiempo estrictamente creciente, valores finitos, al menos 50 muestras y ningún hueco interno o de borde mayor de 50 unidades. De 1.188 ventanas completas candidatas se aceptaron **1.164 (97,98 %)** y se excluyeron 24. Los fragmentos finales incompletos no se puntúan; su longitud consta por archivo en el informe. Se observaron 43 intervalos entre mediciones mayores de 50 unidades, algunos dentro de la misma ventana o fuera de las ventanas completas.

De las 1.164 ventanas aceptadas, **233** tienen desviación de magnitud de aceleración menor de 1: 184 `NF` y 49 `F`. Ese umbral se fijó como comprobación técnica de sensibilidad antes de observar los resultados del clasificador. No es una escala de fatiga ni un detector validado de carrera. Tras retirarlas quedan 931 ventanas; la persona `016` no conserva ninguna ventana `NF` por encima del umbral. Para comparar ambas condiciones en cada persona se excluyen también sus 27 ventanas `F` restantes, dejando **904 ventanas de 18 personas**. Esa pérdida de cobertura se informa y no se reemplaza con observaciones inventadas.

Los identificadores de los depósitos bruto y procesado tampoco coinciden exactamente: los procesados incluyen `010` y omiten `016`; los brutos incluyen `016` y omiten `010`. Comparten 18 identificadores. Por tanto, los dos porcentajes no constituyen una comparación pareada exacta sobre las mismas grabaciones ni una validación externa independiente.

## Método fijado antes de leer los resultados

Se usa Random Forest con 150 árboles, profundidad máxima 5, mínimo 10 ventanas por hoja, pesos equilibrados por clase y semilla 42. Las siete características son media, desviación, mediana, percentiles 10 y 90, RMS y rango de la magnitud de aceleración de rango amplio (`Accel_WR_X/Y/Z`). Se omite la primera diferencia de la prueba anterior porque depende directamente del intervalo de muestreo. No entran ID, nombre de archivo, respuesta, tiempo desde el inicio ni muestreo como características de este modelo.

En cada ronda se reserva una **persona completa**, con todas sus ventanas de ambas condiciones. La referencia constante predice la clase más frecuente de las otras personas, evaluada sobre exactamente las mismas ventanas. El control instrumental usa el mismo modelo fijo, pero recibe exclusivamente número de muestras e intervalo mediano dentro de cada ventana. No se buscaron hiperparámetros ni se eligió una versión por su resultado de prueba. La comparación con movimiento suficiente se definió antes de leer las métricas; su cohorte elegible se determinó por cobertura de señal, no por aciertos.

## Métricas observadas

| Prueba | Personas | Ventanas | Acierto | Referencia constante | Precisión/PPV de `F` | Sensibilidad de `F` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Aceleración, todas las ventanas aceptadas | 19 | 1.164 | 66,49 % | 55,50 % | 63,28 % | 58,88 % |
| Control: solo número de muestras e intervalo | 19 | 1.164 | 80,41 % | 55,50 % | 92,40 % | 61,00 % |
| Aceleración, sensibilidad a poco movimiento | 18 | 904 | 62,94 % | 51,11 % | 63,08 % | 58,37 % |

En la última prueba, la matriz de confusión, filas reales `NF`/`F` y columnas predichas `NF`/`F`, es `[[311, 151], [184, 258]]`. Se omitieron **184 de 442 ventanas `F` (41,63 %)** y hubo 151 falsos positivos entre 462 ventanas `NF`. Las ventanas de una misma carrera comparten condición; no son 904 evaluaciones independientes de fatiga ni 904 personas.

Los intervalos percentiles exploratorios del 95 % remuestrean personas completas 10.000 veces, manteniendo juntas sus predicciones de prueba. Para las 904 ventanas, el intervalo de acierto es **56,09–70,46 %**, el de PPV **55,81–72,38 %** y el de sensibilidad **41,72–75,64 %**. El promedio de exactitud equilibrada por persona es **64,83 %**, intervalo **58,23–71,53 %**. No se deben mezclar este promedio por persona y el acierto agrupado de la tabla. Los intervalos no incluyen toda la incertidumbre de entrenamiento, elección de fuente o transferencia a un sendero.

## Afirmación defendible

“En una evaluación exploratoria de carrera exterior con sensor lumbar y personas reservadas completas, un clasificador de aceleración obtuvo 62,94 % de acierto sobre 904 ventanas con movimiento suficiente de 18 participantes al distinguir condiciones antes y después de un protocolo de agotamiento. Un control basado únicamente en muestreo logró 80,41 % sobre las 1.164 ventanas de calidad de los 19 participantes, evidenciando una asociación entre registro y condición. Estos resultados no validan detección de fatiga durante trekking.”

Los controles usan conjuntos de evaluación distintos cuando se informa la sensibilidad a poco movimiento; el 80,41 % debe compararse directamente con el 66,49 % de las mismas 1.164 ventanas. El detector de aceleración no recibe las características del control, por lo que su resultado no queda explicado automáticamente por ese control; sí quedan demostrados factores de confusión importantes en la fuente.

No se integró un modelo nuevo ni se aprobó su despliegue. Tampoco se publicaron cambios. Reproducción: `python training/python/evaluate_ucd_windows.py`, con NumPy, pandas y scikit-learn; `--audit-only` genera una auditoría separada en `ucd-windows-audit.json`. [Script](../../training/python/evaluate_ucd_windows.py), [predicciones, exclusiones, versiones e intervalos](ucd-windows-results.json).
