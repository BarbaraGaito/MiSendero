# Detección de caídas — IA experimental (MiSendero)

Fecha: 2026-10-22. Estado global: **experimental**. El modelo está **entrenado, evaluado en laboratorio sobre datos públicos e integrado en la app para inferencia local**. La **captura continua con pantalla bloqueada NO está validada** y no se promete (ver sección 13).

Se distinguen siempre cuatro niveles de evidencia:

| Nivel | Estado |
|---|---|
| Modelo entrenado | Sí (XGBoost, 300 árboles, UniMiB SHAR, 30 participantes) |
| Modelo evaluado | Sí, por participante (leave-one-participant-out), sobre caídas experimentales, no sobre accidentes reales |
| Inferencia integrada | Sí: pipeline TypeScript puro, equivalente al de Python (pruebas con registros reales) y ejecutado en Jest. **No ejecutado en un teléfono** en este entorno |
| Monitoreo continuo validado | **No.** Sin pruebas en dispositivo, sin medición de batería, sin servicio en primer plano |

## 1. Objetivo y beneficio para la seguridad

Detectar localmente, mediante el acelerómetro del teléfono y sin Internet, un movimiento compatible con una caída durante un recorrido, y preguntar al usuario si necesita ayuda. El beneficio potencial es acortar el tiempo hasta que el propio usuario pida ayuda si está en condiciones de responder. **No** reemplaza un plan de emergencia, **no** llama ni envía SMS por sí mismo y **no** interpreta la falta de respuesta como inconsciencia.

## 2. Datasets y procedencia

* **Principal: UniMiB SHAR** (Micucci, Mobilio, Napoletano, *Applied Sciences* 7(10):1101, 2017). Descargado de la página oficial (enlace Dropbox publicado por los autores). SHA-256 del ZIP: `365a396729c0755b4ba8ef8ee0ba52a0621aa535282470546d8a663ff2567160` (266 206 080 bytes). Se usan los registros continuos (`full_data.mat`), no las ventanas pre-recortadas. Licencia: la página no declara una; los autores piden citar el artículo. Por eso solo se conservan en el repositorio pequeños extractos (`testing/fixtures/fall-detection/parity.json`) para pruebas de equivalencia, y los datos crudos están fuera de git (`training/data/raw/`). **Verificar los términos antes de redistribuir públicamente.**
* **Complementario: MobiAct — no incorporado.** Se entrega solo por solicitud a bmi@hmu.gr con un acuerdo de uso (investigación/educación no comercial). No se obtuvo acceso autorizado, por lo que no se usó. (Condiciones leídas en la página oficial el 2026-10-22; la conexión HTTPS directa desde este equipo falló, por lo que no se intentó descargar nada.)
* Procedencia detallada: `training/data/public/fall_detection/provenance.json`.

## 3. Cantidad real de participantes y registros

* 30 participantes (18–60 años; 24 mujeres y 6 varones), teléfono Android en el **bolsillo del pantalón** (derecho/izquierdo), 50 Hz exactos, m/s² con gravedad.
* 1 980 ensayos originales: 540 AVD (9 actividades × 2 ensayos × 30) y 1 440 caídas (8 tipos × 6 ensayos × 30). 90,4 min de caídas y 156,9 min de AVD registrados.
* **1 ensayo excluido** por muestras NaN (participante 9, Jumping, 2.º ensayo). Nada se imputó.
* **Hallazgos de auditoría que condicionan el diseño:**
  1. Los 240 ensayos de cambios de postura (sentarse, pararse, acostarse) son 5 repeticiones concatenadas con saltos de ~4 s: se dividieron en 960 segmentos contiguos para que ninguna ventana cruce un empalme.
  2. Las caídas están recortadas: mediana 1,4 s después del impacto. Una ventana de 3 s centrada en el pico solo es posible en el 43 % de las caídas.
  3. Los ensayos de caída duran 3–9 s; los de caminar/correr ~30 s. El dataset no contiene horas de uso continuo.

## 4. Preprocesamiento

