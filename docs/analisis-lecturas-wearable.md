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

La sesión sigue guardando `avg_fatigue: null`: las reglas de aviso no se transforman en observaciones de fatiga para actividades, entrenamiento o tesis. Las mediciones y predicciones simuladas siguen identificadas como pruebas, en memoria, separadas del historial de dispositivos reales. Se conservan consentimiento, vigencia de lectura y aislamiento por cuenta.

## Verificación

Las pruebas cubren los límites de los umbrales, uso de cada sensor por separado, ausencia de valores inventados, lecturas caducadas/futuras y entradas inválidas. Las pantallas se verifican usando el análisis real del servicio, incluyendo el caso con SpO₂ y sin pulso. La inferencia de bosques sin validación conserva sus pruebas de abstención: ya no es una dependencia del resumen operativo del reloj.
