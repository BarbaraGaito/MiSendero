# Siguiente comparación: datos manuales adicionales y regularización

El aprendizaje conjunto de la etapa 46 alcanzó 62,2253 % CV con CatBoost, por debajo del control global de 63,7972 %. Su [diagnóstico](two-history-joint-regularization-diagnostic.json) muestra que cinco de seis pares reducen la pérdida nativa de ajuste y empeoran la CV al pasar de 80 a 200 épocas. Eso justifica probar otra cantidad de regularización y una fuente real nueva, manteniendo 80 épocas. Este diseño aún no está implementado ni ajustado.

La nueva fuente de James Thomas y Johan Wahlström contiene [1.003 respuestas manuales verificadas](resistance-reported-rpe-verification.json), tomadas después de cada repetición en 69 series de cinco participantes. Se conservaron los valores originales 1–10 y su propia salida fuente. La fila original de conteos suma 1.001, pero las 1.003 celdas de respuesta coinciden una a una con los identificadores de repetición de la tabla publicada; las dos diferencias de conteo se documentan sin modificar ninguna respuesta.

El [adaptador independiente](resistance-history-input-verification.json) prepara 934 pares actuales/anteriores dentro de cada serie. La división por persona, fijada antes de exigir pares disponibles, reserva 68 pares de una persona y deja 866 pares de cuatro personas para ajuste. Junto con los 550 casos fuente anteriores hay **1.416 objetivos fuente de ajuste**, de los cuales **1.169** tienen dos antecedentes genuinos. Los 487/179 casos nativos originales se mantienen.

La comparación propuesta conserva las 40 bases nativas ya ajustadas y verificadas en la etapa 46; no hace falta volver a ajustar esas bases para cada receta. Se usarán las configuraciones positivas elegidas por la CV anterior: MLP con peso auxiliar 0,1 y CatBoost con peso auxiliar 1; ambas a 80 épocas.

| Eje | Valores |
| --- | --- |
| Base nativa | MLP o CatBoost, congelada durante backpropagation |
| Penalización de corrección | 0,1 / 1 / 10 |
| Peso de la nueva salida resistencia | 0 / 0,1 / 1 |
| Nuevas recetas | 18, más cuatro controles heredados |
| Folds de comparación | Los cinco grupos originales por persona; 90 ajustes nuevos de la red |

La salida nueva se agregará después de inicializar las tres salidas anteriores, para conservar sus inicializaciones. La imputación y escala de historia se ajustarán exclusivamente con los mismos casos permitidos anteriores —550 fuentes y el fold nativo de ajuste— y se aplicarán también a las historias nuevas. Así el control de peso nuevo cero y penalización 0,1 debe reproducir los pronósticos de su receta anterior. Las etiquetas nuevas quedarán fuera del objetivo cuando su peso sea cero.

Para peso nuevo positivo, la pérdida fuente será `(3 × promedio_anterior + peso_nuevo × pérdida_resistencia) / (3 + peso_nuevo)`, multiplicada por el peso auxiliar anterior correspondiente a cada base. Cada salida conservará sus objetivos continuos originales y pesos por persona. El contexto nativo, el encoder 16/8 y la corrección de 21 clases se mantienen, con tasa AdamW 0,003 y decay 0,1.

Las pruebas deberán comprobar las 866 etiquetas nuevas en el ajustador real, la exclusión de sus 68 casos reservados, los pesos y gradientes, la coincidencia de los controles, los faltantes naturales y las bases inmutables. Se usarán únicamente las anotaciones manuales del archivo original. Las tablas de EMG aprendido, los pesos suministrados y los procedimientos SMOTE/jitter de los experimentos del artículo quedan fuera de este diseño.

Las tres fuentes anteriores y resistencia mantendrán salidas distintas. No se inferirán tiempos de respuesta, edades, pausas o fases equivalentes a caminatas. Se elegirá por CV completa; el umbral previo de 0,65 para abrir otro test original permanece. El objetivo del 80 % exige un artefacto congelado y recargado con al menos **144/179 aciertos exactos**; el resultado retenido continúa en **108/179**.
