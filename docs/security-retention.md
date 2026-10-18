# Conservación de datos nuevos

Política aprobada el 18 de octubre de 2026. La migración agrega marcas nulas a los históricos y habilita marcas para altas posteriores. No rellena las marcas antiguas.

- Salud local: 7 días desde inserción.
- Puntos GPS locales: 90 días; solo de sesiones finalizadas, nunca de recorridos activos/pausados o sin confirmación de fin.
- Payload de cola: 7 días desde confirmación o abandono explícito. Se mantienen identidad, dedupe, propietario, estado y referencia remota. No se retiran pendientes, fallidos ni envíos en proceso.
- SOS remoto registrado: 30 días; se retiran ubicación, contacto, mensaje y datos asociados, manteniendo una constancia mínima de identidad para evitar duplicados. No representa envío/recepción de socorro.
- Plan confirmado/cancelado: 30 días desde cierre y alta, excluyendo trabajos pendientes/en proceso; se eliminan contactos y referencia al sendero. La identidad mínima conserva la idempotencia. Las copias locales de planes elegibles cerrados se retiran al activar la aplicación.
- Revocaciones: hasta expiración; cuotas: dos días.

El cliente ejecuta mantenimiento al activarse, reconectarse y durante sincronización con la app activa. El servidor lo ejecuta al inicio y diariamente. El plazo es un umbral de elegibilidad, no una garantía de ejecución mientras el dispositivo está apagado. Reintentos de mantenimiento son idempotentes. Los resúmenes del historial permanecen hasta eliminación del titular. La política no modifica las fuentes HealthKit/Health Connect ni los SMS ya enviados. Los backups requieren un procedimiento operativo independiente.

Antes de desplegar: ejecutar migraciones 012–014 y comprobar el mantenimiento sobre una copia de prueba. No se ejecutaron migraciones ni borrados sobre RDS durante la corrección.
