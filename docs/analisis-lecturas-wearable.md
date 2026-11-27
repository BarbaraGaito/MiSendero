# Análisis operativo de lecturas del reloj

El resumen del reloj ya no espera que las funciones experimentales de fatiga y riesgo devuelvan una predicción. Utiliza `assessWearableReadings` para generar una orientación por umbrales a partir de los sensores recibidos. En ajustes y mapa se muestran **Avisos de lectura** y **Carga por pulso**, sin la salida fija `sin_datos`.

## Comportamiento

- Pulso y SpO₂ válidos: considera ambos y declara ese alcance.
- Solo pulso válido: calcula la carga orientativa por pulso y sus avisos; no inventa una lectura de SpO₂.
- Solo SpO₂ válida: genera sus avisos y omite la carga por pulso.
- Ningún sensor válido o muestra antigua: espera una lectura reciente, sin inventar una clasificación ni mostrar ausencia de peligro.

Se conservan los cinco minutos de vigencia y la tolerancia de treinta segundos para el reloj del dispositivo. Se descartan valores no finitos y lecturas fuera de los rangos de aceptación que ya usaba la app: pulso 30–240 bpm y SpO₂ 50–100 %. Esos rangos de aceptación no describen normalidad clínica.

La velocidad y el tiempo de actividad solo se incorporan al resumen cuando son válidos. No condicionan la existencia del análisis de pulso/SpO₂ y no se usan para inventar etiquetas de fatiga.

## Reglas explícitas

| Lectura | Salida |
| --- | --- |
| Pulso menor de 145 bpm | Carga por pulso baja |
| Pulso entre 145 y menos de 165 bpm | Carga por pulso media |
| Pulso desde 165 bpm | Carga por pulso alta |
| Pulso desde 145 bpm o SpO₂ menor de 94 % | Aviso para revisar lectura |
| Pulso desde 180 bpm o SpO₂ menor de 90 % | Revisión prioritaria |

Son umbrales de orientación del producto basados en los avisos existentes. No se entrenó un modelo con esas reglas ni se generaron etiquetas para la tesis. Las categorías de carga no son una medición de fatiga, no están ajustadas por edad o condición física y no equivalen a intensidad individual validada. La activación de un aviso de SpO₂ que antes podía quedar solo como texto ahora también cambia el nivel del resumen, aunque el pulso no active un umbral.

La [FDA](https://www.fda.gov/consumers/consumer-updates/pulse-oximeter-basics) indica que la oximetría debe interpretarse junto con síntomas y contexto y puede tener limitaciones de precisión. El [CDC](https://www.cdc.gov/yellow-book/hcp/environmental-hazards-risks/high-altitude-travel-and-altitude-illness.html) describe cambios de saturación con la altitud y los límites de atribuir enfermedad de altura a una lectura aislada. Estas fuentes justifican la presentación contextual; no validan los umbrales concretos de la app. Una carga baja o un resumen sin umbrales activados no autorizan a continuar una caminata.

## Modelos y datos

Los modelos experimentales de Borg, AMS nocturno, OSM y APN conservan sus artefactos, métricas y limitaciones. No se modificó `deployment_approved`, no se habilitó un modelo incompatible ni se fabricó una probabilidad. El resultado operativo declara `method: sensor_rules` y no incluye porcentajes de confianza.

La incorporación del 27/11/2026 agrega un panel separado de controles personales. El modelo `fatigue-v1` estima Borg con pulso nativo de un minuto completo y hasta dos respuestas anteriores de la misma salida; no utiliza valores instantáneos del resumen ni la respuesta que acaba de guardarse. Los recordatorios opcionales aparecen al inicio y cada diez minutos. Si faltan muestras o el historial está fuera del rango aprendido, explica la abstención.

El modelo `ams-v1` corresponde a un control por la mañana, tras descansar durante la noche, en reposo y antes del próximo ascenso. Usa HR, SpO₂ y altitud absoluta, no desnivel acumulado. Se entrenó con visitas sucesivas de Boos 2018, separando equipos entre entrenamiento y prueba. La etiqueta procede de LLS y dolor de cabeza observados en la siguiente visita, nunca de los sensores de entrada ni de la columna publicada de AMS futuro que presentó discrepancias. Aunque mejora average precision y Brier, el umbral OOF clasificó positivos todos los casos del test; el servicio suprime esa clasificación y la interfaz muestra solo una puntuación orientativa con la limitación explícita. No se ajustó otro umbral mirando el test.

Ambos modelos son artefactos del prototipo académico, con `clinical_or_general_field_approved: false`. Los criterios técnicos de mejora se guardan como `runtime_eligible` y no equivalen a aprobación clínica o general de campo. Los JSON históricos conservan sus controles originales. Los controles y entradas se guardan únicamente por cuenta y consentimiento de salud, con borrado por revocación, baja de cuenta y retención de siete días. No hay conexión de estos resultados con SOS automático.

La sesión sigue guardando `avg_fatigue: null`: las reglas de aviso no se transforman en observaciones de fatiga para actividades, entrenamiento o tesis. Las mediciones y predicciones simuladas siguen identificadas como pruebas, en memoria, separadas del historial de dispositivos reales. Se conservan consentimiento, vigencia de lectura y aislamiento por cuenta.

## Verificación

Las pruebas cubren los límites de los umbrales, uso de cada sensor por separado, ausencia de valores inventados, lecturas caducadas/futuras y entradas inválidas. Las pantallas se verifican usando el análisis real del servicio, incluyendo el caso con SpO₂ y sin pulso. La inferencia de bosques sin validación conserva sus pruebas de abstención: ya no es una dependencia del resumen operativo del reloj.

La ejecución `npm run ai:field -- validate` reconstruye las dos nuevas tareas y su evidencia. Las pruebas móviles comparan las probabilidades exportadas contra Python en las 318 observaciones reservadas, con tolerancia absoluta de 1e-6, antes de aplicar las restricciones de entrega. Las pruebas de servicio usan SQLite real en memoria y dobles de la frontera nativa; no acreditan lectura física de un reloj, persistencia cifrada ni funcionamiento de HealthKit/Health Connect en un dispositivo. Esa comprobación requiere builds propias y hardware compatible.
