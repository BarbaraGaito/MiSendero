# Entrenamiento exploratorio por horizonte

Se ajustó regresión logística con ponderación de clases para predecir una detección de fuego en el mismo píxel dentro de 1, 2, 3, 6 o 12 horas. Las entradas son ubicación, hora/fecha y las detecciones válidas previas del píxel. Las observaciones de enero se usaron para entrenar, febrero para elegir el umbral y marzo como prueba temporal. Las etiquetas objetivo y los predictores provienen de GOES; este experimento no mide incendios físicos que el satélite no haya visto.

La muestra de prueba de marzo tiene solo 9 detecciones positivas para los horizontes de 1 a 6 horas y 6 para 12 horas. Corresponden a muy pocos días y sectores, por lo que las métricas son inestables y no permiten estimar precisión poblacional.

| Adelanto | AP del modelo en prueba | AP de persistencia | Precisión del modelo con umbral 0,5 | Recall del modelo con umbral 0,5 | Positivos en prueba |
|---:|---:|---:|---:|---:|---:|
| 1 h | 0,0748 | 0,2222 | 0,060 % | 33,3 % | 9 |
| 2 h | 0,0139 | 0,0556 | 0,051 % | 11,1 % | 9 |
| 3 h | 0,000016 | 0,000013 | 0 % | 0 % | 9 |
| 6 h | 0,000027 | 0,000014 | 0 % | 0 % | 9 |
| 12 h | 0,000026 | 0,0185 | 0 % | 0 % | 6 |

AP es el área bajo la curva precisión-recall. La regla de persistencia pregunta si el mismo píxel ya tenía una detección reciente. En 1 y 2 horas superó al modelo en prueba. Con umbral 0,5, el modelo emitió demasiadas alertas falsas en los horizontes cortos y no detectó positivos en los horizontes de 3 horas o más. Las probabilidades de la regresión no están calibradas; el 0,5 no significa una posibilidad real del 50 %. Aunque el umbral de validación alcanzó precisión aparente de 0,80 para algunos horizontes, no produjo detecciones en la prueba de marzo.

**No hay un horizonte predictivo aprobado.** El resultado respalda continuar evaluando detecciones observadas recientemente y persistencia, no afirmar que el modelo predice incendios con horas de anticipación. Se excluyó 30 minutos porque el muestreo elegido es horario y no permite medirlo. El entrenamiento guardó modelos solo en la caché privada local; no se generaron artefactos de app ni se activó inferencia.

El registro reproducible está en [fire-goes16-2025-q1-training-report.json](fire-goes16-2025-q1-training-report.json); la cobertura y demora de fuente están en [fire-goes16-2025-q1.md](fire-goes16-2025-q1.md). Los modelos binarios están en `training/data/environmental/private/fire-goes16-2025-q1-models/`, ignorados por Git.
