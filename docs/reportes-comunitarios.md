# Reportes comunitarios y sectores afectados

El reporte pide elegir el incidente, si se puede pasar y cuándo se observó. No supone una causa ni un nivel de riesgo. La causa y el texto son opcionales. La primera ubicación GPS válida queda fija mientras se completa el formulario; se puede actualizar expresamente o elegir el lugar sobre el mapa.

Se puede señalar un punto o los dos extremos de un sector. Los extremos se validan contra el recorrido real en el cliente y en el servidor. Los mapas 2D y 3D resaltan el sector siguiendo las curvas del trazado.

## Referencia y adaptación

Se tomó como referencia el [reporte de peligros de Waze](https://support.google.com/waze/answer/13739290?hl=en): captura de ubicación al reportar, respuestas sobre un aviso existente y vigencia influida por observaciones posteriores. Las reglas siguientes son propias de MiSendero; no reproducen un algoritmo de Waze.

- Una cuenta mantiene una respuesta actual por aviso: «Sigue igual», «Ya no está» o «No pude verificar». Una nueva visita puede renovar la misma respuesta; no suma otra persona.
- Una respuesta «Ya no está» de otra cuenta deja el aviso en disputa y visible. Dos cuentas distintas con observaciones posteriores a la última presencia confirmada lo resuelven. El autor puede resolver su propio reporte.
- Una observación positiva posterior vuelve a activar un reporte resuelto. «No pude verificar» no borra la última observación positiva ni prolonga por sí sola su vigencia.
- La vigencia parte de la observación original o de la última presencia confirmada, la más reciente, y usa `REPORT_STALE_AFTER_DAYS` (30 días por defecto). Los reportes vencidos se filtran y se eliminan con la limpieza existente.
- Los reintentos de una respuesta antigua no reemplazan una respuesta posterior. Las respuestas usan la cola existente por cuenta, también sin conexión. Se conservó el flujo existente de guardado y publicación.

## Recorrido y duplicados

Al crear un reporte se sugieren avisos activos cercanos de la misma categoría. Se puede actualizar uno o indicar expresamente que se trata de otro incidente. Los reportes anteriores sin progreso sobre la ruta se comparan por cercanía geográfica.

Durante un recorrido activo se muestra el aviso más próximo dentro de unos 500 m siguiendo el sendero, con margen por la ubicación aproximada. Se considera el sentido de avance y las apariciones del mismo lugar en una ruta de ida y vuelta. Un aviso de riesgo alto o paso bloqueado vibra una vez por encuentro y sentido; la simulación no vibra. Se puede abrir el detalle o descartar el aviso. No se muestra al pausar, fuera del sendero o con precisión GPS insuficiente. Los avisos resueltos dejan de generar advertencias y siguen consultables en la lista de reportes recientes.

## Datos y puesta en servicio

La migración `015_report_community_and_sections.sql` agrega los extremos de sectores y `report_feedback`, con una respuesta por reporte y cuenta y borrado en cascada. Se aplica con el comando habitual de migraciones del backend antes de servir la nueva versión.

La vista pública conserva la minimización existente: coordenadas a tres decimales, progreso a 100 m y horas redondeadas. No expone identidades de quienes responden ni texto privado. Los nuevos datos se incluyen en la exportación de la propia cuenta y se eliminan con ella. El servidor autentica las respuestas, respeta bloqueos y moderación y aplica el límite existente de acciones sobre reportes.
