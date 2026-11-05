# UCD: evaluación de condiciones antes/después de agotamiento durante carrera exterior

Fecha: 22 de octubre de 2026. [Datos procesados originales](https://zenodo.org/records/7997851), [señales brutas complementarias](https://zenodo.org/records/11114096). Autores: Bahavathy Kathirgamanathan, Brian Caulfield y Pádraig Cunningham; University College Dublin. Licencia declarada en Zenodo: CC BY 4.0.

## Qué mide esta prueba

Diecinueve corredores realizaron 400 m a ritmo cómodo, un beep test progresivo hasta no poder mantener el ritmo y otros 400 m a ritmo cómodo. El dispositivo Shimmer3 estaba fijado en la región lumbar; los metadatos declaran una frecuencia de 256 Hz. La [auditoría posterior de señales brutas](ucd-windows.md) halló intervalos compatibles con aproximadamente 51,2, 150,31 y 256 Hz, por lo que esa frecuencia declarada no debe imponerse a todos los archivos. Se conservaron las etiquetas originales `NF` (carrera anterior al protocolo) y `F` (carrera posterior); no se generaron etiquetas a partir del pulso ni se usaron opiniones de usuarios de MiSendero.

La referencia es la **condición del protocolo**. No es una medición continua e independiente de toda la fatiga fisiológica. La fase posterior puede diferir en velocidad, orden u otros factores además de fatiga. Tampoco hay etiquetas verificadas que indiquen el instante de aparición de fatiga durante el beep test. Estos límites deben acompañar cualquier cifra.

## Integridad y método

Se descargó `Accel_mag_all.csv` (9.767.363 bytes), verificando el MD5 oficial `054b2be68060e0e4543a431fe49c4f14`. El archivo **no tiene cabecera**: contiene 6.006 filas de zancadas, cada una con ID de participante, condición original y 180 muestras de magnitud de aceleración. No se descarta la primera fila como cabecera ni se contabilizan las muestras internas como observaciones independientes. El SHA-256 y los recuentos están en [el informe](ucd-running-results.json). El CSV bruto queda en `training/data/raw/ucd-running/`, excluido de Git por la regla existente.

Se fijó un Random Forest de 150 árboles, profundidad máxima 5, mínimo 10 muestras por hoja, pesos equilibrados y semilla 42. Sus ocho características son estadísticas de magnitud de aceleración: media, desviación, mediana, percentiles 10 y 90, RMS, rango y RMS de la primera diferencia. No recibe ID, fase del protocolo, tiempo transcurrido ni respuesta subjetiva. Se hicieron 19 rondas dejando fuera **una persona completa**, con todas sus zancadas de ambas condiciones. La referencia predice la condición más frecuente de las otras personas. No se seleccionaron parámetros por el resultado de prueba.

## Resultados

| Métrica | Modelo | Referencia constante |
| --- | ---: | ---: |
| Acierto por zancada | 63,00 % | 51,28 % |
| Exactitud equilibrada por clase, todas las zancadas | 63,13 % | 50,00 % |
| Precisión/valor predictivo positivo de condición `F` | 65,76 % | 51,28 % |
| Sensibilidad para condición `F` | 58,12 % | 100,00 % |

El promedio de exactitud equilibrada de las 19 personas fue **62,74 %**. Su intervalo percentil exploratorio del 95 % al remuestrear personas completas fue **55,86–69,83 %**. Describe la variación de las predicciones ya calculadas entre personas; no incluye toda la incertidumbre por entrenamiento, selección de fuente o cambio de entorno.

Las zancadas comparten una condición dentro de cada carrera. Al decidir por mayoría de zancadas para cada una de las **38 grabaciones**, se acertaron **25/38 (65,79 %)**: 14 de las 19 carreras `NF` y 11 de las 19 `F`. Hubo **5 falsos positivos y 8 falsos negativos**. Por grabación, la precisión de `F` fue 68,75 % y la sensibilidad 57,89 %. La agregación utiliza la carrera completa; no es una medida de latencia ni de acierto de una alerta en tiempo real.

## Afirmación permitida y límites para la app

“En un conjunto público de carrera exterior de 19 personas, un clasificador de aceleración lumbar distinguió las condiciones anteriores y posteriores a un protocolo de agotamiento con un promedio por participante de 62,74 % de exactitud equilibrada (intervalo exploratorio 55,86–69,83 %), dejando fuera personas completas.”

Esto es evidencia exploratoria de diferencias de movimiento asociadas al protocolo; **no demuestra detección de fatiga durante trekking**. No se ha comprobado transferencia de correr a caminar, de pista a sendero, de Shimmer3 a celular/reloj ni de sensor lumbar a bolsillo/muñeca. La segmentación en zancadas procede del dataset y también tendría que implementarse y evaluarse para uso continuo. La omisión de 8 de 19 grabaciones posteriores al agotamiento impide presentar este modelo como una base fiable para recomendaciones de seguridad. No se integró en la app ni se cambió ninguna aprobación de despliegue.

Reproducción: `python training/python/evaluate_ucd_running.py`, con numpy, pandas y scikit-learn. El script verifica el archivo original, conserva las etiquetas y produce los resultados por persona y grabación.
