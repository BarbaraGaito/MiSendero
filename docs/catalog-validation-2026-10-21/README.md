# Validación del recomendador por datos esenciales

Se revisaron los diez registros iniciales sin procedencia estructurada, se recuperaron observaciones reales del modelo de elevación para once trazas completas y se prepararon doce escenarios de conformidad funcional. Los cambios están en archivos del repositorio; no se modificó RDS ni se publicó un backend o APK.

## Qué se completó y qué sigue pendiente

| Comprobación sobre las 51 fichas del repositorio | Resultado |
| --- | ---: |
| Fichas con alguna fuente documentada | 51 |
| Fichas con verificación parcial de atributos | 9 |
| Fichas cuyo tiempo total sigue sin confirmar | 9 |
| Referencias previas de ascenso conservadas del export local | 32 |
| Perfiles nuevos con muestras DEM guardadas y recalculables | 11 |
| Fichas sin referencia de ascenso, por traza parcial | 8 |
| Escenarios funcionales definidos y comprobados | 12 |

Las filas se superponen: no son grupos que deban sumarse. Una fuente que solo confirma el destino no convierte en verificados la distancia, duración o dificultad. `catalogVerification: partial` y los avisos conservan esa diferencia. Las referencias anteriores de ascenso proceden del export local del 18/10; no se presentan como perfiles recién descargados ni como mediciones de campo.

La revisión tiene dos confirmaciones de duración completa: Lahuán Solitario, documentado por APN como 90 minutos de ida y vuelta, y Cerro Morado, cuyo administrador publica tres horas para el recorrido incluida la permanencia en cumbre. En Cerro Morado no se deduce una forma circular a partir de la palabra circuito.

En Confluencia las fuentes oficiales consultadas publican intervalos diferentes, 4–5 y 6–8 horas. La ficha conserva el valor anterior, marcado como pendiente, sin contar como coincidencia exacta de tiempo. En Laguna del Tesoro se corrigió Alta a Media según la dificultad intermedia publicada; las seis horas de ida no certifican las 10–12 horas totales del catálogo. El detalle por campo, el razonamiento y los enlaces se conservan en [la revisión de fuentes](../../backend/src/data/reviewedTrailFacts20261021.json).

## Evidencia y reproducción

```powershell
npm.cmd --prefix backend run catalog:validate
```

El comando compila el código y comprueba datos publicados, destino, intervalos, dificultades, avisos y tratamiento de faltantes. No consulta la red ni la base de datos. Reconstruye las fichas desde las definiciones del repositorio y utiliza sus IDs reales del export previo. Genera [results.json](results.json), con preferencias de cada escenario, resultado, fuentes, pendientes y hashes SHA-256 de entradas/código. Si una comprobación falla, termina con error.

Las doce búsquedas son casos de prueba declarados, no consultas observadas de personas ni etiquetas para entrenamiento. Su cumplimiento no es accuracy de un modelo, satisfacción de usuarios ni evidencia de seguridad. Los escenarios de requisitos puramente funcionales, como no cambiar de ciudad ante un error de escritura, se distinguen de los que contrastan cifras publicadas.

Las estimaciones nuevas de elevación se encuentran en [el archivo de perfiles](../../backend/src/data/recommendationElevation20261021.json). Se guardan fecha, fuente, hash de geometría y las 874 muestras recibidas de Copernicus DEM GLO-90 mediante Open-Meteo. El validador reproduce la ubicación de cada muestra y el cálculo de ascenso/descenso, y comprueba que todas las trazas incorporadas estén documentadas como completas. Una geometría o un nombre diferente invalida su reutilización.

El muestreo utiliza la lógica existente: separación objetivo de 90 metros, hasta 500 puntos por traza, extremos incluidos y umbral de 5 metros para acumular cambios. Esos parámetros son decisiones del cálculo; no equivalen a precisión de 5 metros ni a validación de campo. La fuente tiene resolución aproximada de 90 metros: [documentación del proveedor](https://open-meteo.com/en/docs/elevation-api), DOI del conjunto [10.5270/ESA-c5d3d65](https://doi.org/10.5270/ESA-c5d3d65). La app los identifica como estimaciones sobre la traza disponible.

Para reintentar únicamente la obtención de perfiles de las trazas completas, sin acceder a una base:

```powershell
npm.cmd --prefix backend run catalog:elevation:refresh
```

El script reutiliza perfiles de la misma geometría. No inventa elevaciones cuando falla el proveedor. El archivo fijo es evidencia versionada; para actualizar una campaña de datos conviene conservar una nueva revisión. Las ocho trazas parciales permanecen excluidas de este cálculo y están enumeradas en `pendingElevation` del informe.

## Integración sin publicación

El seed consume las definiciones revisadas, sin cambiar IDs ni agregar observaciones humanas. No se ejecutó sobre la base configurada: esta apunta a RDS y publicar/aplicar allí quedó expresamente fuera del alcance pedido. El endpoint puede usar los perfiles DEM incluidos solo cuando coinciden clave, nombre y hash de la geometría; si existe un perfil válido en la base, conserva su prioridad. Las fichas remotas requieren su futura actualización explícita para recibir la nueva revisión de atributos.

La justificación de las reglas y los límites para la tesis se encuentran en [fundamento y alcance](fundamento-tesis.md). Los modelos de fatiga, AMS y dificultad OSM/APN conservan su evaluación independiente.
