# Corrección del arranque de Android — 1.0.3

La APK 1.0.2 reproducía el bloqueo en «Cargando rutas cercanas...». La apertura de
la base cifrada llegaba a su limpieza de la base anterior y pasaba a `File` la
ruta absoluta que devuelve SQLite en Android. La API de archivos requiere una
URI `file://`. El error rechazaba la inicialización y la pantalla inicial no
manejaba ese rechazo.

Se normalizan las rutas usadas para la limpieza de la base anterior y sus archivos
auxiliares. Se conservan el cifrado, los controles de integridad y la clave local.
El inicio maneja errores y una espera excesiva con un botón «Reintentar inicio».
Se elimina una llamada redundante de inicialización sin manejo de errores.

Se reprodujo el bloqueo con el código anterior y se probó una actualización de
la misma instalación de Android, con sus datos existentes: el código corregido
alcanzó «Bienvenida de nuevo / Iniciar sesión». También hay pruebas de inicio
normal, sesión guardada, error recuperable, espera limitada y contratos de URI.
Las pruebas de la base simulan la frontera nativa; la prueba del emulador usa los
módulos nativos de la APK.
