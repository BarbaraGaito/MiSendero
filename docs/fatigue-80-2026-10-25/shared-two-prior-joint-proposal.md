# Siguiente comparación: aprendizaje conjunto con antecedentes reales

La transferencia mediante funciones fuente congeladas todavía no supera el control global de 63,7972 % CV. La siguiente hipótesis es aprender una representación compartida de las respuestas anteriores mediante backpropagation, conservando una salida distinta para cada estudio y una corrección nativa separada. Este documento describe un ensayo pendiente de implementación; no anuncia una mejora obtenida.

La entrada pública propuesta es `public-two-prior-histories-80-v2`, [verificada contra las celdas originales](public-two-prior-history-v2-verification.json). Conserva 607 pares actuales: 550 para ajuste y 57 EMAP reservados por persona. De los 550 de ajuste, 367 tienen dos antecedentes genuinos. Las 202 segundas respuestas Worker y las 203 EMAP disponibles en el conjunto completo están comprobadas; 202 segundas respuestas no disponibles permanecen ausentes. La versión de cadenas anterior omitía dos celdas reales y queda [reemplazada](public-two-prior-history-chain-review.json). Ninguna de estas dos versiones entró en ajuste de modelos hasta esta preparación.

El ensayo mantendrá los 487/179 casos nativos originales y sus cinco folds por persona. Las dos entradas compartidas serán Borg previa y segunda Borg previa reales, con su faltante natural. La rama nativa podrá usar el contexto compacto de 13 entradas ya existente. Las edades de las respuestas fuente, sus fases equivalentes a caminata y sus sensores no están disponibles y no se inferirán.

| Componente | Comparación propuesta |
| --- | --- |
| Base nativa | MLP 16/8, L2=10, hasta 5.000 iteraciones; o CatBoost 900 árboles, profundidad 3, L2=30 |
| Logits de ajuste de la base | Tres folds internos por persona, exclusivamente dentro del fold nativo de ajuste |
| Encoder compartido | Dos antecedentes medidos, imputación/indicador de ausencia y escalado solo con datos permitidos de ajuste; capas 16/8 tanh |
| Salidas fuente | Tres regresores separados: EMAP, Worker, STS; cambio continuo original respecto de la respuesta anterior |
| Corrección nativa | Capa de 16 neuronas y 21 logits de cambio, inicializada en cero; predicción Borg exacta 0–10 |
| Optimización | AdamW, tasa 0,003, decay 0,1; pérdida nativa más promedio de pérdidas fuente ponderadas por persona y penalización de corrección |
| Hiperparámetros principales | Peso auxiliar 0/0,1/1 y 80/200 épocas fijas, para cada base nativa |
| Plan acotado | 12 variantes nuevas más cuatro controles heredados; 60 ajustes externos nuevos |

El peso auxiliar cero es el control pareado que conserva la misma arquitectura y preparación, con las etiquetas fuente fuera del objetivo de entrenamiento. Se conservará también el control nativo original sin corrección. Un piso de probabilidad de 0,0001 permitirá evaluar clases de cambio ausentes en algún ajuste interno, comprobando que la inicialización en cero conserve las decisiones de la base.

Cada época usará únicamente las respuestas medidas originales. Los objetivos fraccionarios fuente permanecerán continuos, separados de las etiquetas nativas. Las pruebas deberán observar filas y objetivos en el ajustador real, los límites de personas, las estadísticas de preparación, los gradientes, los pesos base congelados y la recarga sin etiquetas actuales ni identificadores de consulta.

Se elegirá solo mediante CV completa por personas. El umbral previo de 0,65 CV para abrir un nuevo test original se mantiene. El resultado retenido sigue siendo **108/179 = 60,3352 %**; el objetivo del 80 % exige **144/179**, todavía pendiente.
