# Verificación ejecutada el 22/10/2026

Los resultados científicos y los resultados de pruebas de software se registran por separado.

## Experimentos con observaciones reales

| Comando | Resultado observado |
|---|---|
| Exportador de geografía | Tres regiones reales del catálogo, con coordenadas, fuentes y hash |
| `environmental_sources.py` | Dos series INA activas, 37.533 observaciones originales/admitidas; 32926 excluida |
| `audit_environmental_access.py` | Colección CMR v61 y tres metadatos por región; catálogo ORNL sin producto diario requerido |
| Evaluación hidrométrica activa | Cuatro comparaciones conservadas con cuatro candidatos y selección por validación; la corrida previa se archivó |
| `validate:environmental` | Cuatro experimentos y 8.963 filas de prueba activas verificadas contra originales; MAE/RMSE recalculados |
| `fetch:environmental:fire` | 440 pares de máscara/QA, 880 originales; 2.204.981 registros de píxel/día muestreados antes de deduplicar |
| `train:environmental:fire` | Seis referencias/candidatos comparados; XGBoost seleccionado con validación; resultado insuficiente para uso |
| `validate:environmental:fire` | 880 hashes originales, joins, particiones y métricas de 530.925 predicciones de prueba verificados |
| `fetch:environmental:fire:recent` | 55 pares recientes, en archivos separados del experimento histórico |
| `predict:environmental` | Cuatro artefactos hidrométricos inhabilitados, cero números de estación; ocho diagnósticos privados de fuego con habilitación falsa; cero lotes de ruta |
| Exportador de snapshots Node | Cero lotes de ruta preparados; cero escrituras en base |

Las corridas científicas exigen también disponibilidad de etiquetas antes de los cortes de entrenamiento y validación. Los hashes e informes están en `results-audit.json` y `fire-results-audit.json`. No se adquirieron píxeles nivales; para fuego sí se adquirieron píxeles diarios y QA y se entrenó. El entrenamiento exitoso como ejecución no se presenta como éxito predictivo: el modelo seleccionado detectó 1/31 positivos temporales con 12.880 falsas alarmas y falló en los tres positivos geográficos.

## Pruebas de software

| Comando | Resultado |
|---|---|
| `npm.cmd run typecheck` | Sin errores |
| `npm.cmd --prefix backend run build` | Sin errores |
| `npm.cmd test -- --runInBand` | 62 suites, 520 pruebas aprobadas |
| `npm.cmd --prefix backend test -- --runInBand` | 27 suites, 249 pruebas aprobadas |
| `npm.cmd run test:environmental:data` | Siete pruebas de causalidad, calidad y preservación de originales aprobadas |
| `npm.cmd run test:environmental:fire` | Siete pruebas aprobadas de clases, QA, duplicados, particiones, disponibilidad y aprobación |
| `npm.cmd run test:ai-data` | 39 pruebas aprobadas; incluye recomputación de evidencia de los cuatro modelos previos |
| Tests de caché y componente ambiental tras reforzar el contrato | Dos suites, seis pruebas aprobadas |
| `expo export --platform web` | Exportación local completada, 1.194 módulos; sin publicación |
| `git diff --check` | Sin errores de espacios en los archivos versionados modificados |

El primer intento de exportación Expo se detuvo porque el proyecto exige una URL HTTPS en distribución. Se repitió únicamente para compilar con `EXPO_PUBLIC_API_URL=https://example.invalid/api` en el entorno del proceso; no se guardó esa URL en configuración ni se probó un servidor con ella. El resultado está en `.expo-export-environmental-check`, ignorado por Git.

En la primera ejecución de tests se detectaron un manejo de timestamp nulo, una suscripción de red sin `remove` en los mocks y una expectativa de caché ausente (`null`). Se corrigieron y se ejecutaron nuevamente las suites afectadas y las suites completas indicadas arriba. No quedaron fallos reproducibles. Un timeout inicial de pantalla de catálogo no reapareció en su ejecución aislada ni en la segunda suite completa.

La adquisición de fuego detectó capas diarias superpuestas al cambiar de año; se implementó deduplicación por máscara/QA con exclusión de conflictos. La auditoría numérica restaura el dtype float32 original de XGBoost al leer el CSV, y comprueba además la fórmula binaria directa de Brier con tolerancia de redondeo. No se alteraron las métricas para aprobar el modelo. La grilla inicial insuficiente y las revisiones de protocolo anteriores al ajuste están preservadas en `archive/`.

La cobertura nueva incluye importación transaccional/idempotente en PostgreSQL simulado, asociación revisada o revocada, geometría faltante/cambiada, artefactos inhabilitados, fechas futuras y horizonte inválido, integridad de lote, SQLite real en memoria, aislamiento por cuenta, fallos de proveedor, pérdida/recuperación de conexión, lectura sin red y vencimiento durante la visualización. Los tests existentes de mosaicos incompletos, GPS, sesiones y SOS también aprobaron.

No se ejecutó SonarQube remoto, build Android/iOS, migración en PostgreSQL real, despliegue, envío de mensajes, salida de campo ni validación en dispositivo físico. Los tests utilizan fixtures de software identificados expresamente; sus valores no figuran como evidencia del entrenamiento. La compilación y los tests no aprueban clínicamente fatiga/AMS ni establecen seguridad de tránsito.
