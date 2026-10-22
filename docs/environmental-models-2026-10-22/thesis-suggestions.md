# Sugerencias de actualización de la tesis

Este archivo propone texto para revisión del autor. No modifica el PDF. Los resultados numéricos corresponden al informe del 22/10/2026; se deben mantener asociados a la fuente y al protocolo descritos en el README.

## Sección 4.5: arquitectura y funcionalidades

> MiSendero incorpora un módulo complementario de información ambiental con contratos versionados para cobertura nival, nivel hidrométrico y detecciones satelitales de fuego. El backend entrega snapshots precalculados, asociados a una geometría de ruta y a una versión de evidencia. La aplicación puede conservarlos en el paquete SQLite de mapas descargados, verificar su integridad y presentar su fecha de vencimiento aun sin conectividad. Las estimaciones experimentales se distinguen de las observaciones y de los avisos oficiales. Una falla del módulo no bloquea el registro de actividad, la navegación ni las funciones de emergencia.

> La implementación de nivel hidrométrico dispone de un pipeline real de adquisición, preparación, comparación de modelos y exportación de predicciones por estación. La vinculación numérica con senderos permanece inhabilitada hasta disponer de evidencia hidrológica del sector representado. Para fuego se adquirieron capas diarias MOD14A1 y QA públicas y se implementó un pipeline separado de evaluación e inferencia. Nieve permanece pendiente de acceso autenticado. Estos módulos no constituyen predictores aprobados de transitabilidad ni de seguridad de un cruce.

Conservar el texto sobre los cuatro clasificadores previos y su estado de aprobación; esta ampliación no valida fatiga ni AMS para alertas durante trekking.

## Sección 4.8: evaluación y amenazas a la validez

> La evaluación hidrométrica conservada comprende dos series públicas del Instituto Nacional del Agua, con 37.533 mediciones originales. Se compararon persistencia, regresión lineal, Random Forest y XGBoost con particiones cronológicas por estación. Los objetivos que cruzaban los cortes temporales fueron excluidos; se exigió disponibilidad de predictores anterior a la emisión y de etiquetas de entrenamiento/validación anterior al corte respectivo. La selección se realizó sobre validación, reservando julio–diciembre de 2025 para prueba.

> En Puerto Iguazú, el modelo seleccionado no mejoró la referencia; en Los Moscos se seleccionó persistencia. Por lo tanto, no se afirma mejora del ML hidrométrico sobre persistencia en el alcance conservado. No se evaluó transferencia a otros cursos de agua ni seguridad de cruce. Se auditaron 8.963 predicciones de prueba contra las observaciones originales.

> La actualización final de cada registro se utilizó como aproximación conservadora de su disponibilidad; no se dispone del historial completo de publicación y revisiones. Las mediciones no se certifican como datos históricos consolidados y pueden contener errores de sensor. Los resultados retrospectivos no sustituyen una evaluación prospectiva o de crecidas extremas. El MAE expresa error medio histórico y no una garantía de error máximo.

> El entrenamiento nival se detuvo por falta de acceso autenticado a los archivos científicos MOD10A1. Para fuego, el acceso a MOD14A1 mediante Planetary Computer permitió construir etiquetas a partir de máscaras diarias y calidad, separando tierra observada sin fuego de nubes, agua, baja confianza y faltantes. La cobertura se recortó con límites IGN/Georef de Argentina. No se generaron muestras sintéticas. Los resultados de detección, calibración y prueba geográfica deben citarse desde el informe de fuego, sin convertir la accuracy mayoritaria en garantía de seguridad. La evaluación de software se realizó con fixtures separados de la evidencia científica.

> El experimento de fuego utilizó 2022 para entrenamiento y dos períodos reservados de 2023, además de una tesela patagónica excluida del ajuste y la selección. XGBoost fue seleccionado con validación; en la prueba temporal detectó uno de 31 positivos y produjo 12.880 falsos positivos, con precision aproximada de 0,0078 % y recall de 3,23 %. Omitió los tres positivos de la prueba geográfica. Estos resultados y la mala calibración impiden usarlo como alerta durante trekking. Se conserva como experimento reproducible con resultado negativo, no como una mejora de seguridad demostrada.

Evitar expresiones como «tres nuevos modelos entrenados», «detección validada de incendios», «precisión de seguridad» o «sendero seguro». Para regresión informar MAE/RMSE y la unidad, no convertir el error en un porcentaje de accuracy. Los conteos de pruebas de software no son métricas del desempeño del modelo.
