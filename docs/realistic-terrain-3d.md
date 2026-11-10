# Vista 3D del terreno

La vista ofrece **Imagen**, con fotografía satelital de referencia, y **Relieve**, con color por altitud y curvas de nivel. Ambas conservan el mismo trazado y las alturas reales, sin exageración vertical.

El botón **Información del mapa**, abajo a la derecha, abre una ficha con escala, norte, altura ×1, rango de elevación, detalle del DEM, clima y suelo reportado. La misma ficha incluye las fuentes y el copyright del mapa, con acceso a las licencias completas. Estos datos no ocupan permanentemente la vista 3D; abrir y cerrar la ficha conserva la escena y su cámara.

El recorrido se apoya en la superficie de alturas, incluidos sus bordes. Las flechas muestran el sentido del trazado; las etiquetas agregan distancia acumulada y altitud aproximada. El encuadre inicial incluye la ruta completa según la proporción de pantalla. La escala se calcula sobre el terreno visible en el centro y se actualiza al mover la cámara; la flecha norte sigue la orientación geográfica.

Se leen entre 17 × 17 y 33 × 33 muestras reales según la extensión de la ruta, con una malla de renderizado limitada a 65 × 65 vértices. La descarga usa hasta nueve mosaicos DEM Terrarium y hasta tres solicitudes simultáneas, con caché compartida de mosaicos y grillas durante la sesión. La interpolación facilita la visualización, pero no agrega precisión geográfica. Los mapas antiguos siguen siendo legibles; las grillas menos detalladas se pueden actualizar al abrir el 3D con conexión, conservando la copia anterior si falla la consulta.

La imagen satelital usa hasta 2048 píxeles por lado, con proporción geográfica consistente con el área consultada para evitar desplazamientos entre foto, recorrido y relieve. Incluye filtrado y sombras del terreno. La imagen es histórica, no una cámara en vivo.

Mientras se carga la imagen del terreno, un indicador cubre la superficie sin textura. Desaparece después del primer frame con la imagen aplicada. Si la descarga falla o supera 20 segundos, se muestra el relieve por altitud; la ficha de información indica que la imagen no está disponible. Cambiar de ruta o pasar a Relieve descarta los resultados tardíos de la descarga anterior.

El clima usa la condición del modelo meteorológico, día/noche, nubosidad, velocidad y dirección del viento y la hora de la consulta. Se distinguen cielo despejado, nubosidad parcial, cielo cubierto, lluvia, tormenta, nieve y niebla. La probabilidad diaria de lluvia no activa lluvia actual. Los datos incompletos se muestran como no disponibles; los campos opcionales ausentes permanecen desconocidos. La consulta funciona con datos móviles y se actualiza cada 15 minutos mientras la pantalla está enfocada.

El barro, nieve/hielo, agua alta o rocas/derrumbe destacados sobre el trazado provienen de reportes recientes y mantienen su ubicación aproximada. Son zonas reportadas de precaución: no representan un relevamiento de la cobertura del suelo ni se infieren automáticamente del clima. Las advertencias siguen siendo consultables sobre el mapa.

## Precisión y fuentes

- La vista 3D usa [Mapzen Terrain Tiles en AWS](https://registry.opendata.aws/terrain-tiles/), un DEM público compuesto de fuentes reales como SRTM/GMTED2010 (USGS) y ETOPO1 (NOAA). Se decodifica la altura numérica del [formato Terrarium](https://github.com/tilezen/joerd/blob/master/docs/formats.md), no el color de una fotografía. Se mantiene un límite conservador de detalle de al menos 90 m, ampliado si el tamaño de la grilla o el zoom del mosaico es más grueso. No permite dibujar con certeza piedras, pozos, vegetación individual o microrelieve.
- Los perfiles y las grillas antiguas de [Open-Meteo / Copernicus GLO-90](https://open-meteo.com/en/docs/elevation-api) siguen siendo compatibles y conservan sus créditos. El mapa muestra la atribución de la fuente que realmente se cargó.
- La fotografía usa Esri World Imagery y respeta la proporción del área solicitada según [Export Map](https://developers.arcgis.com/rest/services-reference/enterprise/export-map/).
- El clima es una representación del [modelo meteorológico de Open-Meteo](https://open-meteo.com/en/docs), no una observación del suelo en cada punto del sendero.

Los campos nuevos de clima requieren actualizar el backend junto con la app. Con un servidor anterior, los campos opcionales no se inventan. Los mapas básicos descargados siguen siendo 2D y no descargan nuevas imágenes satelitales ni relieve 3D.

## Verificación

Las pruebas cubren interpolación y límites de la malla, curvas de nivel, distancia acumulada, escala ante cambios de cámara, encuadre completo, registro de imagen, selección de puntos, advertencias, suelo reportado, clima, API y compatibilidad con grillas anteriores. También se verifica TypeScript.

El 10/11/2026 se reprodujo un HTTP 429 de Open-Meteo al cargar una ruta extensa: la consulta sumaba las muestras del perfil y hasta 1089 coordenadas de la grilla. El 3D ahora descarga mosaicos de alturas sin consultar esa API punto por punto ni reducir la grilla. Las pruebas nuevas verifican la decodificación numérica del PNG, orientación geográfica, deduplicación, límite de concurrencia, recuperación tras fallos y timeout; los datos corruptos o ausentes nunca se sustituyen por un terreno plano.

Se comprobó con descargas reales la grilla y la construcción del modelo de las 51 geometrías de los catálogos del repositorio: 93 mosaicos descargados y cero fallos. También pasaron las 595 pruebas del frontend, TypeScript y la exportación de iOS. Esto verifica los datos y el empaquetado, sin sustituir una prueba visual en el teléfono.

La validación visual de GPU y la prueba en teléfono físico quedan pendientes: el host de navegador de pruebas no estuvo disponible en esta sesión.
