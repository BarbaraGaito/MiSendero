# Revisión de WHAMAP para MiSendero

Fecha: 22 de octubre de 2026. Dataset: WHAMAP, versión 1, DOI [10.17632/8zt9g9g64c.1](https://doi.org/10.17632/8zt9g9g64c.1), Silva, Silva y Oliveira. Licencia de la ficha original: CC BY 4.0.

## Resultado

WHAMAP es un candidato público para experimentos sobre movimiento durante caminatas y subidas. **No es un reemplazo directo del modelo de fatiga de MiSendero con pulso y SpO₂.** El protocolo y las columnas revisados requieren otra entrada y otra evaluación. La documentación revisada tampoco establece que las caminatas se hayan realizado durante excursiones de montaña.

La fuente declara mediciones de diez participantes, cinco IMU en los miembros inferiores y sensores del teléfono. El README describe dos bloques, actividades previas de sentadillas y caminatas a velocidades fijadas. No se debe presentar esta colección como trekking prolongado ni como validación de fatiga en montaña.

## Evidencia consultada

- [Ficha y descarga originales](https://data.mendeley.com/datasets/8zt9g9g64c/1).
- [README original descargable](https://data.mendeley.com/public-files/datasets/8zt9g9g64c/files/0e64f0fa-079c-454d-bfe6-d4906f4d339f/file_downloaded). Se conserva una copia íntegra en [source-readme.md](source-readme.md), atribuida a los autores y reutilizada bajo CC BY 4.0.
- [Metadatos seleccionados de la ficha original](source-metadata.json).
- [Manifiesto de las seis descargas y SHA-256](download-manifest.json). Los seis archivos coincidieron con los tamaños y SHA-256 publicados por Mendeley.
- [Auditoría de los cuatro CSV de movimiento](sample-audit.json).

La revisión comprende el README, la tabla de participantes y cuatro trazas completas: `subject_01/walking.csv`, `subject_01/uphill.csv`, `subject_10/walking_B.csv` y `subject_10/uphill_B.csv`. No es una auditoría de todos los participantes o archivos, ni una evaluación de un modelo. Los CSV de gran tamaño se descargaron temporalmente para el análisis; el manifiesto permite recuperar los originales.

## Compatibilidad

| Aspecto | WHAMAP revisado | MiSendero actual |
| --- | --- | --- |
| Entradas principales | Aceleración, giroscopio y orientación de cinco sensores de piernas; aceleración, giroscopio y magnetómetro del teléfono | Pulso, SpO₂, pasos, energía activa y velocidad |
| Frecuencia de movimiento | Aproximadamente 50 Hz en las cuatro trazas | El contrato actual de métricas del reloj no transporta estas series IMU |
| Etiqueta | `f-level`, niveles 0–4 atribuidos a Borg | El resumen operativo usa avisos por lecturas; el modelo experimental Borg conserva otra tarea |
| Actividad | Caminata y subida en protocolo; el README indica velocidades fijas | Caminatas de duración y terreno variables |

La comparación de la app se basa en [WearableMetricSample](../../types/index.ts) y [el puente nativo](../../services/nativeWearableBridge.ts). Que el teléfono tenga acelerómetro no demuestra que un modelo con sensores de piernas funcione con ese teléfono: una investigación con las columnas del teléfono tendría que entrenarse y evaluarse exclusivamente con esas entradas.

## Etiquetas y límites metodológicos

El README identifica `f-level` como una anotación basada en Borg, pero no aporta la variante exacta de la escala, la tabla de conversión a 0–4, los valores originales ni el criterio completo para asignar las etiquetas a las caminatas. No se puede tratar `f-level` como una puntuación Borg original, convertirla automáticamente a bajo/medio/alto o afirmar que su correspondencia con fatiga fisiológica está demostrada.

En las cuatro trazas inspeccionadas la etiqueta es constante dentro de cada archivo. Esto no prueba que la etiqueta sea incorrecta ni sintética. Sí significa que sus miles de filas no son miles de evaluaciones independientes de fatiga. Una futura evaluación debería separar participantes y mantener juntas las ventanas de una misma grabación; usar ID de persona, reloj o número de bloque como predictores puede introducir atajos asociados al protocolo.

El README menciona videos del procedimiento, pero no revisamos esos videos. No confirmamos pendiente, superficie, ubicación exterior ni colocación del teléfono. La ficha consultada no enlaza una publicación asociada; esta revisión no acredita una validación externa del modelo final.

## Calidad técnica de la muestra

| Traza | Filas | Duración aproximada | `f-level` almacenado |
| --- | ---: | ---: | ---: |
| subject_01 / walking.csv | 18.167 | 363,32 s | 1 |
| subject_01 / uphill.csv | 17.882 | 357,62 s | 1 |
| subject_10 / walking_B.csv | 14.857 | 297,12 s | 2 |
| subject_10 / uphill_B.csv | 15.537 | 310,72 s | 3 |

Las 66.443 filas revisadas tienen 78 columnas consistentes, valores de sensores numéricos y finitos, tiempos crecientes e intervalo mediano de 20 ms. No se encontraron celdas vacías en estas cuatro trazas. Esto verifica formato y consistencia de esa muestra; no certifica precisión de los sensores, cobertura del resto del dataset o validez de las etiquetas.

La tabla `User_data.csv` contiene diez filas de datos con siete campos, pero el encabezado se separa en once campos al leerlo como CSV estándar. No se corrigió la fuente ni se usó esa tabla para entrenar.

## Decisión para la tesis

**Conservar como candidato para investigación de movimiento durante caminatas y subidas. No incorporarlo todavía como predictor fiable de fatiga durante trekking en MiSendero.** Para ese uso faltan la definición reproducible de la etiqueta, compatibilidad de sensores y una evaluación con personas separadas. Esta revisión no creó datos sintéticos, no entrenó modelos, no cambió indicadores de aprobación y no modificó la aplicación.
