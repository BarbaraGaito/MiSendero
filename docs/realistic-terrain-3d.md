# Vista 3D del terreno

La vista ofrece **Imagen**, con fotografía satelital de referencia, y **Relieve**, con color por altitud y curvas de nivel. Ambas conservan el mismo trazado y las alturas reales, sin exageración vertical.

El recorrido se apoya en la superficie de alturas, incluidos sus bordes. Las flechas muestran el sentido del trazado; las etiquetas agregan distancia acumulada y altitud aproximada. El encuadre inicial incluye la ruta completa según la proporción de pantalla. La escala se calcula sobre el terreno visible en el centro y se actualiza al mover la cámara; la flecha norte sigue la orientación geográfica.

Se consultan entre 17 × 17 y 33 × 33 muestras reales según la extensión de la ruta, con una malla de renderizado limitada a 65 × 65 vértices. La interpolación facilita la visualización, pero no agrega precisión geográfica. Los mapas antiguos siguen siendo legibles; las grillas menos detalladas se pueden actualizar al abrir el 3D con conexión, conservando la copia anterior si falla la consulta.

La imagen satelital usa hasta 2048 píxeles por lado, con proporción geográfica consistente con el área consultada para evitar desplazamientos entre foto, recorrido y relieve. Incluye filtrado y sombras del terreno. La imagen es histórica, no una cámara en vivo.

El clima usa la condición del modelo meteorológico, día/noche, nubosidad, velocidad y dirección del viento y la hora de la consulta. Se distinguen cielo despejado, nubosidad parcial, cielo cubierto, lluvia, tormenta, nieve y niebla. La probabilidad diaria de lluvia no activa lluvia actual. Los datos incompletos se muestran como no disponibles; los campos opcionales ausentes permanecen desconocidos. La consulta funciona con datos móviles y se actualiza cada 15 minutos mientras la pantalla está enfocada.

El barro, nieve/hielo, agua alta o rocas/derrumbe destacados sobre el trazado provienen de reportes recientes y mantienen su ubicación aproximada. Son zonas reportadas de precaución: no representan un relevamiento de la cobertura del suelo ni se infieren automáticamente del clima. Las advertencias siguen siendo consultables sobre el mapa.

## Precisión y fuentes

- La fuente de alturas es [Open-Meteo / Copernicus GLO-90](https://open-meteo.com/en/docs/elevation-api), de resolución nominal de 90 m. La separación de muestras puede ser mayor en rutas extensas; la interfaz muestra ese límite aproximado. No permite dibujar con certeza piedras, pozos, vegetación individual o microrelieve.
- La fotografía usa Esri World Imagery y respeta la proporción del área solicitada según [Export Map](https://developers.arcgis.com/rest/services-reference/enterprise/export-map/).
- El clima es una representación del [modelo meteorológico de Open-Meteo](https://open-meteo.com/en/docs), no una observación del suelo en cada punto del sendero.

Los campos nuevos de clima requieren actualizar el backend junto con la app. Con un servidor anterior, los campos opcionales no se inventan. Los mapas básicos descargados siguen siendo 2D y no descargan nuevas imágenes satelitales ni relieve 3D.

## Verificación

Las pruebas cubren interpolación y límites de la malla, curvas de nivel, distancia acumulada, escala ante cambios de cámara, encuadre completo, registro de imagen, selección de puntos, advertencias, suelo reportado, clima, API y compatibilidad con grillas anteriores. También se verifica TypeScript.

La validación visual de GPU y la prueba en teléfono físico quedan pendientes: el host de navegador de pruebas no estuvo disponible en esta sesión.
