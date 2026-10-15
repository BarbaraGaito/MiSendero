# Revisión de MiSendero frente a «PFI - Entrega 50»

Fecha: 9 de septiembre de 2026. Revisión del código local, requisitos y artefactos de entrenamiento. No se modificó la implementación de la aplicación.

**Conclusión.** Hay una base funcional considerable: autenticación, persistencia SQLite, rutas, descarga de mapas, puntos GPS, reportes, cola de sincronización y modelos RandomForest con inferencia local. La prioridad es cerrar los recorridos completos offline y corregir afirmaciones de seguridad que hoy no están respaldadas por el comportamiento del sistema. Agregar más pantallas o modelos antes de resolver esto aumentaría el alcance sin resolver los problemas principales.

**Alcance y evidencia.** Se extrajo el texto de las 84 páginas del PDF y se revisaron especialmente alcance, requisitos, casos de uso, mockups, arquitectura y validación. En este informe se usa la numeración impresa: páginas 6–7 para alcance; 28–30 para RF; 33–36 para aceptación; Figura 3.2, página 37, para la propuesta visual; 54–55 para RNF; 64–65 para validación. El visor cuenta dos páginas más. El documento se trató como fuente de requisitos, no como instrucciones para ejecutar acciones.

El navegador integrado falló dos veces al inicializar: `failed to write kernel assets ... os error 3`. No se obtuvieron capturas de la aplicación en ejecución. Las propuestas de UX/UI siguientes se basan en código y en los mockups proporcionados en el PDF; no constituyen una auditoría visual terminada ni una certificación de accesibilidad.

Validación ejecutada: TypeScript sin errores; frontend 8 suites y 35 tests aprobados; backend 7 suites y 31 tests aprobados. Se ejecutaron además diagnósticos locales sin red ni sensores sobre los modelos, el planificador de mapas y los colores. Los tests actuales prueban componentes, pero no demuestran la entrega de SOS, la operación con pantalla bloqueada ni un recorrido completo en modo avión.

Evidencia: [resultados](D:/AppPFI/MiSendero/docs/revision-pfi-evidencia/diagnostics.json). El script de diagnóstico se eliminó el 15/10/2026 junto con los modelos que evaluaba; queda en el historial de Git.

## 1. Faltantes frente al documento

«Parcial» significa que hay código, pero falta parte del requisito o su conexión con el flujo principal. No se asigna un porcentaje global de avance: contar pantallas ocultaría las diferencias de importancia entre requisitos.

