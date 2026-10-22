# Sugerencias de actualización de la tesis

Este archivo propone texto para revisión del autor. No modifica el PDF. Los resultados numéricos corresponden al informe del 22/10/2026; se deben mantener asociados a la fuente y al protocolo descritos en el README.

## Sección 4.5: arquitectura y funcionalidades

> MiSendero incorpora un módulo complementario de información ambiental con contratos versionados para cobertura nival, nivel hidrométrico y detecciones satelitales de fuego. El backend entrega snapshots precalculados, asociados a una geometría de ruta y a una versión de evidencia. La aplicación puede conservarlos en el paquete SQLite de mapas descargados, verificar su integridad y presentar su fecha de vencimiento aun sin conectividad. Las estimaciones experimentales se distinguen de las observaciones y de los avisos oficiales. Una falla del módulo no bloquea el registro de actividad, la navegación ni las funciones de emergencia.

> La implementación de nivel hidrométrico dispone de un pipeline real de adquisición, preparación, comparación de modelos y exportación de predicciones por estación. La vinculación numérica con senderos permanece inhabilitada hasta disponer de evidencia hidrológica del sector representado. Para nieve y fuego se implementaron los contratos, estados y puntos de integración; su entrenamiento permanece pendiente de adquirir observaciones que cumplan los requisitos de acceso y calidad. Estos módulos no constituyen predictores aprobados de transitabilidad ni de seguridad de un cruce.

Conservar el texto sobre los cuatro clasificadores previos y su estado de aprobación; esta ampliación no valida fatiga ni AMS para alertas durante trekking.

## Sección 4.8: evaluación y amenazas a la validez

> Se evaluó la predicción del nivel observado a tres y seis horas en tres series públicas del Instituto Nacional del Agua, con 68.769 mediciones originales. Se compararon persistencia, regresión lineal, Random Forest y XGBoost con particiones cronológicas por estación. Los objetivos que cruzaban los cortes temporales fueron excluidos; se exigió disponibilidad de predictores anterior a la emisión y de etiquetas de entrenamiento/validación anterior al corte respectivo. La selección se realizó sobre validación, reservando julio–diciembre de 2025 para prueba.

> En la serie Uruguay–Concepción del Uruguay, Random Forest obtuvo MAE de 0,03385 m a tres horas y 0,05433 m a seis horas, frente a 0,05305 m y 0,07927 m de persistencia. En Puerto Iguazú, el modelo seleccionado no mejoró la referencia; en Los Moscos se seleccionó persistencia. Por lo tanto, la evidencia de mejora se limita a una estación y dos horizontes en el período reservado. No se evaluó transferencia a otros cursos de agua ni seguridad de cruce. Se auditaron 17.276 predicciones de prueba contra las observaciones originales.

> La actualización final de cada registro se utilizó como aproximación conservadora de su disponibilidad; no se dispone del historial completo de publicación y revisiones. Las mediciones no se certifican como datos históricos consolidados y pueden contener errores de sensor. Los resultados retrospectivos no sustituyen una evaluación prospectiva o de crecidas extremas. El MAE expresa error medio histórico y no una garantía de error máximo.

> El entrenamiento nival se detuvo por falta de acceso autenticado a los archivos científicos MOD10A1. En fuego, no se construyeron etiquetas negativas a partir de la ausencia de detecciones FIRMS: falta evidencia diaria de cobertura válida. Estos impedimentos se documentaron y no se generaron muestras sintéticas para completar los experimentos. La evaluación de software de la infraestructura ambiental se realizó con fixtures separados de la evidencia científica.

Evitar expresiones como «tres nuevos modelos entrenados», «detección validada de incendios», «precisión de seguridad» o «sendero seguro». Para regresión informar MAE/RMSE y la unidad, no convertir el error en un porcentaje de accuracy. Los conteos de pruebas de software no son métricas del desempeño del modelo.
