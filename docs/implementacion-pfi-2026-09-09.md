# Implementación de mejoras de MiSendero

Esta entrega implementa las correcciones críticas derivadas de la [revisión de la tesis](revision-pfi-2026-09-09.md). No equivale a completar todos los requisitos y validaciones del PFI. La revisión original se conserva como evidencia del estado anterior.

## Cambios disponibles

| Área | Comportamiento implementado |
| --- | --- |
| SOS | Persiste el pedido sin GPS o sesión, incluye hora de la última ubicación real, distingue guardado local de registro en servidor y ofrece preparar SMS o llamar. No afirma que el contacto recibió un aviso. |
| Reintentos | Identidad estable del SOS y deduplicación en servidor; cola por cuenta, sincronización al volver a primer plano o recuperar conexión, exclusión mutua, recuperación de operaciones interrumpidas y espera progresiva entre reintentos. SOS y cierres de planes no se descartan por alcanzar cinco fallos. |
| Plan de regreso | Nueva pantalla desde «Antes de salir» y desde el resumen final. Permite compartir un plan por SMS y registrar en el servidor un aviso si no se confirma el regreso. |
| Recorrido | Estado persistente de inicio, pausa, reanudación y finalización; tiempo sin pausas, puntos y distancia conservados al cambiar de pantalla. Un coordinador registra GPS en primer plano. Inicio ofrece recuperar el recorrido abierto. |
| Offline | Repositorio compartido de senderos, reportes y catálogo; el trazado guardado sigue disponible aunque las imágenes del mapa estén incompletas. Clima no se consulta sin conexión conocida. |
| Mapas | Plan de descarga completo para ambas capas; reduce resolución para respetar el límite de 220 imágenes, sin cortar la ruta por la mitad. Se retiraron las curvas, arroyos, senderos secundarios y vista 3D generados que aparentaban datos geográficos reales. |
| Preparación | Agua/equipo y acuerdo de regreso se confirman manualmente; batería se lee del dispositivo y mapa descargado se verifica. Se eliminó «Todo listo» como afirmación incondicional. |
| Exploración | Las tarjetas muestran nombre y datos aunque no cargue su foto, con indicación de imagen no disponible. |
| IA | Abstención ante variables ausentes, no finitas o inválidas. SpO₂ ausente no se reemplaza por 97 y desnivel ausente no se reemplaza por cero. Lecturas antiguas o futuras no se usan para inferencia. |
| Presentación de IA | Modelo experimental, variables disponibles, recomendaciones orientativas y falta de información. Se retiraron porcentajes de confianza del panel principal; los resultados del conjunto de evaluación se identifican como internos. |
| Salud nativa | HealthKit respeta la ventana de la salida; pulso, velocidad y oxígeno no se combinan como simultáneos cuando distan más de un minuto. Una lectura nueva de pasos no rejuvenece un pulso anterior. |
| Cuentas | Consentimientos, preferencias, experiencia, favoritos, puntos y operaciones separados por cuenta. Revocar consentimiento borra los datos de salud de esa cuenta. Registro de usuarios con rol `user`; las migraciones ya no promueven usuarios a administrador. |

## Emergencias y falta de señal

| Situación | Qué puede hacer esta versión |
| --- | --- |
| Sin internet, con servicio celular | Preparar un SMS en Mensajes o abrir una llamada. La app no presupone que el sistema haya enviado el SMS. |
| Sin cobertura celular ni internet | Guardar el pedido y consultar el mensaje y la última ubicación. No puede transmitir mediante SMS, llamada o API. |
| Contacto sin señal | El aviso puede quedar demorado. No se marca como recibido o leído. Antes de partir se debe acordar una persona alternativa y qué hacer si no se confirma el regreso. |
| Teléfono del excursionista desconectado después de registrar el plan | El servidor conserva la hora prevista y el margen. Puede generar el aviso por falta de confirmación sin otro mensaje del teléfono. |
| Regreso confirmado offline | La confirmación queda pendiente en la cola. El servidor todavía puede emitir el aviso hasta recibirla. |
| Mensaje ya aceptado por el canal | Cerrar el plan evita futuros intentos pendientes, pero no puede retirar un aviso ya enviado o en curso. |