| Requisito | Estado | Qué falta cerrar |
|---|---|---|
| RF-01: explorar rutas | Parcial | Hay búsqueda por nombre/zona, dificultad, distancia y favoritas. Completar filtros por duración y disponibilidad descargada; ofrecer catálogo local cuando no responde la API. |
| RF-02: información previa | Parcial | Distancia, duración y dificultad existen. El desnivel se calcula con una fórmula visual; falta perfil de elevación con datos geográficos y un acceso coherente a los reportes vigentes. |
| RF-03: descargar mapas, ruta y elevación | Parcial | Hay descarga y verificación de tiles/ruta/reportes. Faltan elevaciones reales, garantía de cobertura del recorrido y proveedor habilitado para descarga offline. |
| RF-04: administrar descargas | Base implementada | Hay estados, reintentos y borrado. Verificar actualizaciones, tiles compartidos entre rutas y que «completo» equivalga a cobertura útil. |
| RF-05: iniciar, pausar, reanudar, finalizar | Parcial | Persistir una sesión activa única, restaurar acumulados y separar tiempo activo de tiempo total. Evitar que navegar entre pantallas cambie la identidad de la sesión. |
| RF-06: GPS sobre mapa local | Parcial | El mapa principal tiene fallback local y puntos GPS persistidos. Falta cerrar los accesos offline y verificar seguimiento con pantalla bloqueada. |
| RF-07: desvíos | Parcial | Existe umbral de distancia al trazado. Corregir distancia en pantalla de alerta, preservar sesión y agregar señal sonora/vibración según CU-03. |
| RF-08: crear reportes georreferenciados | Parcial | Formulario, validación y backend presentes. El formulario busca la geometría solo en red; sin ella no puede validar una nueva ubicación offline. |
| RF-09: consultar reportes vigentes | Parcial | Existen consulta, copia offline y limpieza de reportes antiguos. Mostrar ubicación, antigüedad y vigencia de forma consistente, también tras sincronizar. |
| RF-10: conservar reportes pendientes | Base implementada | La cola persiste el reporte si llega a enviarse desde el formulario. Resolver primero RF-08 para que el flujo offline pueda llegar a ese punto. |
| RF-11: sincronizar al recuperar conexión | Parcial, prioridad alta | `runSync()` existe, pero no hay coordinador global de reconexión. Añadir aislamiento por cuenta, recuperación de operaciones interrumpidas y política específica de SOS. |
| RF-12: emergencia | Parcial, prioridad máxima | Hay mensaje, última ubicación y persistencia; falta transporte hacia el contacto. «Enviado» hoy significa que la API guardó un registro. |
| RF-13: contactos | Parcial | Se guarda un contacto local por usuario. Resolver textos contradictorios sobre edición offline; definir si el alcance exige varios contactos y cuál es el orden de respaldo. |
| RF-14: cuenta y sesión | Base implementada con brechas | Registro/login/JWT y almacenamiento seguro del token en nativo. Aislar todo el estado local por usuario y resolver expiración sin bloquear funciones offline esenciales. |
| RF-15: experiencia y preferencias | Parcial | Hay cuestionario y preferencias guardadas. El recomendador toma la primera coincidencia de dificultad; ahorro de batería, unidades y notificaciones no están conectados a todos los consumidores. |
| RF-16: clima | Parcial | Hay Open-Meteo y estimación de respaldo. Distinguir pronóstico, dato almacenado y estimación; preservar hora de consulta y evitar presentar estimaciones como condiciones verificadas. |
| RF-17: dificultad y recomendaciones IA | Parcial | Existe modelo y script manual de aplicación al backend. Falta trazabilidad por ruta y ranking que use condición/preferencias, no solo la primera dificultad compatible. |
| RF-18: métricas offline | Parcial | Se persisten puntos y distancia. Resolver recuperación, pausas, filtrado de mala precisión GPS y tiempo activo. |
| RF-19: wearable con consentimiento | Base preparada, según alcance | Hay HealthKit/Health Connect y simulación. Validar frescura y alineación temporal; la integración completa de dispositivos puede quedar para evolución posterior según pp. 6 y 65. |
| RF-20: alertas, resumen y privacidad | Parcial | Hay inferencia y recomendaciones visibles. Faltan abstención con datos insuficientes, registro de eventos en el resumen y consentimiento estrictamente ligado a cada cuenta. |

Los RNF se traducen en tareas concretas: RNF-01, cerrar el flujo offline; RNF-02, aislar datos y consentimientos; RNF-03, eliminar confirmaciones falsas y hacer accesibles las acciones críticas; RNF-04, medir latencia en dispositivo; RNF-05, recuperar sesiones/colas tras interrupción; RNF-06, implementar y medir ahorro de batería; RNF-07, errores recuperables y timeouts; RNF-08, unificar servicios compartidos; RNF-09, URL completa configurable con HTTPS para entorno remoto; RNF-10, textos simples, estados inequívocos y menos decisiones durante la actividad.

## 2. Hallazgos prioritarios y cambios propuestos

**P0 — SOS afirma una notificación que no ocurrió.** [ConfirmSosScreen.tsx](D:/AppPFI/MiSendero/mobile/screens/ConfirmSosScreen.tsx:91) muestra «Se notifico a…». [emergencyAlerts.ts](D:/AppPFI/MiSendero/services/emergencyAlerts.ts:105) devuelve `sent` cuando `createEmergencyAlert()` responde. El [backend](D:/AppPFI/MiSendero/backend/src/routes/emergencyAlerts.routes.js:37) solo inserta una fila con estado predeterminado `sent`. No hay proveedor de SMS, llamada o push a ese destinatario. El test de emergencia verifica persistencia, no entrega. Cambiar el estado a «Registrado en el servidor; entrega no confirmada» y completar un canal real. Excluir rescate automático del alcance del PDF no equivale a excluir el mensaje al contacto de RF-12/13.

