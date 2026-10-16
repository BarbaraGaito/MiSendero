# Cambios de privacidad y pendientes de verificación — 16/10/2026

Aplicados en `D:/AppPFI/MiSendero`, sobre `64f3007ed801cb631fdf2a5902dd2e9de6bbc670`. La tesis y sus originales de auditoría no se modificaron. Las [notas recibidas](pendientes-originales-2026-10-16.md) se conservaron con SHA-256 `52a60e55215de968a340d6d62447ba1d28acd3f6e85a38f7326ece545c269ae7`.

Esta entrega acredita cambios y pruebas locales. No acredita cumplimiento jurídico, aprobación de tiendas, infraestructura publicada, funcionamiento en campo ni validación clínica.

## Implementación

| Pendiente original | Cambios verificables en el repositorio | Lo que permanece abierto |
| --- | --- | --- |
| 1. Credenciales, transporte, logs | SecureStore o sesión en memoria; nunca se escribe el token en SQLite. Se descartan tokens heredados en texto plano y se exige un nuevo ingreso. Configuración y ejecución de distribución exigen API HTTPS; Android sin respaldo automático ni tráfico claro en distribución. Logs HTTP sin URL, IP, headers o cuerpo; errores sin detalles SQL; redacción adicional de credenciales, contactos y coordenadas. La autenticación consulta la existencia y el rol actual de la cuenta. | Cifrado y permisos efectivos de archivos, TLS del servicio publicado, almacenamiento de logs, accesos, rotación, incidentes y recuperación. La eliminación lógica de filas no acredita borrado físico del soporte. |
| 2. Decisiones independientes | Términos, autorización fisiológica y analítica separados; los permisos del SO siguen siendo independientes. Decisiones y retiros registran titular, finalidad, texto, versión, fecha de decisión y recepción API; cola idempotente offline. Retiro fisiológico elimina muestras/conexión del titular y bloquea nuevas muestras. Las autorizaciones antiguas acopladas requieren una nueva decisión. | Ensayo de negativa y revocación en HealthKit/Health Connect físicos. El registro de una autorización no establece la admisibilidad jurídica del tratamiento. |
| 3. Baja | Perfil con contraseña y confirmación; `DELETE /api/auth/me`; recurso `/account-deletion`. Se eliminan cuenta, reportes y sus nombres/textos, actividades, alertas, planes, trabajos, decisiones y relaciones por cascada. Validación de cuenta en otras instalaciones al volver a conectar. Marcador local de baja suspende colas y nuevos envíos antes de pedir la baja; un resultado perdido se puede reintentar. Un rechazo explícito de contraseña no bloquea la cuenta. | Ensayos con PostgreSQL real, procesos concurrentes, dispositivos físicos y respaldos. Un webhook o SMS ya despachado no se puede retirar por borrar la cuenta. |
| 4. Derechos y conservación | Web con descarga de datos remotos y actualización del nombre, además de baja. Canal configurable `PRIVACY_CONTACT_URL` para solicitudes fuera del autoservicio, incluidos contactos. | Identificar responsable, canal atendido, atención integral, identidad proporcional y calendario de plazos. La descarga remota no incluye muestras ni otros datos exclusivamente locales. Falta aprobar conservación y excepciones por categoría. |
| 5. Reportes y copias | Contrato explícito sin autor ni precisión GPS del autor; conserva ID de reporte para su gestión, posición del incidente y campos de terreno. Fecha de observación distinta de recepción, vencimiento basado en observación y fecha de corrección. Corrección/retiro del titular, denuncias, bloqueo por usuario y moderación admin. Web de moderación para administradores. Se limpian nombres en reportes históricos asociados a cuentas. Copias offline depuradas; renovación con conexión y al sincronizar; vencimientos locales. | No es posible propagar un retiro a un dispositivo desconectado en el instante del cambio. Deben verificarse tiempos de atención, revisión de texto libre, proveedores de moderación y todos los binarios instalados. |
| 6. Salud y modelos | Se vuelve a comprobar consentimiento antes/después de lecturas nativas y al guardar. Las muestras requieren una preferencia vigente. Textos distinguen reglas experimentales de modelos de investigación; ningún modelo fue habilitado para campo. | Permisos y borrado en dispositivos físicos, fallos nativos, calidad de medición y evaluación del uso previsto. |
| 7. Estados y avisos | SOS muestra preparación, envío/recepción API, envío al contacto, entrega y asistencia por separado. No inventa confirmación de entrega ni rescate. Términos compartidos/versionados con el backend; aceptar términos no concede tratamiento fisiológico ni analítica. | Capturas de binarios, canales reales de aviso y evaluación profesional de las comunicaciones. |
| 8. Gobernanza | Se documentan decisiones y evidencias pendientes aquí. No se inventó un responsable, domicilio, inscripción ni contrato. | Responsable real, política completa, bases alcanzadas, menores/contactos, contratos, países, subencargados, incidentes y transferencias. |
| 9. Licencias | Inventario reproducible de dependencias, pantalla de fuentes/licencias y atribución ampliada de Copernicus y Esri. Descarga offline exige ambos proveedores HTTPS, atribución, referencia de licencia y confirmación de revisión por el operador. | Autorización efectiva de ambos proveedores, revisión de avisos literales de Copernicus y créditos por zona de Esri, expediente de todas las imágenes/datos, licencia de GeoFatigue y plan de Open-Meteo. Las llamadas de grilla DEM del cliente siguen siendo directas a Open-Meteo. |
| 10. Distribución y finalidad | Configuración de distribución y textos ajustados a capacidades existentes. | Contrastar binarios y fichas Apple/Google, restricciones de ubicación/SOS y Health Connect, y encuadre ANMAT según finalidad y comunicaciones reales. |