«Registrado en servidor» significa almacenamiento del SOS. Este endpoint no envía mensajes al contacto. El aviso automático implementado corresponde al **plan de regreso**, mediante el adaptador configurable descrito abajo.

El SOS utiliza UUID y `UNIQUE(user_id, client_event_id)` para evitar duplicados después de una respuesta perdida. No usa coordenadas de simulación. Las solicitudes creadas sin sesión no se atribuyen a quien inicie sesión más tarde; permanecen locales. Los registros históricos `sent` se migran a `registered` porque el servidor anterior no tenía evidencia de transporte.

## Configuración para ejecutar

Se incorporaron `expo-sms`, `expo-battery` y `expo-crypto` en las versiones compatibles con Expo SDK 54. Las dependencias y el archivo de bloqueo están actualizados. Las funciones nativas deben probarse en una compilación de desarrollo instalada en un teléfono.

### API

En la configuración del cliente puede usarse `EXPO_PUBLIC_API_URL`, una URL completa que termine en `/api`. Usar HTTPS fuera del desarrollo local. Se conserva el mecanismo previo por host para desarrollo. Las solicitudes tienen una espera máxima de diez segundos para recibir respuesta HTTP.

Al iniciar el backend se aplican las migraciones habituales del proyecto, incluidas `003_honest_emergency_status.sql` y `004_trip_plans.sql`. Los tests usan bases de prueba; no se ejecutaron migraciones contra una base de producción.

Los administradores existentes conservan su rol: el operador debe revisar explícitamente los permisos otorgados por versiones anteriores. No se hizo una degradación masiva de cuentas.

Los registros antiguos sin propietario (preferencias, consentimiento, favoritos y operaciones pendientes) no se asignan automáticamente a la siguiente cuenta que ingrese. Permanecen en sus tablas anteriores o sin dueño; las preferencias y el consentimiento deben configurarse para cada cuenta. Esta decisión evita publicar información de una persona con las credenciales de otra.

### Proveedor de mapas offline

Configurar en el cliente:

```dotenv
EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL=https://PROVEEDOR-AUTORIZADO/standard/{z}/{x}/{y}.png
EXPO_PUBLIC_OFFLINE_TERRAIN_TILE_URL=https://PROVEEDOR-AUTORIZADO/terrain/{z}/{x}/{y}.png
EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION=ATRIBUCION-EXIGIDA-POR-EL-PROVEEDOR
```