**P0 — La ruta descargada no alimenta todos los pasos offline.** [TrailDetail](D:/AppPFI/MiSendero/mobile/screens/TrailDetail.tsx:33), [TrailStart](D:/AppPFI/MiSendero/mobile/screens/TrailStart.tsx:149), [AlertRouteScreen](D:/AppPFI/MiSendero/mobile/screens/AlertRouteScreen.tsx:36), [ReportTerrainScreen](D:/AppPFI/MiSendero/mobile/screens/ReportTerrainScreen.tsx:85) y [RestBreakScreen](D:/AppPFI/MiSendero/mobile/screens/RestBreakScreen.tsx:57) dependen de `getTrailById()`. `RouteMap` sí tiene fallback local. Crear un repositorio común que entregue primero la ruta descargada, permita actualización remota con timeout y conserve los datos útiles si falla la red. Aceptación: descargar, activar modo avión, abrir detalle, iniciar, reportar, atender desvío, pausar y finalizar sin bloqueo por API.

**P0 — Relieve y referencias dibujadas sin respaldo geográfico.** [Terrain3DScene.tsx](D:/AppPFI/MiSendero/mobile/components/Terrain3DScene.tsx:109) estima desnivel a partir de distancia y dificultad. [TrailMap.tsx](D:/AppPFI/MiSendero/mobile/components/TrailMap.tsx:230) dibuja curvas, arroyo y senderos secundarios desplazando la ruta. No son observaciones del lugar. El detalle muestra ese desnivel sin aclarar su origen. Retirar estas capas de navegación operativa; reservarlas para una demostración inequívocamente identificada. Incorporar elevación real con procedencia/resolución y graficar distancia versus altitud. El dato ausente debe quedar como «Sin datos de elevación».

**P1 — Sincronización sin disparador global y con riesgos de integridad.** Las llamadas a `runSync()` están principalmente en Perfil y `syncSessions()`. Falta un coordinador al iniciar la app, recuperar red y volver al primer plano. `pending_operations` no guarda propietario y el envío usa el token del usuario conectado en ese momento: una operación de A podría enviarse bajo B después de cambiar de cuenta. Tampoco se recuperan filas que quedaron en `syncing` tras una interrupción; no hay exclusión global entre ejecuciones. Implementar propietario, ejecución única, leases recuperables e idempotencia servidor. Refrescar reportes descargados al reconectar aunque no hubiera operaciones que subir. Evidencia: [syncQueue.ts](D:/AppPFI/MiSendero/services/syncQueue.ts), [database.ts](D:/AppPFI/MiSendero/database/database.ts).

**P1 — Estado de recorrido dependiente de navegación.** `RouteMap` reinicia el acumulado en memoria al montarse. La pantalla de desvío calcula distancia al inicio aun para una alerta de separación del trazado y vuelve al mapa sin `startedAt`. «Cancelar» en SOS tampoco conserva los parámetros. La duración final usa fin menos inicio sin descontar pausas. Introducir `sessionId` persistido, estados explícitos y eventos de pausa/reanudación; todas las pantallas deben leer la misma sesión. Usar distancia al segmento de ruta para desvío, distancia al inicio solo para preparación. Ver [AlertRouteScreen.tsx](D:/AppPFI/MiSendero/mobile/screens/AlertRouteScreen.tsx:64) y [RouteCompletedScreen.tsx](D:/AppPFI/MiSendero/mobile/screens/RouteCompletedScreen.tsx:163).