* Conversión a g (÷ 9,80665), gravedad incluida. `expo-sensors` ya entrega g en Android e iOS.
* **Regla determinística de candidatos (no es decisión del modelo):** una muestra es candidata si su magnitud supera 1,5 g y es el primer máximo dentro de ±0,4 s. Con 1,5 g el 99,93 % de los segmentos de caída tienen candidato (tabla de umbrales en `metrics.json`: 1,25 g → 99,93 %; 1,75 g → 99,79 %; 2,0 g → 99,58 %; 2,5 g → 80,4 %). Se eligió 1,5 g por ese techo de sensibilidad y porque coincide con el criterio del dataset.
* **Ventana:** 61 muestras = 0,8 s antes + pico + 0,4 s después. Elegida por **cobertura de datos, no por rendimiento**: retiene 99,3 % de los impactos de caída y 84,8 % de los picos de cambios de postura (con 1,5 s + 0,6 s retendría solo 29 % de estos últimos). La decisión se toma 0,4 s después del impacto.
* Candidatos sin ventana real completa no se clasifican (no se rellena ni se replica el borde): 10 impactos de caída y 264 candidatos AVD.
* En la app: remuestreo lineal a 50 Hz exactos desde timestamps del sensor; saltos > 100 ms descartan el búfer; separaciones > 45 ms marcan la muestra como dudosa y las ventanas que la contienen se omiten.

## 5. Características y algoritmos

37 características **invariantes a la orientación** (solo magnitud y ángulo entre vectores de gravedad medios), porque la orientación del teléfono es desconocida y las convenciones de ejes difieren entre Android e iOS: estadísticos por tramo (pre-lejano, pre-cercano, impacto, post), energía, caída libre, jerk, conteo de picos, **cambio de orientación** (ángulo entre gravedad previa y posterior), quietud posterior.

Comparados: (1) baseline convencional por umbrales (pico ≥ UFT, mínimo previo ≤ LFT, desvío posterior ≤ PST; 528 combinaciones elegidas por validación), (2) Random Forest (300 árboles, `min_samples_leaf=2`, pesos de clase), (3) XGBoost (300 árboles, profundidad 4, `lr=0,05`, `scale_pos_weight`), (4) CNN 1D liviana (ver sección 8). Hiperparámetros fijados a priori, **sin ajuste sobre los folds de evaluación**.

## 6. Entrenamiento

`training/python/fall_detection/` (`py -m fall_detection.run_loso`). Sin datos sintéticos, sin SMOTE/ADASYN ni aumentación: el desbalance se trata solo con pesos de clase. Positivos: impacto principal de cada segmento de caída (1 429). Negativos: todo candidato de AVD (6 009). Los picos secundarios dentro de segmentos de caída (878) se excluyen de las métricas por candidato por tener etiqueta ambigua; sí pueden activar la alarma a nivel evento.

## 7. Evaluación por participante

Leave-one-participant-out (30 folds). **El umbral de decisión se elige solo con los 29 participantes de entrenamiento** (GroupKFold interno de 5, objetivo F2). La corrida es reproducible: dos ejecuciones dan métricas idénticas.

### Resultados por candidato (30 participantes, 7 438 candidatos; IC 95 % por remuestreo de participantes)

| Modelo | Precisión | Recall caídas | Especificidad | F1 caída | F1 macro | PR-AUC |
|---|---|---|---|---|---|---|
| Baseline por umbrales | 0,431 [0,39–0,48] | 0,942 [0,92–0,96] | 0,704 [0,66–0,75] | 0,591 | 0,705 | 0,417 |
| Random Forest | 0,960 [0,94–0,98] | 0,989 [0,98–0,995] | 0,990 [0,98–0,996] | 0,974 | 0,984 | 0,990 |
| **XGBoost (elegido)** | **0,963 [0,94–0,98]** | **0,992 [0,986–0,997]** | **0,991 [0,986–0,996]** | **0,978** | **0,986** | **0,993** |
| CNN 1D | 0,937 [0,91–0,96] | 0,987 [0,978–0,994] | 0,984 [0,977–0,991] | 0,961 | 0,976 | 0,996 |

