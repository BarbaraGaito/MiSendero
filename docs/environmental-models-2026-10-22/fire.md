# Fuego: datos públicos, entrenamiento y resultado real

Se resolvió el acceso a observaciones diarias y se implementaron adquisición, control de calidad, preparación causal, entrenamiento, evaluación, auditoría e inferencia. **El modelo obtenido no es adecuado para alertas durante trekking y permanece inhabilitado.** Esta conclusión surge de los datos reservados, no de una falta de implementación.

## Fuente y variable objetivo

Se utilizó la colección pública [MODIS Thermal Anomalies/Fire Daily de Planetary Computer](https://planetarycomputer.microsoft.com/dataset/modis-14A1-061), filtrada exclusivamente a **MOD14A1.061, Terra**. El servicio permite obtener URLs temporales de lectura sin cuenta del usuario; esas URLs y sus tokens no se guardan ni se imprimen. Se conservaron los COG originales completos de FireMask y QA, sus URLs sin firma, fechas, bytes y SHA-256. No se mezclaron Aqua, Terra, VIIRS o fuentes con resoluciones diferentes.

MOD14A1 contiene capas **diarias** separadas dentro de un archivo que agrupa varios días. MOD14A2 es un resumen de ocho días y no se usó. Las clases y los bits QA siguen la [guía oficial del producto MODIS](https://landweb.modaps.eosdis.nasa.gov/data/userguide/MODIS_C6_Fire_User_Guide_C.pdf): se admite tierra firme con QA de tierra; positivo es máscara 8 o 9 (confianza nominal/alta) y negativo es máscara 5 (tierra observada sin detección). Nubes, agua, costa, baja confianza, desconocidos y faltantes se excluyen. No se infiere una clase negativa de la ausencia de una fila FIRMS.

El objetivo es **detección satelital nominal/alta durante las siguientes 24 horas en un píxel terrestre**, condicionado a una observación válida del objetivo. No es presencia física infalible de fuego, causa forestal, área quemada, propagación ni seguridad de evacuación. Puede haber quemas agrícolas o fuentes térmicas en los sectores observados; no se las reclasifica como incendio forestal.

## Cohorte argentina y trazabilidad

Se eligieron ocho ubicaciones ya documentadas en el catálogo: Macuco, Quebrada del Condorito, Mburucuyá, El Rey, Lihué Calel, Refugio Frey, Bosque Tallado/Piltriquitrón y Cerro Ventana. Las coordenadas, fuentes y hashes proceden del exportador existente. Se muestrean píxeles originales de la grilla sinusoidal, aproximadamente 927 m, dentro de los mismos sectores de 61 × 61 píxeles alrededor de esas ubicaciones. La grilla final toma un píxel cada tres posiciones; no se fabrican mediciones en coordenadas nuevas.

Se descargaron los [polígonos provinciales de Georef](https://www.argentina.gob.ar/georef/descarga-de-la-base-completa), cuya fuente declarada es IGN. Se rasterizan en la proyección nativa y se aplica un margen interior de un píxel antes de seleccionar muestras. Así se excluyen el exterior argentino y celdas próximas a fronteras. Los sectores cercanos a Chile, Brasil o Paraguay no agregan por proximidad muestras extranjeras. La precisión de ese recorte está limitada por la cartografía y la resolución del sensor.

La consulta 2024–2025 mostró huecos importantes. Antes de ajustar modelos se fijó el período más continuo 2022–2023. La primera grilla, cada seis posiciones, dejó dos positivos en validación: se archivó el intento sin entrenar candidatos. Se aumentó uniformemente la densidad a cada tres posiciones sobre **las mismas áreas**, sin cambiar fechas, zona reservada, mínimos o criterios de selección. No había métricas de modelos disponibles al hacer ese cambio. Se documenta esta inspección de conteos; no se presenta como un protocolo sin ninguna exploración de datos. No hubo muestreo preferencial por fuego, duplicación de positivos, SMOTE, ADASYN o generación sintética.

Se verificaron **440 pares FireMask/QA, 880 COG originales, 588.014.601 bytes**. La cohorte extraída tiene 2.204.981 registros píxel/día antes de deduplicar paquetes superpuestos. Se excluyeron 433.962 registros por calidad/clase no admitida. Los paquetes pueden superponerse en fechas: máscara y QA idénticas se cuentan una sola vez, con su disponibilidad más temprana; si difieren, se excluye ese píxel/día completo. La preparación registró 19.146 duplicados idénticos y dejó **1.756.393 negativos y 184 positivos únicos**. Esos conteos no representan incendios independientes: píxeles y días de un mismo evento pueden estar correlacionados.

La auditoría de adquisición está en `fire-source-audit.json`; el manifiesto por archivo y el CSV científico están en `training/data/environmental/private/`. Los originales están en `training/data/raw/environmental/fire-mod14a1/`. Se preserva el campo de licencia STAC tal como lo devuelve el proveedor (`proprietary`); no se sustituyó por una licencia inventada ni se redistribuyeron los COG en Git. Antes de redistribuir originales deben revisarse las condiciones de NASA y del proveedor; el acceso y la reproducción local no requieren credenciales del usuario.

## Disponibilidad y ejemplos causales

Cada emisión ocurre a las 00:00 UTC. El objetivo corresponde a la capa de ese día, hasta las 00:00 UTC siguientes: horizonte exacto de 24 h. Se verifica la lista de fechas reales del COG y su concordancia con QA; no se presupone que todo archivo tenga ocho bandas.

La disponibilidad de cada versión es el máximo de los timestamps STAC presentes, producción del original y Last-Modified de ambas bandas. Si el producto se revisó, sus valores no se utilizan antes de la disponibilidad conservadora de esa revisión. La demora mediana observada en los archivos es de aproximadamente **10,08 días**; algunas revisiones llegan mucho más tarde. No se sustituye esa disponibilidad por el día de adquisición ni se atribuyen capas finales de calidad científica al tiempo real.

Las entradas son cuatro observaciones válidas anteriores realmente disponibles, sus indicadores de detección y antigüedades, fracción histórica, extensión de la historia, coordenadas y estacionalidad anual. Si faltan cuatro registros o el último supera 45 días de antigüedad se abstiene. No se interpola una nube, no se imputa un faltante y no se utiliza la calidad futura como predictor. La demora del producto limita especialmente la utilidad de los antecedentes de fuego para anticipar nuevos eventos.

El procesamiento conserva la matriz numérica compacta en memoria y escribe la trazabilidad por filas en disco para no necesitar todos los metadatos como objetos simultáneos. Esa optimización no cambia las mediciones ni sus particiones.

## Entrenamiento y particiones

La tesela completa `h12v13`, que contiene los dos sectores patagónicos, se excluye de todo ajuste y selección. En el resto se entrena con objetivos y etiquetas disponibles antes del 01/01/2023; validación comprende enero–junio de 2023 y etiquetas disponibles antes del 01/07/2023. La prueba temporal corresponde a julio–diciembre de 2023; la geográfica reserva 2023 en la tesela excluida. Se purgan objetivos que cruzan los cortes.

| Partición | Ejemplos causales | Positivos |
|---|---:|---:|
| Entrenamiento | 495.190 | 106 |
| Validación | 332.695 | 12 |
| Prueba temporal | 341.975 | 31 |
| Prueba geográfica | 188.950 | 3 |

Se comparan prevalencia de entrenamiento, prevalencia mensual de entrenamiento, persistencia, logística, Random Forest y XGBoost. La logística estandariza solo con entrenamiento. RF usa 120 árboles, profundidad 8 y hoja mínima 10; XGBoost 150 árboles, profundidad 3 y tasa 0,05. Semilla 42, dos hilos. La ponderación de clases se calcula sobre entrenamiento, sin crear o replicar observaciones. Esa ponderación no garantiza calibración; se mide Brier y se reportan intervalos de confiabilidad por probabilidad.

El criterio fijado es la mayor **average precision de validación**, resumen de la curva precision–recall, no su integral trapezoidal. El umbral de clasificación permanece en 0,5. XGBoost fue seleccionado con validación (AP 0,0013253); no se reemplaza por otro candidato mirando el test.

## Resultados reservados y decisión

Fracciones, no porcentajes, salvo donde se indica expresamente. Resultados completos, matrices y calibración en `fire-results.json`.

| Candidato | AP temporal | Precision temporal | Recall temporal | Brier temporal |
|---|---:|---:|---:|---:|
| Prevalencia | 0,00009065 | 0 | 0 | 0,00009066 |
| Prevalencia mensual | 0,00022317 | 0 | 0 | 0,00009064 |
| Persistencia | 0,00009065 | 0 | 0 | 0,00015206 |
| Logística | 0,00007653 | 0 | 0 | 0,11106466 |
| Random Forest | 0,00158815 | 0,00677966 | 0,06451613 | 0,00905403 |
| **XGBoost seleccionado** | **0,00014849** | **0,00007763** | **0,03225806** | **0,02967577** |

En la prueba temporal, XGBoost tiene **1 verdadero positivo, 30 falsos negativos y 12.880 falsos positivos**. Su precision es aproximadamente 0,0078 % y su recall 3,23 %. No supera la referencia estacional en AP y sus probabilidades tienen Brier mucho peor que la prevalencia. Random Forest tiene mejor AP en esta prueba, pero detecta solo dos positivos y produce 293 falsos positivos; tampoco es evidencia de una alerta fiable y seleccionarlo después de ver estos resultados usaría indebidamente el test.

En la prueba geográfica, XGBoost omite los tres positivos. Su accuracy de 99,9984 % refleja la clase mayoritaria, no capacidad de detección. Tres positivos correlacionados no permiten una afirmación de precisión generalizable a Patagonia. La evaluación geográfica, los errores por mes y la calibración son parte del resultado negativo y no se ocultan.

**Decisión: `visualization_allowed:false` y `deployment_approved:false`.** La regla exige superar las tres referencias en AP en ambas pruebas, al menos cinco positivos geográficos y Brier no peor que prevalencia. No se cumplió; no se redujeron esos requisitos para habilitar el modelo. La incertidumbre por pocos eventos y el sesgo de cobertura impiden afirmar una precisión válida para todos los senderos argentinos.

## Inferencia e integración

Las observaciones de los 90 días recientes se adquieren por separado, con QA y hashes propios. No modifican el conjunto histórico ni sus particiones. `predict_fire.py` verifica el informe auditado y el modelo local, y prepara diagnósticos para la celda real que contiene cada centro del catálogo, con emisión, ventana de 24 h, observación y vencimiento. Si falta tierra válida o la historia está vencida, se abstiene. La probabilidad candidata queda exclusivamente en el archivo privado de investigación cuando el modelo está inhabilitado.

El exportador Node y el backend preservan exactamente píxel, probabilidad y geometría si en el futuro existiera un modelo habilitado y una asociación revisada con una ruta real. Los diagnósticos `not_approved` nunca se convierten en números para la app. Las pruebas cubren esa separación y la revocación/cambio de píxel. No se inventaron IDs de rutas ni se escribieron snapshots en una base remota. Los módulos de fatiga, AMS, mapas y SOS conservan su comportamiento.

## Reproducción

Usar `.venv-ai` con `training/python/requirements-environmental.txt` o el lock de esta carpeta; los COG requieren espacio local y los cachés evitan descargas repetidas.

```powershell
npm.cmd run fetch:environmental:fire
npm.cmd run train:environmental:fire
npm.cmd run validate:environmental:fire
npm.cmd run fetch:environmental:fire:recent
npm.cmd run predict:environmental
npm.cmd run test:environmental:fire
```

`validate:environmental:fire` reconstruye los joins desde las observaciones, comprueba hashes de originales y modelo, clases/fechas/particiones, selección por validación y métricas de las probabilidades de prueba. Requiere los originales y CSV privados; no certifica únicamente un JSON agregado. `fire-results-audit.json` conserva su salida.

No se afirma que el experimento resuelva la predicción preventiva de incendios. Para un nuevo experimento harían falta más eventos independientes y predictores disponibles con menor demora; cualquier reformulación requiere nuevas particiones reservadas y evaluación, sin reutilizar este test para seleccionar modelos. No se reetiquetan resultados malos para presentarlos como una función aprobada.