**P1 — Segundo plano y consumo sin validar.** El GPS usa `watchPositionAsync` con permisos de primer plano; no se encontró tarea de ubicación en segundo plano. Expo requiere configuración, permisos y una tarea específica, y aun así el cierre forzado impone límites. Implementar el servicio de sesión fuera de las pantallas, medir batería y probar builds nativos. No prometer envío inmediato al reconectar si la app fue terminada. [Expo Location, SDK 54](https://docs.expo.dev/versions/v54.0.0/sdk/location/).

**P1 — Descarga de mapas: cobertura y proveedor.** El plan se corta en 220 tiles y la verificación comprueba ese mismo plan recortado. Un diagnóstico con la geometría `tresPicos` y zoom 14 alcanzó el límite: 121 tiles estándar y 99 de terreno. Es un caso de función con parámetros explícitos, no una observación de una descarga del usuario. Se puede confundir «todo lo planificado descargado» con «toda la ruta cubierta». Planificar un corredor por ruta y zoom, reducir detalle antes que cortar silenciosamente, y verificar cobertura geográfica. Además, el servicio estándar `tile.openstreetmap.org` usado por el código prohíbe predescargas para uso offline: elegir un proveedor que las permita o tiles propios. No es una prohibición de usar los datos OSM. [Política oficial de tiles](https://operations.osmfoundation.org/policies/tiles/).

**P1 — Datos ausentes o viejos producen mensajes de normalidad.** Falta de SpO₂ se transforma en 97 y elevación faltante en 0; `predictWearableHealth()` no pasa elevación al modelo. Los factores pueden decir «Oxigeno estable» y «Ritmo sostenido» con valores ausentes. El estado del wearable no comprueba caducidad antes de inferir; el puente de Apple lee las muestras más recientes de cada métrica, que pueden corresponder a momentos distintos. Un diagnóstico de la función, sin SpO₂ y con entradas ordinarias, devolvió riesgo bajo con confianza 0,93. Esto demuestra ausencia de abstención, no un diagnóstico sobre una persona. Ver [inferenceEngine.ts](D:/AppPFI/MiSendero/ai/inferenceEngine.ts:94) y [wearableMetrics.ts](D:/AppPFI/MiSendero/services/wearableMetrics.ts:549).

**P1 — Separación de uso real y demostración.** El registro asigna `admin` a todos y una migración promueve cuentas existentes. Limitar esto a un entorno de demostración explícito; en uso habitual, rol de usuario y controles de simulación restringidos. Separar fuente simulada de fuente real también en muestras, eventos y estadísticas. Consentimiento y perfil de experiencia son tablas singleton por dispositivo, aunque contacto y wearable ya tienen usuario: evitar heredar consentimiento al cambiar de cuenta. La URL de API está construida con `http://`; admitir HTTPS completo en configuración remota. Evidencia: [auth.routes.js](D:/AppPFI/MiSendero/backend/src/routes/auth.routes.js:68), [privacyConsent.ts](D:/AppPFI/MiSendero/services/privacyConsent.ts), [api.ts](D:/AppPFI/MiSendero/services/api.ts:6).

## 3. Mejoras de UX/UI por paso

Estos estados describen revisión estática y propuestas; todos necesitan validación visual en móvil.

| Paso | Pantalla / estado general | Cambio recomendado |
|---|---|---|
| 1 | Inicio y explorar — base presente, offline parcial | Priorizar «Continuar recorrido» si existe sesión; luego rutas descargadas y preparación. Mostrar datos aunque falle la foto. Filtros claros por duración, dificultad y «Descargadas en este dispositivo». |
| 2 | Detalle — información útil, procedencia insuficiente | Una acción principal «Preparar recorrido»; dificultad y razones debajo; perfil de elevación real; reporte reciente con fecha; clima con fuente/hora. Distinguir descargable de descargado. |
| 3 | Preparar — confirmaciones incorrectas | «Todo listo» y los checks de mapa, batería y aviso son estáticos en el código. Hacer cada fila verificable o confirmable; agua/equipo son confirmaciones personales. Mostrar pendientes y permitir resolverlos ahí. No afirmar que se avisó a nadie por tener un teléfono guardado. |
| 4 | Navegación — núcleo existente, continuidad parcial | Mapa 2D confiable, posición/precisión, distancia restante y tiempo activo. Indicadores independientes «GPS», «Internet» y «Mapa descargado». SOS y pausa accesibles; detalles de IA desplegables. |
| 5 | Desvío — corrección funcional necesaria | Distancia al trazado, no al inicio; antigüedad/precisión de GPS; acción «Ver mi recorrido registrado». Mantener sesión y evitar llamar «ruta segura» a una línea calculada sin evaluar terreno. |
| 6 | Reportar — formulario completo, demasiado predeterminado | Solicitar primero qué ocurrió y dónde; severidad después; causa opcional. Quitar barro/lluvia preseleccionados para evitar reportes involuntarios. Confirmar «Guardado en el teléfono» y ofrecer volver a la misma sesión. |
| 7 | SOS — prioridad máxima | Contacto, canal disponible, ubicación y hora; confirmación breve; luego estado persistente y opciones concretas. No depender de un modal que desaparece. Acceso a llamada/mensaje manual aunque falte GPS o sesión. |
| 8 | Pausa y resumen — persistencia parcial | Separar tiempo activo/total, pausas y distancia registrada/progreso. Mostrar eventos de desvío, alertas y acciones tomadas; aviso de llegada solo con evidencia de envío. |
| 9 | Perfil, offline y reloj — base presente, opciones incompletas | Mover información técnica de modelos a vista de investigación. Conectar unidades/ahorro/notificaciones a comportamiento real o marcar la función pendiente. Mostrar fuente y última lectura del wearable. |

La base visual compartida en `MiSenderoUI` es aprovechable: colores, botones con rol/estado accesible, controles con área táctil ampliada y avisos anunciables. No hace falta sustituirla. Conviene reforzar texto e icono para cada estado, ampliar objetivos táctiles críticos como decisión de diseño, revisar escalado de tipografía y mantener el CTA de SOS visible en pantallas pequeñas.

El cálculo estático de tokens dio blanco sobre rojo `#D84C3F`: 4,18:1; texto secundario `#6E7A73` sobre fondo `#F6FAF7`: 4,25:1. Para texto normal la referencia WCAG es 4,5:1; hay que oscurecer esas combinaciones cuando se usen para texto normal. El tamaño, peso, superposiciones y estado final deben comprobarse en pantalla antes de afirmar incumplimiento por componente. [W3C: contraste mínimo](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

## 4. Mejor uso y presentación de la IA

**Conservar los tres objetivos y mejorar el contrato de datos.** RandomForest exportado a JSON ya permite inferencia local; no es necesario añadir un modelo generativo ni migrar a TensorFlow Lite para resolver los problemas observados. Documentar la decisión y verificar equivalencia entre predicciones Python y TypeScript con un conjunto fijo de entradas.

| Objetivo | Uso propuesto | Presentación al senderista |
|---|---|---|
| Dificultad de ruta | Evaluar atributos geográficos verificados; guardar ID de ruta, versión/hash del modelo, atributos, fecha y procedencia. Conservar separadamente una dificultad editorial si existe. | «Dificultad estimada: alta. Factores disponibles: desnivel, pendiente y distancia». No afirmar que las razones son una explicación exacta del modelo si provienen de reglas. |
| Fatiga/esfuerzo | Agregar ventanas temporales, velocidad GPS válida y muestras frescas; distinguir señales medidas de imputadas. Comparar con historial/baseline personal solo si existe evidencia suficiente. | «Esfuerzo estimado elevado» + acción + «Basado en FC y ritmo; lectura hace…». Sin datos: «No podemos estimar tu estado físico». |
| Riesgo fisiológico | Separar salida del clasificador y reglas preventivas. Unificar semántica de alto/medio/bajo: hoy `riskLabel=alto` puede terminar como `level=caution`. Incorporar política de calidad, caducidad, repetición e historial. | Estado y acción primero; fuente, antigüedad y limitación después. Evitar «umbral seguro» o «estás bien» como garantías. |

No sustituir faltantes por parámetros normales por defecto. Usar modelos validados para conjuntos de variables disponibles, o abstenerse de producir una clasificación completa. La incertidumbre por dato ausente es distinta de la confianza matemática del clasificador. Separar «sin permiso», «sin dispositivo», «esperando muestra», «muestra antigua», «muestra inválida», «demostración» y «estimación disponible».

El porcentaje actual es la probabilidad interna de la clase elegida por el bosque; no equivale a probabilidad de accidente ni garantía clínica. Antes de presentarlo como confianza interpretable se requiere estudiar calibración. En navegación propondría ocultarlo del nivel principal y mostrarlo, con explicación, en detalles técnicos. [Scikit-learn: calibración](https://scikit-learn.org/stable/modules/calibration.html).

**Validación académica.** Los artefactos guardados, sin reentrenar en esta revisión, informan:

| Modelo | Filas totales / test | Accuracy test | Macro-F1 test | Soporte crítico reducido |
|---|---|---|---|---|
| Fatiga | 1095 / 329 | 99,70 % | 0,9963 | 12 filas de fatiga alta en test |
| Riesgo | 477 / 144 | 100 % | 1,0000 | 6 filas de riesgo alto en test |
| Dificultad | 218 / 66 | 100 % | 1,0000 | 6 filas de dificultad media en test |

Estos valores no prueban precisión en montaña. [build_datasets.py](D:/AppPFI/MiSendero/training/python/build_datasets.py:114) genera las etiquetas con reglas sobre las propias variables de entrada. En BIDMC también genera velocidad y elevación sintéticas antes de dividir train/test: que el test no reciba augmentation adicional no lo convierte en contexto de trekking observado. El bosque está aprendiendo a reproducir esas etiquetas, lo cual es válido como prototipo si se explica así.

La documentación original describe PAMAP2 como actividades físicas, WESAD como estrés/afecto y BIDMC como registros hospitalarios; ninguno proporciona por sí solo verdad de referencia sobre fatiga y riesgo en una travesía. Esta conclusión se obtiene al contrastar sus propósitos con el uso del repositorio. [PAMAP2](https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring), [WESAD](https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html), [BIDMC](https://physionet.org/content/bidmc/1.0.0/).

Para fortalecer la defensa: comparar contra las reglas que generaron las etiquetas y un baseline sencillo; conservar procedencia y agrupación anónima por participante/sesión fuera de las features; dividir por grupos y por tiempo cuando corresponda; aplicar augmentation solo dentro de entrenamiento; informar sensibilidad por clase, confusiones, intervalos de incertidumbre, faltantes y tasa de abstención. El split aleatorio actual no demuestra independencia entre personas/sesiones; no se afirma que haya fuga comprobada, sino que no está controlada. [Scikit-learn: validación por grupos](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data).

Una pantalla de investigación puede mostrar modelo/versión, dataset y mezcla sintética, estrategia de split, métricas y limitaciones. `guardrails.status=ok` solo resume controles programados; no debe traducirse a «validado para seguridad». En el resumen de actividad, guardar versión del modelo, datos usados, calidad, resultado, regla activada y acción del usuario. La validación de campo con etiquetas independientes puede permanecer como trabajo futuro explícito según el alcance de esta entrega.

## 5. Contacto de emergencia sin señal

La condición debe evaluarse en ambos extremos. «Sin internet», «sin servicio celular» y «sin ubicación GPS» son situaciones diferentes. Tener GPS no habilita transmitir mensajes.

| Caso | Conducta propuesta | Texto de estado |
|---|---|---|
| Senderista con internet y contacto alcanzable | Guardar evento local; backend lo acepta; proveedor intenta entrega; registrar recibos disponibles. | «Registrado», luego «Enviado» o «Entregado» solo con evidencia. |
| Senderista sin datos, con servicio SMS/voz utilizable | Ofrecer abrir SMS precompletado y llamada desde el sistema. Mantener copia local e historial del intento. | «Mensaje preparado; completá el envío en Mensajes». |
| Senderista sin red celular ni internet | Guardar SOS con última ubicación y hora; mostrar opciones locales y reintentar cuando exista transporte y la app pueda ejecutar. | «SOS guardado en este teléfono. Todavía no pudimos enviarlo». |
| Senderista conectado; contacto sin señal, sin datos o teléfono apagado | Conservar intento servidor, usar recibos del proveedor si existen; probar contactos/canales secundarios previamente acordados. No inferir que vio el aviso. | «Sin confirmación del contacto». |
| Ambos sin señal | No hay entrega inmediata posible mediante la app sola. Resulta útil un plan de salida enviado previamente y un control de llegada del lado servidor. | «Última comunicación confirmada: …». |
| GPS ausente o permiso denegado | Permitir preparar ayuda sin coordenadas; ofrecer última ubicación con antigüedad o información manual. No esperar indefinidamente un fix. | «Ubicación actual no disponible; última conocida: …». |

`expo-network` no prueba capacidad SMS ni disponibilidad del destinatario. `expo-sms` abre el compositor del sistema; `sent` puede significar enviado/programado, y en Android el resultado es `unknown`. Ninguno demuestra lectura o recepción del contacto. Registrar «acción iniciada» y entrega desconocida cuando corresponda. [Expo SMS, SDK 54](https://docs.expo.dev/versions/v54.0.0/sdk/sms/).

La comunicación satelital depende de hardware, servicio y país. Como ejemplo verificado, Argentina no figura en la lista de disponibilidad de SOS satelital de Apple consultada para esta revisión. MiSendero no debe ofrecerla como capacidad propia garantizada; puede orientar al recurso nativo o dispositivo externo compatible cuando efectivamente exista. [Disponibilidad oficial de Apple](https://support.apple.com/en-us/101573).

**Implementación mínima propuesta para esta tesis:**

1. Persistir primero un `emergency_event` con UUID, propietario, sesión, `occurred_at`, posición/precisión/`location_recorded_at`, estado básico y batería si está disponible. Mantener snapshot del destinatario y registrar cada canal por separado.
2. Separar estados: `saved_local`, `accepted_by_server`, `queued_for_delivery`, `sent_to_provider`, `delivered`, `acknowledged`, `failed`, `cancelled`. Un HTTP 201 solo permite afirmar aceptación del servidor. `acknowledged` requiere una acción explícita del contacto; un recibo técnico no prueba lectura ni ayuda en camino.
3. Permitir SMS/llamada manual como alternativa. El SOS local y esas opciones no deben depender de reautenticarse ni de tener GPS. El envío autenticado al backend puede quedar pendiente de recuperar la cuenta.
4. Implementar outbox de servidor, transporte configurable, recibos autenticados del proveedor y reintentos con espera creciente. Usar clave idempotente estable por evento/destinatario/canal y reintentar con la misma clave si la respuesta se pierde.
5. Dar prioridad a SOS y no incluirlo en el descarte masivo de reportes después de cinco intentos. Si una alerta envejece o se cancela antes de enviarse, conservar trazabilidad y comunicar el estado actual; no mandar un SOS antiguo como si acabara de ocurrir.
6. Mostrar un panel persistente con último intento, canal y respuesta. Prevenir dobles toques con estado de envío real; una confirmación breve con opción accesible es suficiente para el prototipo.

**Mejora adicional: plan de salida y aviso de llegada.** Antes de perder señal, registrar ruta, hora prevista de regreso, margen elegido y contactos que aceptaron recibir avisos. Mostrar «Plan activo» solo después de confirmación del servidor. Un trabajo persistente del backend revisa si llegó el check-in; al vencer el plazo avisa «No se recibió confirmación de regreso», con la última comunicación y su hora. Esto funciona aunque el teléfono del senderista esté desconectado, porque el servidor ya conoce el plazo; no detecta un SOS que nunca llegó ni prueba un accidente. Si el contacto también está fuera de servicio, usar respaldo previamente configurado sin afirmar recepción. Permitir cancelar/extender el plan con confirmación servidor y resolver duplicados. Es una ampliación propuesta, no un requisito explícito ya cumplido.

## 6. Orden de trabajo y aceptación

| Orden | Entregable | Criterio para darlo por terminado |
|---|---|---|
| 1 | Honestidad de SOS, checklist, mapa e IA | Ningún texto confirma contacto avisado, preparación completa, relieve real o estado fisiológico normal sin evidencia. |
| 2 | Repositorio de rutas offline y sesión única | Completar el circuito de uso en modo avión; volver de alerta/pausa/reporte conserva ruta, sesión y acumulados. |
| 3 | Cola durable y canal de emergencia | Reconexión desde cualquier pantalla; usuario correcto; recuperación tras interrupción; envío idempotente y estado de entrega verificable. |
| 4 | Contrato de datos IA y trazabilidad | Faltantes/caducidad/simulación distinguibles; documentación de etiquetas y split; inferencia consistente Python/TypeScript. |
| 5 | UI en dispositivo y evidencia de tesis | Capturas actuales; pruebas de lectura y tareas; matriz requisito → caso → resultado real → evidencia. |

Pruebas de aceptación que faltan: GPS activo sin internet; GPS denegado con red; red disponible con API caída; sesión expirada; destinatario no alcanzable; doble envío; respuesta HTTP perdida después de persistir; reconexión sin pasar por Perfil; cierre con operación `syncing`; cambio A→B con pendientes; cerrar/reabrir durante ruta; pausar sin acumular tiempo activo; SpO₂ ausente y muestra antigua; modelo fuera de rango; mapa parcial; almacenamiento lleno. Para el piloto, agregar pantalla bloqueada, batería y GPS bajo vegetación. No ejecutar un SOS real como prueba accidental: usar destinatarios y proveedores de prueba deliberadamente preparados.

La tesis no exige resolver infraestructura comercial, rescate automático ni integración completa de todos los relojes. Actualizar el texto para reflejar JSON RandomForest en vez de TFLite, las fuentes geográficas realmente utilizadas, Docker/PostgreSQL frente a RDS no demostrado en este repositorio y el alcance exacto de emergencia. El README ya reconoce varias desviaciones, pero su tabla de trazabilidad es más optimista que los recorridos funcionales revisados.

El siguiente paso recomendado es implementar los puntos 1 y 2, luego cerrar transporte/sincronización. La revisión visual queda pendiente de un navegador funcional o ejecución en teléfono; no se reemplazó con capturas antiguas.