Matriz de confusión (filas real; columnas predicho no-caída/caída): baseline [[4231, 1778], [83, 1346]]; RF [[5950, 59], [16, 1413]]; **XGBoost [[5955, 54], [11, 1418]]**. Diferencias RF–XGBoost dentro del intervalo de confianza: **la elección de XGBoost se debe a menor tamaño y mejor PR-AUC/F2, no a una superioridad demostrada**.

Por participante (XGBoost): recall medio 0,992 (mínimo 0,917); especificidad media 0,991 (mínima 0,948). Por bolsillo: derecho recall 0,992 / especificidad 0,992; izquierdo 0,993 / 0,990.

### Falsos positivos por actividad (XGBoost, por candidato AVD)

Sentarse **9,2 %**, acostarse 5,8 %, saltar 2,1 %, correr 0,6 %, caminar 0,1 %, subir/bajar escaleras ≤ 0,5 %, pararse desde sentado/acostado 0 %. Los **cambios bruscos de postura y los saltos son la fuente principal de falsas alarmas**; el baseline falla mucho más (correr 49,7 %, saltar 67 %).

### Nivel evento (segmentos completos)

XGBoost detecta 1 431 de 1 440 segmentos de caída (99,4 %; 99,5 % de los evaluables) y emite alarmas en 41 de 1 499 segmentos AVD (54 candidatos) sobre 156,9 min de AVD guionados. **Esto NO es una tasa de falsas alarmas por hora de uso real y no debe extrapolarse**: el dataset no tiene horas continuas de caminata ni de otras situaciones de montaña, por lo que esa tasa no puede calcularse. La app no declara ninguna.

### Controles de cordura (`sanity_checks.json`)

* Etiquetas permutadas: PR-AUC 0,191 (≈ prevalencia 0,193): no hay fuga de información.
* Ablaciones (GroupKFold 6, RF): sin cambio de orientación 0,977; sin contexto previo 0,961; sin post-impacto 0,972; sin magnitud de pico 0,994; sin caída libre 0,991. Solo la magnitud del pico: **0,548**, por lo que el resultado no es un simple umbral de impacto. El rendimiento es redundante entre grupos de características.

### Ventanas continuas y sin compuerta (limitación real)

Entrenado sobre ventanas alineadas al impacto, el clasificador es **muy sensible a la alineación**: con el impacto desplazado dentro de la ventana, el recall de XGBoost cae a 99,2 % (0), 97,7 % (−10 muestras), 51,7 % (−20), 29,8 % (−30), 94,1 % (+10) y 60,9 % (+20). Aplicado sobre ventanas deslizantes sin compuerta, marca 0,0–2,9 % de las ventanas AVD según la actividad, pero casi todas las marcadas contienen picos > 1,5 g. Por eso la app usa candidatos alineados al pico y no una ventana fija deslizante.

## 8. Comparación con la CNN 1D

Implementada en `fall_detection/cnn_eval.py`: 2 canales invariantes a la orientación (magnitud y coseno respecto de la gravedad previa al impacto), 3 convoluciones con pooling global, 5 905 parámetros, 40 épocas, Adam, pérdida con peso de clase (sin remuestreo). Mismo protocolo anidado leave-one-participant-out y **los mismos 7 438 candidatos** que los modelos de árboles. Resultados en `training/data/public/fall_detection/metrics_cnn.json` (84 min en CPU).

| | CNN 1D | XGBoost |
|---|---|---|
| Matriz [[VN, FP], [FN, VP]] | [[5914, 95], [19, 1410]] | [[5955, 54], [11, 1418]] |
| F1 caída [IC 95 %] | 0,961 [0,946–0,976] | 0,978 [0,966–0,988] |
| PR-AUC | **0,996** | 0,993 |
| FP al sentarse / acostarse / saltar | 9,8 % / **12,9 %** / 3,5 % | 9,2 % / 5,8 % / 2,1 % |
| Recall por participante (media; mínimo) | 0,987; 0,917 | 0,992; 0,917 |
| Especificidad por participante (media; mínimo) | 0,985; 0,922 | 0,991; 0,948 |

La CNN ordena los candidatos levemente mejor (PR-AUC 0,996), pero en el punto de operación elegido sin ver al participante evaluado produce **más falsas alarmas (95 contra 54)**, sobre todo al acostarse, y algo menos de recall. Los intervalos de F1 se solapan apenas, así que **no es claramente mejor**. Además exigiría implementar convoluciones en TypeScript y validar su equivalencia. **Decisión: no se despliega; XGBoost queda como modelo de la app.**