El ID público de un incidente permite corregirlo o denunciarlo; no identifica públicamente la cuenta autora. La API autenticada agrega `is_mine` para mostrar las acciones del titular. Bloquear un autor oculta sus reportes para esa cuenta; no los retira para todas las personas. Una denuncia no implica por sí misma que el contenido haya sido ocultado.

## Puesta en servicio

1. Aplicar `backend/migrations/008_privacy_and_moderation.sql` junto con las migraciones existentes, primero en una copia de prueba. El arranque del backend ya ejecuta las migraciones. Revisar y ensayar la transacción de baja y las cascadas con PostgreSQL real.
2. Configurar `EXPO_PUBLIC_API_URL` con el dominio HTTPS real en EAS para `preview`/`production`. El valor usado en la exportación local fue un dominio reservado de prueba, no un servicio desplegado. El backend HTTP del compose local no configura TLS público.
3. Publicar `/account-deletion` bajo el dominio del backend y verificar la ruta desde el enlace de Perfil y desde las fichas de tienda. La página mantiene la sesión solo en memoria; exige contraseña para eliminar. Los recursos están dentro de `backend/src/public` y se incluyen en la imagen Docker existente.
4. Configurar y atender `PRIVACY_CONTACT_URL` en el backend. Debe corresponder al responsable real; una variable vacía no resuelve los derechos de contactos u otros pedidos fuera del autoservicio.
5. Antes de activar tiles offline, documentar ambas licencias y completar `EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL`, `EXPO_PUBLIC_OFFLINE_TERRAIN_TILE_URL`, `EXPO_PUBLIC_OFFLINE_TILE_ATTRIBUTION`, `EXPO_PUBLIC_OFFLINE_TILE_LICENSE_URL` y `EXPO_PUBLIC_OFFLINE_TILE_LICENSE_CONFIRMED=true`. La confirmación es una declaración del operador, no una verificación automática del permiso.
6. Actualizar los binarios instalados. Los clientes anteriores no ejecutan la nueva limpieza local ni el nuevo control de consentimiento. Ante una restauración antigua, no habilitar tráfico hasta reconciliar las bajas registradas fuera de ese respaldo y revocar las credenciales previas.

La baja suspende nuevas solicitudes desde el cliente actualizado. Una solicitud ya en curso puede competir con la eliminación; las referencias a la cuenta impiden recrear datos remotos después de borrarla. Esto requiere pruebas de concurrencia reales. Un aviso externo ya enviado puede seguir su curso. El bloqueo de la cola no equivale a detener un mensaje en manos del receptor.

## Conservación y solicitudes: decisiones que debe aprobar el responsable

La siguiente tabla describe el comportamiento técnico actual y el cierre requerido. No fija plazos legales de conservación ni presenta una política aprobada.

