# Mapas básicos 2D sin conexión

La descarga predeterminada guarda un mapa vectorial básico de la zona, el trazado y los datos disponibles del sendero y sus reportes. Los mapas de las zonas del catálogo se preparan antes de publicar la app y se incluyen en la APK. Al tocar Descargar se extrae la zona seleccionada al almacenamiento persistente del teléfono. No necesita claves de un proveedor de mapas ni infraestructura nueva en AWS.

El mapa muestra caminos, senderos, cursos de agua, lagos, bosques y referencias con nombre que figuran en OpenStreetMap. No tiene imágenes satelitales ni relieve 3D. El nivel de detalle depende de los datos reales de cada zona. Las rutas nuevas fuera de las zonas incluidas requieren preparar un catálogo actualizado; no se ofrecen como descargadas con un fondo vacío.

## Uso y comprobación en Android

1. Instalar una APK nueva compilada con estos cambios. La APK anterior no se actualiza sola.
2. Con conexión, elegir un sendero y descargar su mapa.
3. Abrirlo desde Mapas descargados: fuerza la vista 2D local incluso con Wi-Fi.
4. Activar modo avión, cerrar y volver a abrir la app, entrar en Mapas descargados y abrir la misma ruta. Comprobar caminos, referencias, trazado y zoom.
5. La posición funciona con GPS y permiso de ubicación. Fuera de la zona guardada aparece un aviso para volver al recorrido. El mapa no descarga más datos al desplazarse.
6. Eliminar un mapa y comprobar que deja de estar disponible. Cancelar o interrumpir un guardado no debe dejarlo marcado como completo.

Los archivos se verifican antes de marcar la descarga como disponible y nuevamente al abrirla. El paquete local conserva la geometría asociada para rechazar archivos corruptos o mapas que correspondan a un trazado anterior. Se mantienen compatibles los paquetes raster de versiones previas.

## Preparación de datos

`node scripts/prepare-offline-maps.cjs` prepara las regiones a partir de las geometrías versionadas del catálogo y consultas acotadas a Overpass. Es una tarea manual de preparación; la app no utiliza las instancias públicas como backend. El script conserva las respuestas en `tmp/offline-map-sources` para reanudar sin repetir consultas y genera `assets/offline-maps/catalog.json`. Esa salida debe versionarse y verificarse antes de una nueva compilación.

`node scripts/prepare-offline-maps.cjs --verify` comprueba que todos los recorridos cartografiados del catálogo queden cubiertos, que existan entidades reales y que se conserven los créditos y fechas de los datos.

Datos: © OpenStreetMap contributors, ODbL 1.0. El catálogo incluye la licencia, atribución y fecha de la fuente; el visor mantiene el crédito visible y la pantalla Fuentes y licencias explica su procedencia también sin conexión.

- Fuente y licencia: https://www.openstreetmap.org/copyright
- ODbL: https://opendatacommons.org/licenses/odbl/1-0/
- Preparación responsable: https://dev.overpass-api.de/overpass-doc/en/preface/commons.html

## Proveedor raster opcional

Si se configura `EXPO_PUBLIC_OFFLINE_STANDARD_TILE_URL`, se conserva la descarga raster existente (HTTPS XYZ con permiso de uso offline, atribución y licencia configuradas). No se utiliza `tile.openstreetmap.org` para descargas masivas. Sin esa variable, el flujo usa automáticamente el mapa vectorial incluido.

La visualización 3D online sigue disponible en las pantallas normales. Abrir desde Descargados usa exclusivamente el mapa básico local, sin solicitudes de terreno, satélite ni imágenes remotas.
