# Cobertura de FireComp cerca de rutas argentinas

## Resultado del filtro de cobertura

FireComp ofrece un benchmark público de propagación diaria basado en VIIRS a 375 m. La tarea parte del fuego detectado el día T y pronostica su extensión o los píxeles nuevos al día T+1; por eso evalúa **propagación con un incendio ya activo**, no ignición. El conjunto tiene unas 130.649 muestras y un tamaño publicado de 212 GB; sus ocho shards principales ocupan aproximadamente 19–20 GB cada uno. [Repositorio y protocolo](https://github.com/justuskarlsson/FireComp) · [ficha del conjunto](https://huggingface.co/datasets/justuskarlsson/FireComp)

Se revisaron los metadatos de su partición pública de prueba sin descargar los HDF5. De 32.665 muestras de test, 3.738 pertenecen a Sudamérica y 139 caen dentro de un rectángulo geográfico amplio que contiene Argentina. Al comparar los centros de muestra con 51 trazas de rutas argentinas del repositorio, solo **tres filas** quedaron a menos de 70 km de una ruta: un ID de fuego cada una, en Aconquija–El Pozón (41,3 km), Laguna Tesoro (55,0 km) y Tabaquillo (62,3 km). Las fechas son 2024-09-06, 2024-08-09 y 2024-10-04.

El radio de 70 km es un filtro preliminar, comparable con la diagonal de un parche de 256×256 celdas de 375 m; no confirma que el raster de la muestra cruce el sendero. Los tres casos están en el split de test, pero son demasiados pocos eventos para estimar precisión fiable o defender transferencia a la Argentina. Tampoco hay evidencia de que el benchmark incluya completos los incendios menores ni una referencia exhaustiva de días sin fuego.

**Decisión:** no descargar los shards de decenas de GB ni entrenar FireComp con estos datos. El resultado es insuficiente para la evaluación local; sí queda como referencia para una futura función distinta: anticipar expansión de un fuego ya detectado, no predecir que se iniciará fuego en una ruta.

## Reproducción y entradas

La auditoría se reproduce descargando primero solo índices públicos JSON/JSONL y ejecutando el filtro local:

```powershell
.venv-ai\Scripts\python.exe training/python/acquire_firecomp_coverage_metadata.py
.venv-ai\Scripts\python.exe training/python/audit_firecomp_argentina_coverage.py
```

El auditor genera las geometrías desde las trazas vigentes del repositorio. El conteo completo está en [`fire-firecomp-argentina-route-coverage.json`](fire-firecomp-argentina-route-coverage.json). No se descargaron los ocho archivos HDF5, no se ejecutó el modelo y no se modificó ningún artefacto de producción.
