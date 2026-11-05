# Verificación ejecutada el 22/10/2026

Los resultados científicos y los resultados de pruebas de software se registran por separado.

## Experimentos con observaciones reales

| Comando | Resultado observado |
|---|---|
| Exportador de geografía | Tres regiones reales del catálogo, con coordenadas, fuentes y hash |
| `environmental_sources.py` | Tres series INA, 68.769 observaciones originales/admitidas |
| `audit_environmental_access.py` | Colección CMR v61 y tres metadatos por región; catálogo ORNL sin producto diario requerido |
| `train:environmental:river` | Seis comparaciones con cuatro candidatos y selección por validación |
| `validate:environmental` | Seis experimentos y 17.276 filas de prueba verificadas contra originales; MAE/RMSE recalculados |
| `predict:environmental` | Seis artefactos registrados, dos estimaciones numéricas de estación en esa ejecución, cero asociaciones de ruta |
| Exportador de snapshots Node | Cero lotes de ruta preparados; cero escrituras en base |

La última corrida científica exige también disponibilidad de las etiquetas antes de los cortes de entrenamiento y validación. El hash del informe evaluado y los hashes del código están en `results-audit.json`. No se adquirieron píxeles MODIS ni etiquetas negativas válidas de fuego; esos entrenamientos no se contabilizan como éxitos.

## Pruebas de software

| Comando | Resultado |
|---|---|
| `npm.cmd run typecheck` | Sin errores |
| `npm.cmd --prefix backend run build` | Sin errores |
| `npm.cmd test -- --runInBand` | 62 suites, 520 pruebas aprobadas |
| `npm.cmd --prefix backend test -- --runInBand` | 27 suites, 248 pruebas aprobadas |
| `npm.cmd run test:environmental:data` | Siete pruebas de causalidad, calidad y preservación de originales aprobadas |
| `npm.cmd run test:ai-data` | 32 pruebas aprobadas; incluye recomputación de evidencia de los cuatro modelos previos |
| Tests de caché y componente ambiental tras reforzar el contrato | Dos suites, seis pruebas aprobadas |
| `expo export --platform web` | Exportación local completada, 1.194 módulos; sin publicación |
| `git diff --check` | Sin errores de espacios en los archivos versionados modificados |

El primer intento de exportación Expo se detuvo porque el proyecto exige una URL HTTPS en distribución. Se repitió únicamente para compilar con `EXPO_PUBLIC_API_URL=https://example.invalid/api` en el entorno del proceso; no se guardó esa URL en configuración ni se probó un servidor con ella. El resultado está en `.expo-export-environmental-check`, ignorado por Git.

En la primera ejecución de tests se detectaron un manejo de timestamp nulo, una suscripción de red sin `remove` en los mocks y una expectativa de caché ausente (`null`). Se corrigieron y se ejecutaron nuevamente las suites afectadas y las suites completas indicadas arriba. No quedaron fallos reproducibles. Un timeout inicial de pantalla de catálogo no reapareció en su ejecución aislada ni en la segunda suite completa.

La cobertura nueva incluye importación transaccional/idempotente en PostgreSQL simulado, asociación revisada o revocada, geometría faltante/cambiada, artefactos inhabilitados, fechas futuras y horizonte inválido, integridad de lote, SQLite real en memoria, aislamiento por cuenta, fallos de proveedor, pérdida/recuperación de conexión, lectura sin red y vencimiento durante la visualización. Los tests existentes de mosaicos incompletos, GPS, sesiones y SOS también aprobaron.

No se ejecutó SonarQube remoto, build Android/iOS, migración en PostgreSQL real, despliegue, envío de mensajes, salida de campo ni validación en dispositivo físico. Los tests utilizan fixtures de software identificados expresamente; sus valores no figuran como evidencia del entrenamiento. La compilación y los tests no aprueban clínicamente fatiga/AMS ni establecen seguridad de tránsito.