Las URLs deben permitir descarga y almacenamiento offline bajo las condiciones contratadas. No colocar secretos privados en variables `EXPO_PUBLIC_*`. El servicio público `tile.openstreetmap.org` se rechaza como origen de descarga masiva; su [política oficial](https://operations.osmfoundation.org/policies/tiles/) prohíbe ese uso. Sin proveedor configurado, se guarda geometría y reportes y se informa que la descarga del mapa base no quedó disponible.

La verificación de archivos se mantiene: la disponibilidad se calcula sobre el plan completo, no sobre el subconjunto que alcanzó a descargarse. Para rutas que no caben ni en la resolución mínima se devuelve un plan vacío y no se anuncia una descarga completa.

### Canal de avisos por atraso

Configurar únicamente en el backend:

```dotenv
ALERT_WEBHOOK_URL=https://ADAPTADOR-DE-NOTIFICACIONES/events
ALERT_WEBHOOK_TOKEN=SECRETO-DEL-ADAPTADOR
```

La activación de planes responde `503` si faltan esas variables o el endpoint no utiliza HTTPS. Una configuración presente no demuestra que el canal esté operativo: debe validarse antes de usar el servicio en salidas reales.

Cada 30 segundos, el proceso del backend revisa los planes persistidos. Una caída entre creación del plan y creación del trabajo se recupera al reconstruir los trabajos faltantes. Los intentos usan una reserva temporal en la base para evitar procesamiento simultáneo. Ante fallo se reintenta con espera creciente, hasta quince minutos entre intentos.

El adaptador recibe `POST` con `Authorization: Bearer …`, `Content-Type: application/json` e `Idempotency-Key: trip-overdue-<id>`. Ejemplo del contrato:

```json
{
  "event": "trip_return_unconfirmed",
  "notification_id": "trip-overdue-123",
  "contact": { "name": "Contacto de prueba", "phone": "+5491100000000" },
  "expected_return_at": "2026-09-10T20:00:00.000Z",
  "grace_minutes": 30,
  "message": "Regreso no confirmado. Puede estar sin señal; esto no confirma un accidente."
}
```

El receptor debe aceptar el evento de forma duradera, deduplicar por la clave y gestionar su canal SMS/push, reintentos de entrega y escalamiento. Un `2xx` significa **aceptado por el canal**, no entregado ni leído. No se implementó confirmación del destinatario ni se contrató un proveedor. El servidor debe mantenerse ejecutando para procesar los plazos; reinicia pendientes tras una caída, pero no puede cumplir un horario mientras está detenido.

No se enviaron avisos a contactos reales durante este trabajo: los tests del procesador inyectan un transporte falso.

## Alcance de la IA

Las probabilidades del bosque no se presentan como porcentajes de seguridad personal. El modelo de riesgo exige las variables con las que fue entrenado; actualmente la integración del reloj no obtiene desnivel acumulado medido, por lo que se abstiene de estimar riesgo con ese conjunto incompleto. La fatiga puede estimarse cuando sus propias variables son válidas. Las actividades nuevas sin una estimación agregada guardan fatiga nula y muestran «Sin estimación», en lugar de inventar fatiga baja. Los avisos por umbrales siguen separados del resultado del bosque y son experimentales.

La antigüedad máxima de la lectura para inferencia es cinco minutos; se toleran hasta treinta segundos de desfase futuro del reloj. Los límites de admisión de variables son validaciones técnicas, no límites clínicos personalizados.

No se reentrenaron los modelos ni se declaró validación clínica. Siguen pendientes una evaluación por persona/salida independiente, revisión de etiquetas derivadas de reglas, calibración, desempeño por clase, falsos negativos y pruebas en condiciones reales. La ficha anterior explica la procedencia y limitaciones de los conjuntos utilizados.

## Validación y pendientes de dispositivo

- TypeScript: comprobación del proyecto completo.
- App: 54 pruebas en 14 suites, incluidas pausas, continuidad de sesión, aislamiento de cuentas, reintentos, SOS sin GPS/sesión, exclusión de ubicaciones simuladas, datos incompletos y antigüedad del reloj.
- Backend: 38 pruebas en 8 suites, incluidas deduplicación del SOS, plazos del plan, cierre, ausencia de canal, fallos del proveedor y recuperación de trabajos interrumpidos.
- Exportación web: completada. Al retirar la escena 3D del mapa, el paquete de entrada observado pasó de aproximadamente 3,24 MB a 2,35 MB; no es una medición de carga en dispositivo.
- Revisión del diff: sin errores de espacios finales.

La captura de interfaz mediante la herramienta de navegador no estuvo disponible en este entorno. No se afirma una verificación visual o de accesibilidad con lector de pantalla. Tampoco se verificaron SMS, llamadas, batería ni lecturas HealthKit/Health Connect en hardware real.

El seguimiento implementado es de **primer plano**. Se conserva estado y distancia al navegar dentro de la app; cerrar, bloquear o suspender el teléfono puede interrumpir las mediciones. No se rellenan esos tramos con una línea estimada. Siguen pendientes el servicio de ubicación en segundo plano, permisos nativos y pruebas de consumo y recuperación en Android/iOS. La UI comunica esta limitación antes de iniciar.

Otras tareas del informe siguen abiertas: validación integral de los RF/RNF, usabilidad con participantes, escalamiento a un contacto alternativo, confirmación de recepción por el destinatario y una política operativa de rescate acordada. Esta entrega no promete conectividad satelital ni envío sin un medio de comunicación disponible.
