# Registro de ejecuciones

El informe utiliza las ejecuciones **final-seed-20261017** y **final-seed-73**. Cada fila representa una ejecución del mismo conjunto; sus cantidades no se suman como casos distintos.

| Directorio | Casos aprobados / fallidos | Uso y observación |
|---|---:|---|
| `seed-20261017` | 482 / 1 | Diagnóstico de entorno: los tipos de Node del backend diferían del lockfile y faltaba su instalación local de TypeScript. El control de cobertura retornó 1 por el entorno; el resultado de la sonda también fue 1. |
| `locked-seed-20261017` | 482 / 1 | Ejecución con dependencias ajustadas al lockfile y arnés de preparación con su límite inicial de ejecución. |
| `locked-seed-73` | 479 / 4 | La primera pantalla de preparación agotó los 5 segundos del arnés; dos casos posteriores fallaron al acceder a un renderer desmontado. El cuarto fallo corresponde a MF07. Se conservan resultados y comparación fallida. |
| `final-seed-20261017` | **482 / 1** | Entorno fijado y presupuesto de inicialización de la suite de preparación de 30 segundos, con desmontaje al finalizar cada caso. Único fallo: MF07. |
| `final-seed-73` | **482 / 1** | Repetición final con otro orden. Único fallo: MF07. |

El caso de preparación que agotó el presupuesto inicial completó luego sus aserciones en aproximadamente 7,1 segundos en el control aislado instrumentado. El presupuesto de inicialización pertenece al arnés: no se modificaron sus expectativas funcionales ni se utilizó ese tiempo para acreditar latencia de la aplicación. La limpieza al finalizar cada caso conserva el aislamiento del renderer.

La [verificación final](repeat-verification.txt) aprobó la comparación de resultados individuales, contadores de líneas/sentencias/ramas/funciones y hashes de fuentes de las dos ejecuciones finales. El fallo de producto permanece explícito: repetir una observación crea dos reportes remotos en lugar de uno.

Los directorios de diagnóstico conservan sus propios manifiestos. Sus fuentes corresponden a los datos y al arnés registrados en cada ejecución; no se presentan como ejecuciones de los archivos finales. La [comparación que detectó el problema del arnés](repeat-verification-harness-failure.txt) se conserva junto con los resultados originales.