## 9. Exportación del modelo

Formato elegido: **JSON de árboles evaluado en TypeScript puro** (`services/fallDetection/fallModel.json`, 142 KB, 300 árboles, 5 786 nodos). Se prefirió a ONNX porque (a) no añade módulo nativo (`onnxruntime-react-native` obliga a build nativo y no pude compilar aquí), (b) es verificable en Jest y (c) sigue la convención ya usada por los otros modelos de la app. Versionado: `id`, `version` (`2026.10.22-exp1`), `status: experimental`, `deployment_approved: false` (el cargador rechaza cualquier otro valor), `threshold` 0,27 (de predicciones fuera de pliegue de 10 grupos sobre los 30 participantes), procedencia y resumen de evaluación en el mismo archivo. El contrato de señal (`modelContract.json`) se genera desde Python.

Equivalencia verificada con **42 ventanas y 11 segmentos reales** de UniMiB SHAR: características con error relativo < 1e-9; probabilidades dentro de 1e-5 de XGBoost; mismas decisiones; el detector en streaming encuentra los mismos candidatos, picos y probabilidades que Python y decide a pico + 0,4 s.

## 10. Arquitectura de inferencia offline

`Acelerómetro → remuestreo 50 Hz → búfer circular (128 muestras) → regla de candidatos (1,5 g) → ventana de 61 → 37 características → XGBoost local → umbral → enfriamiento 30 s → pantalla de asistencia`.

* Modelo, características y reglas se ejecutan en el teléfono. No hay llamadas a la API: `modelContract.json` y `fallModel.json` van en el bundle.
* **Decisiones del modelo:** solo la probabilidad y el umbral 0,27. **Reglas determinísticas:** compuerta 1,5 g, remuestreo, calidad de señal, enfriamiento de 30 s (no ajustado, solo evita repeticiones), una sola solicitud de asistencia pendiente.
* **Estrategias de reducción de falsas alarmas evaluadas:** enfriamiento y control de señal incompleta (implementados). Confirmación entre ventanas consecutivas y análisis del movimiento posterior **no se implementaron como reglas automáticas**: los registros solo conservan ≤ 0,4–1,4 s tras el impacto y no hay datos para validarlas sin ajustar a ciegas. La confirmación la hace el usuario (“Estoy bien”).
* Latencia medida en Node de escritorio: **0,47 ms por ventana** (características + modelo). No medida en teléfono. Memoria: búferes ~4 KB; modelo en arrays tipados ~81 KB más el JSON de 142 KB.
* Errores: modelo inválido → monitoreo “no disponible”; fallo del clasificador → candidato omitido sin alarma; muestras no finitas o desordenadas → ignoradas y contadas.

## 11. Integración con los sensores

* `expo-sensors` (`Accelerometer`, intervalo 20 ms). Plugin con texto de uso de movimiento para iOS (`NSMotionUsageDescription`); Android no requiere permiso en tiempo de ejecución para este sensor (la app lo consulta igualmente).
* **Activación explícita:** interruptor “Detección de caídas — IA experimental” en *Antes de salir* (`TrailStart`), con aviso de limitaciones y confirmación. Está apagada por defecto, es por cuenta y solo corre **mientras haya un recorrido en curso** y el interruptor esté activado (`FallDetectionCoordinator`).
* Estado real, derivado de las muestras que llegan: `monitoring`, `interrupted` (sin datos > 2 s, con causa “segundo plano” si corresponde), `degraded_rate` (< 40 Hz medidos), `unavailable` (sin sensor, sin permiso, modelo inválido). Se muestra en la tarjeta y en una línea del recorrido activo, con tiempo monitoreado/interrumpido en el estado interno.
* No se guardan datos crudos: solo el búfer circular de ~2,5 s en memoria, liberado al detener el monitoreo.

### Posición del teléfono

El modelo se entrenó **solo con teléfono en el bolsillo del pantalón** (derecho e izquierdo; mismo rendimiento en ambos). **No hay datos ni pruebas** para mochila, mano, pecho ni cinturón; no debe asumirse que funcionen. La app lo indica antes de activar.