| Categoría / finalidad / destino | Regla técnica actual | Decisión y evidencia pendientes |
| --- | --- | --- |
| Cuenta y autenticación / acceso / API y dispositivo | Cuenta hasta baja; token persistente solo en SecureStore, o temporal en memoria; JWT de siete días sujeto a existencia de cuenta. | Política de inactividad, revocación ordinaria, seguridad de archivos y criterio de conservación de evidencias. |
| Términos y decisiones / trazabilidad / API y SQLite | Texto/versiones de nuevas decisiones, titular y fechas; revocación añade evento; baja elimina eventos. No se reconstruye el texto de aceptaciones históricas. | Plazo específico, base de conservación y excepciones documentadas; acceso restringido y borrado de copias. |
| Métricas fisiológicas / actividad local / SQLite | Retiro de autorización y baja limpian muestras y conexión local. No se envían muestras a entrenamiento. | Necesidad de ventana temporal, protección del archivo y pruebas físicas de revocación. |
| Actividades, GPS y preferencias / historial / API y SQLite según dato | Hasta eliminación de cuenta; no hay una caducidad general por edad. | Plazo por finalidad, eliminación de inactividad, opción de borrar por categoría y comprobación de almacenamiento físico. |
| Contactos, planes y alertas / comunicaciones / API, SQLite y receptor externo | Baja elimina copias de la cuenta y trabajos en API; los mensajes externos ya compartidos permanecen fuera de su control. | Procedimiento de derechos de contactos, destinatarios, retención de planes/alertas cerrados y cancelación externa. |
| Reportes / información de terreno / API y copias | `REPORT_STALE_AFTER_DAYS` (30 por defecto), contado desde observación; copia offline usa `expires_at` recibido. Reportes antiguos sin esa fecha aplican 30 días desde observación/creación. Retiro/moderación se propagan con conexión. | Justificar el plazo operativo; coordinar cambios de configuración, clientes anteriores y respaldos. |
| Logs / diagnóstico / destino del proceso y plataforma | Metadata mínima y redacción; el código no establece rotación o plazo del destino. | Fijar plazo, responsables, acceso, rotación y prueba del recolector real; no inferirlos de pino. |
| Respaldos / recuperación / infraestructura | Android declara `allowBackup=false` en nuevos binarios; no hay infraestructura de respaldo remoto administrada aquí. | Ciclo de vida, cifrado, accesos, excepciones y registro de supresiones independiente del respaldo; ensayo de restauración sin reaparición. |

