# Auditoría del recomendador personalizado

Informe histórico del experimento de ranking por valoraciones, retirado del flujo de la API. El recomendador actual usa [reglas sobre datos del catálogo](../trail-recommendation.md), sin etiquetas de relevancia ni modelo por opiniones. Las cifras y políticas de este directorio describen snapshots anteriores.

La revisión histórica posterior está en [POLICY-V4.md](POLICY-V4.md): 51 fichas utilizables con sus límites de documentación y cero etiquetas reales de relevancia. El informe original que sigue describe el snapshot inicial.

Revisión local del 17/10/2026. No se consultó ni modificó RDS.

| Dato observado | Cantidad |
|---|---:|
| Senderos en PostgreSQL local | 52 |
| Con fuentes en provenance | 42 |
| Elegibles por las validaciones actuales | 35 |
| Excluidos por documentación, duración o campos faltantes | 17 |
| Elegibles con terreno estructurado documentado | 2 |
| Elegibles con referencia de ascenso disponible | 15 |
| Tablas de preferencias/relevancia/recomendaciones | 0 |
| Pares encuesta–sendero etiquetados preparados | 0 |

Las cantidades son una observación, no constantes del código. El snapshot está en `training/data/trail-ranking/catalog.json`; el exportador lee todos los registros actuales. Las 15 referencias de ascenso provienen de información de elevación ya disponible en la aplicación y pueden ser aproximaciones DEM, no mediciones de campo.

Se revisaron el backend Express, `db.js`, migraciones de `trails`, procedencia y elevación, seeds del catálogo, tablas de actividades y privacidad, los datasets públicos ya existentes, el servicio de recomendaciones y la encuesta Expo. No se encontró una colección de elecciones con preferencias, exposición de candidatos y consentimiento que permita construir etiquetas supervisadas del recomendador. Una actividad completada o la dificultad publicada de una ruta no prueba que sea la mejor coincidencia para una encuesta.

El intento reproducible de entrenamiento con los datos reales disponibles está en [training-status.json](training-status.json): **no entrenado, datos insuficientes, métricas nulas**. No hay un modelo personalizado que pueda anunciarse como validado. La app funciona con el baseline mientras se realiza un estudio de relevancia.

## Datos públicos de Internet

Conviene reutilizar fuentes externas para atributos o tareas que efectivamente etiquetan, no mezclar tareas para obtener métricas aparentes:

| Fuente | Uso adecuado | Decisión para el ranking personalizado |
|---|---|---|
| [APN](https://www.argentina.gob.ar/parquesnacionales), fichas oficiales | Existencia, ubicación, duración, dificultad y paisajes documentados | Ya fundamenta gran parte del catálogo. No contiene decisiones personales de la encuesta. |
| [OpenStreetMap](https://www.openstreetmap.org/copyright), ODbL | Trazas/atributos cartográficos con procedencia, revisión y atribución | El proyecto ya conserva snapshots para otra tarea de dificultad. No transformar `sac_scale` en preferencia o satisfacción. |
| Dataset APN de dificultad ya versionado en `training/data/public/apn_route_difficulty/` | Entrenar/evaluar la clasificación de dificultad publicada | Mantener separado del recomendador. Sus métricas no son precisión de recomendaciones. |
| [UCI Travel Reviews](https://www.archive.ics.uci.edu/dataset/484/travel%2Breviews), CC BY 4.0 según su ficha | Estudiar valoraciones agregadas de diez categorías turísticas en Asia Oriental | Descartado para este objetivo: no aporta pares de encuesta–sendero con duración, dificultad y experiencia. No se descargó ni se mezcló para aumentar filas. |
| Estudios públicos de trekking con valoraciones y características compatibles | Posible dataset externo de relevancia | No se identificó uno adecuado en esta revisión. Antes de incorporarlo verificar licencia, procedencia, privacidad, significado de etiquetas y correspondencia de atributos. |

Las fuentes y archivos públicos usados anteriormente por otros modelos ya están fijados en `training/data/public/source_catalog.json`, `sources.lock.json` y sus manifiestos de procedencia. No se modificaron esos modelos ni se mezclaron sus etiquetas fisiológicas/de dificultad con relevancia personalizada.

No cargar binarios de modelos descargados, reutilizar reseñas sin procedencia, inventar experiencia de usuarios ni asignar preferencias aleatorias para presentar un entrenamiento como real. La evaluación experta consentida de las opciones del catálogo es una primera opción razonable para la tesis, declarando sus límites; después puede compararse con valoraciones de usuarios reales.

La app solo recomienda IDs existentes en PostgreSQL aunque se investiguen fuentes externas. Un dataset público no puede introducir automáticamente rutas, coordenadas o estados de seguridad en las respuestas. La preparación actual exige correspondencia explícita con el catálogo y evaluaciones completas; una nueva fuente de relevancia necesitará un adaptador revisado antes de utilizarse.

## Reproducir

Desde la raíz, con PostgreSQL local configurado:

```powershell
npm --prefix backend run ranking:prepare
py backend/ml/train.py --catalog training/data/trail-ranking/catalog.json --prepared training/data/trail-ranking/prepared --output backend/ml/artifacts/otra-version-auditoria
```

El segundo comando debe informar insuficiencia y terminar sin modelo mientras no se incorporen etiquetas reales. No ejecutar seeds ni migraciones para esta preparación. El diseño, escala de etiquetas, partición, mínimos, métricas, limitaciones y reglas de activación están en [backend/ml/README.md](../../backend/ml/README.md).

## Comprobación de la implementación

- Backend: 19 suites, **185 pruebas aprobadas**, incluidas autenticación, rate limiting, catálogo real de las fixtures, cinco respuestas, filtros, fallas/protocolo del worker y fallback.
- App/servicios: 46 suites, **332 pruebas aprobadas**, incluidas encuesta completa, destinos cubiertos, experiencia, edición, resultado único y modo offline.
- Python: **7 pruebas técnicas**, con ajuste real de scikit-learn sobre fixtures explícitamente sintéticas, particiones, métricas de valores conocidos, hash/versiones, rechazo en producción e inferencia privada. No son evidencia de precisión de recomendaciones reales.
- Compilación backend y TypeScript de la aplicación aprobadas.
- `ranking:smoke` contra HTTP y PostgreSQL local real devolvió 200, método `baseline` y un ID cuyo nombre, duración y distancia coincidieron con el registro SQL. La prueba informó **0 escrituras**, con 73 opciones de destino en ese snapshot. No inició cron, migraciones o seed.
- No se probó en un dispositivo físico ni en EC2/RDS; quedaron instrucciones de prueba manual y reversión. La imagen Docker opcional con Python no se construyó durante esta revisión.

El ajuste sintético ocurre únicamente en temporales y se identifica como técnico/no desplegable. El entrenamiento del catálogo real sigue con **0 etiquetas, 0 modelos entrenados para este recomendador y métricas nulas**.