## 12. Funcionamiento sin Internet

Todo el flujo (sensor, modelo, asistencia, registro local) funciona sin red; verificado en Jest sin ninguna llamada de red en el camino de detección. El SOS reutiliza el existente, que ya funciona offline con SMS/llamada si hay cobertura celular.

## 13. Restricciones de Android e iOS (pantalla bloqueada)

**Estado: no implementado ni validado.** No se simuló.

* **Android:** desde Android 9 las apps en segundo plano no reciben eventos de sensores de reporte continuo; con pantalla apagada la CPU puede dormirse. Mantener la captura requiere un **servicio en primer plano con notificación** (con tipo declarado en Android 14+) y un *wake lock* parcial, con impacto en batería y revisión de políticas de Google Play. No lo implementé porque en este entorno **no hay Android SDK ni dispositivo**: código nativo sin compilar ni probar podría romper el APK actual y daría una falsa sensación de protección. Queda como trabajo pendiente (módulo Expo local + config plugin, `FOREGROUND_SERVICE` y tipo `specialUse`/`health`, ver protocolo en `device-test-protocol.md`).
* **iOS:** Core Motion no entrega acelerómetro a una app suspendida. `UIBackgroundModes` solo incluye `fetch`; mantenerla viva requeriría un modo de fondo (p. ej. ubicación continua) con implicancias de privacidad y de revisión de App Store que no se justifican aquí.
* **Qué hace hoy la app:** al pasar a segundo plano, si el sistema deja de entregar muestras, el estado pasa a *interrumpido* en ≤ 2 s tras volver a la app (los temporizadores también se pausan), con el texto “sin protección”. El tiempo interrumpido queda contabilizado. **Escenarios compatibles:** app abierta, pantalla encendida. **No compatibles/no verificados:** pantalla bloqueada, app en segundo plano, ahorro de batería agresivo.
* No hay notificaciones locales (no hay `expo-notifications` en el proyecto y, sin captura en segundo plano, no tendrían sentido). Con la app abierta se usa vibración (patrón 3 × 0,5 s) y la pantalla de asistencia. No hay señal sonora.

## 14. Consumo energético

**No medido.** No hay dispositivo en este entorno. Procedimiento propuesto en `device-test-protocol.md` (comparar descarga con y sin monitoreo durante 30–60 min con `adb shell dumpsys batterystats`). Dato indirecto: el sensor se pide a 50 Hz y el modelo solo se ejecuta ante candidatos (> 1,5 g), unos 0,5 ms en un Node de escritorio.

## 15. Integración con el SOS existente

* “Solicitar ayuda” abre `/confirmar-sos` con `origen=caida`, **sin** `sendSms` ni envío automático. La pantalla existente recupera la última ubicación disponible con su fecha y hora (en el mensaje), ofrece el contacto, SMS y llamada, y el botón de volver al recorrido (mapa offline). Se agregó: banner “Abierto desde la detección de caídas (IA experimental)… MiSendero no envió ni llamó a nadie”, y una tarjeta **Conexión** que distingue Internet (medible) de cobertura celular (**no medible por la app**, y lo dice).
* La app no afirma envíos que no puede verificar (comportamiento previo conservado).
* La detección sigue funcionando localmente aunque no exista ningún canal para contactar a terceros.
* “Estoy bien” descarta y registra la confirmación. Cerrar sin responder se registra como **sin respuesta**, nunca como “bien” ni como inconsciencia.

## 16. Persistencia local, privacidad y pruebas