Para solicitudes fuera del autoservicio, se debe designar titular y suplente del canal, registrar recepción, derecho invocado y vencimiento, comprobar identidad con el mínimo necesario, identificar copias/destinatarios, responder sin revelar datos ajenos y conservar constancia de atención. La AAIP informa diez días corridos para acceso y cinco hábiles para rectificación, actualización y supresión; el cómputo y las excepciones deben validarse para cada caso. [Fuente oficial](https://www.argentina.gob.ar/aaip/datospersonales/derechos).

## Proveedores y licencias

| Recurso | Tratamiento visible en el código | Evidencia operativa pendiente |
| --- | --- | --- |
| Backend/PostgreSQL | Cuentas, actividades, reportes, planes, alertas y decisiones; hosting no identificado. | Operador, país, accesos, contratos, respaldos, transferencias y supresiones. |
| Open-Meteo | Clima y elevaciones del backend; grilla DEM consultada directamente desde el cliente con coordenadas del trazado y dirección IP visible al proveedor. | Plan efectivo, endpoint, condiciones de uso, tráfico y eventual intermediación del backend. No incluir claves comerciales en variables `EXPO_PUBLIC_*`. |
| OSM / Esri / proveedores configurados | Imágenes del área de mapa, atribuciones y descarga según configuración; proveedor ve solicitudes e IP del cliente. | Licencias de servicio y descarga, contratos y créditos por área. Bloquear OSM estándar no habilita automáticamente una alternativa. |
| Salud / Health Connect | Lecturas opcionales mediante puentes del dispositivo; las muestras quedan locales. | Pruebas nativas y condiciones de plataformas para el uso previsto. |
| Receptor del webhook / SMS | Contacto, salida y aviso; receptor configurable, proveedor no identificado. | Contrato, país, deduplicación, entrega, cancelación, retención y atención de supresión. |
| Fotos y datos por sendero | Procedencia en fichas del catálogo; no equivale a revisar todos los derechos de imagen. | Expediente por archivo/URL, autorización, versión, atribución y compatibilidad offline/comercial. |
| Dependencias | [Inventario de 1.625 entradas](dependency-licenses.csv), versiones, ámbito, licencias declaradas, integridad y hash del lock. | Tres entradas sin metadatos de licencia (`exit`, `expo-2d-context`, `string-format`); revisar archivos LICENSE y obligaciones de todas las dependencias. El inventario se regenera con `node scripts/license-inventory.js`. |
| GeoFatigue y modelos | Continúan como investigación, sin modelos habilitados para campo. La discrepancia de licencia ya está identificada en `training/python/public_sources.py`. | Aclaración del titular sobre CC BY frente a CC BY-NC-SA antes de ampliar la reutilización. No habilitado por esta entrega. |

Fuentes consultadas para revisar estas condiciones: [elevación Open-Meteo](https://open-meteo.com/en/docs/elevation-api), [planes Open-Meteo](https://open-meteo.com/en/pricing), [licencias Copernicus, GLO-90 artículo 6](https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf), [atribución Esri](https://doc.arcgis.com/en/arcgis-online/reference/display-copyrights.htm), [World Imagery](https://doc.arcgis.com/en/data-appliance/2024/maps/world-imagery.htm), [política de tiles OSM](https://operations.osmfoundation.org/policies/tiles/). La atribución ampliada y los enlaces de la app no sustituyen la revisión de los avisos literales exigibles al producto distribuido.

## Trazabilidad RL-01 a RL-14

La matriz original está en `D:/Importante/UADE/PFI/PFI25/outputs/viabilidad-legal/pendientes-internos/legal-requisitos.csv`. Se leyó como referencia y no se modificó. Sus relaciones RF/RNF originales se conservan allí. Ninguna fila se declara cerrada integralmente por esta entrega.

| Propuesta | Estado sustentado y falta para cierre |
| --- | --- |
| RL-01 | Términos versionados; política completa y responsable real pendientes. |
| RL-02 | Independencia, negativa, retiro y trazabilidad probados localmente; permisos nativos y revisión del texto en binarios pendientes. |
| RL-03 | Acceso remoto y nombre por autoservicio; derechos completos de usuarios/contactos, confidencialidad y plazos operativos pendientes. |
| RL-04 | App/API/web y suspensión de colas probadas por servicios/API; faltan dispositivos, PostgreSQL real, concurrencia y restauración. |
| RL-05 | Vencimiento de reportes y baja; política y ejecución de conservación general pendientes. |
| RL-06 | HTTPS de distribución, almacenamiento de tokens y redacción probados; binario/infraestructura/recuperación pendientes. |
| RL-07 | Contrato, corrección, vencimiento, retiro, denuncia, bloqueo y moderación implementados; operación y ensayos integrales de copias pendientes. |
| RL-08 | Opcionalidad y avisos; admisibilidad jurídica y validación nativa pendientes. |
| RL-09 | Inventario técnico inicial; contratos, países, receptores y garantías sin acreditar. |
| RL-10 | Inventario y atribuciones ampliadas; expediente completo y permisos efectivos sin cerrar. |
| RL-11 | Controles de configuración; fichas, binarios y decisiones de revisión sin verificar. |
| RL-12 | Estados explícitos y abstención de modelos conservada; validación de comunicaciones y encuadre profesional pendientes. |
| RL-13 | No se implementó una política de menores o representación sin decisión profesional del responsable. Contactos requieren canal y procedimiento. |
| RL-14 | Documentación de pendientes; responsable, bases, inscripciones e incidentes operativos sin acreditar. |

En distribución deben examinarse específicamente las restricciones de ubicación para servicios de emergencia de [Apple, sección 5.1.5](https://developer.apple.com/app-store/review/guidelines/), los usos admitidos de [permisos de salud de Android](https://support.google.com/googleplay/android-developer/answer/12991134?hl=en), y la baja en [Apple](https://developer.apple.com/support/offering-account-deletion-in-your-app/) y [Google Play](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en). Cambiar advertencias no acredita aprobación de ese uso. El posible encuadre ANMAT queda sujeto a validación profesional sobre finalidad y comunicación efectivas.

## Validación local y límites

- `npm run typecheck`: correcto.
- `npm test -- --runInBand`: 30 suites, 185 pruebas correctas.
- `cd backend` y `npm test -- --runInBand`: 12 suites, 93 pruebas correctas.
- Exportación web de Expo completada con una URL HTTPS reservada para prueba; no constituye despliegue. Metro advirtió sobre rutas de exportación de cargadores de `three` y completó la resolución alternativa.
- Pruebas nuevas: `services/__tests__/privacyControls.test.ts`, `backend/tests/privacyControls.test.js`, `backend/tests/logPrivacy.test.js`; regresiones de renovación de reportes en `trailRepository.test.ts`.
- Las pruebas backend usan pg-mem: no acreditan bloqueos, rollback y concurrencia de PostgreSQL real. No había Docker disponible para ese ensayo.
- Se intentó iniciar la comprobación visual web; no había navegadores habilitados y el navegador integrado devolvió `Browser is not available: iab`. La página y sus recursos sí se verificaron por HTTP con Supertest; no se afirma una prueba interactiva de sus botones ni capturas de dispositivo.
- No se accedió a cuentas de tiendas, dispositivos físicos, infraestructura productiva, respaldos ni contratos.

Las evidencias automatizadas resumidas se conservan en [privacy-controls-validation.json](privacy-controls-validation.json). Las pruebas automatizadas no convierten los casos de aceptación operativos pendientes en pruebas ejecutadas.