* Tabla SQLite `fall_detection_events`: fecha/hora, actividad (sendero e inicio), versión del modelo, clasificación (`possible_fall`), puntaje, pico en g, respuesta, acción y —solo si el usuario pidió ayuda— la última ubicación **real** (nunca simulada) del seguimiento existente, sin pedir un GPS nuevo. Tabla `fall_detection_settings` por cuenta.
* **No se sincroniza ni entra en `pending_operations`** (verificado en pruebas). Se borra con la eliminación de cuenta (`eraseLocalAccountData`) y por retención a **90 días**. Los eventos pendientes tras un reinicio pasan a “sin respuesta”.
* **Pruebas ejecutadas (todas pasan):** Jest completo 563 pruebas / 68 suites (incluye 6 suites nuevas con 42 pruebas más 1 en la suite del SOS: equivalencia Python/TS, detector en streaming con registros reales, jitter de timestamps, saltos del sensor, 20 Hz, enfriamiento, monitor con estados e interrupciones, persistencia/privacidad/borrado, coordinador, tarjeta de activación, pantalla de asistencia incluyendo “Estoy bien”, acceso al SOS sin envío); `tsc --noEmit` limpio; Python `unittest` 12 pruebas (integridad del dataset, independencia de participantes, métricas consistentes con las predicciones guardadas, modelo exportado idéntico a XGBoost, invarianza a la orientación); reproducibilidad bit a bit de las métricas.
* **Pruebas NO ejecutadas y motivo:** captura real del acelerómetro, inferencia en el dispositivo, comportamiento con pantalla bloqueada y en segundo plano, interrupciones reales del sistema, consumo energético, vibración real, SOS en un teléfono con SIM: requieren un dispositivo físico/compilación nativa que no existe en este entorno. No se hicieron caídas físicas.

## 17. Limitaciones para un despliegue de seguridad real

1. Caídas **experimentales** de 30 voluntarios (24 mujeres, 6 varones; 18–60 años) en laboratorio; no hay accidentes de montaña, terreno irregular, mochila, bastones, trepadas, resbalones parciales ni caídas con el teléfono fuera del bolsillo.
2. Solo **bolsillo del pantalón**, un modelo de teléfono Android en el dataset; sensores y frecuencias de otros dispositivos no validados.
3. Los negativos son AVD guionadas cortas: faltan situaciones difíciles de montaña (saltos de rocas, descensos con impactos, golpes a la mochila, el teléfono cayéndose) y no existen horas de uso continuo, así que **no se puede estimar falsas alarmas por hora**. La precisión de ~0,96 vale para la mezcla del dataset, no para el uso real, donde los negativos serán muchísimo más frecuentes.
4. 15 % de los picos de cambios de postura (los negativos más difíciles) no tienen ventana completa y quedaron fuera; las falsas alarmas reales podrían ser mayores. Sentarse (9 %) y acostarse (6 %) ya son las mayores fuentes.
5. El modelo es sensible a la alineación impacto-ventana (sección 7).
6. Sin captura con pantalla bloqueada: la protección depende de tener la app abierta.
7. Umbral de calidad de señal (45 ms) y detección de interrupciones calibrados por criterio de ingeniería, no con hardware.
8. Hay un único modelo evaluado en un único dataset; sin validación externa.

Conclusión: **no existe evidencia suficiente para un uso de seguridad real**; la función se presenta como experimental y así debe seguir hasta contar con pruebas en dispositivos, datos de montaña y medición de energía.

## Archivos

Entrenamiento y evaluación: `training/python/fall_detection/` (`dataset.py`, `features.py`, `candidates.py`, `run_loso.py`, `cnn_eval.py`, `sanity_checks.py`, `export_contract.py`, `export_model.py`), `training/python/test_fall_detection.py`, `training/data/public/fall_detection/{metrics,metrics_cnn,sanity_checks,provenance}.json`.
App: `services/fallDetection/` (`features.ts`, `detector.ts`, `model.ts`, `monitor.ts`, `fallEvents.ts`, `FallDetectionCoordinator.tsx`, `modelContract.json`, `fallModel.json`), `mobile/components/{FallDetectionCard,SosConnectivityNotice}.tsx`, `mobile/screens/FallAssistanceScreen.tsx`, `app/caida-detectada.tsx`, cambios mínimos en `app/_layout.tsx`, `TrailStart.tsx`, `RouteMap.tsx`, `ConfirmSosScreen.tsx`, `accountLifecycle.ts`, `app.json`, `package.json`.

Comandos: `npm run train:fall-detection` (≈ 15 min); la CNN es opcional y aparte: `cd training/python && py -m fall_detection.cnn_eval` (≈ 1,5 h en CPU, requiere `torch`), `npm run test:fall-detection`.
