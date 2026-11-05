# Comparación de calibración del proxy SNMF

## Resultado

Se comparó la regresión logística ponderada por clase que venía usando el experimento con la misma regresión sin ponderación. La selección se hizo por average precision y Brier en diciembre de 2025; enero de 2026 quedó reservado como test. El objetivo continúa siendo coincidir con un incidente listado por SNMF a 10 km del sector, no predecir una ignición confirmada.

| Pronóstico | Variante seleccionada | Average precision de test | Brier de test | Avisos al corte diagnóstico 0,5 |
|---|---|---:|---:|---:|
| GFS | Sin ponderar | 0,137 (prevalencia: 0,129) | 0,127 (baseline constante: 0,127) | 0/240; recall 0 % |
| JMA GSM | Sin ponderar | 0,120 (prevalencia: 0,129) | 0,127 (baseline constante: 0,127) | 0/240; recall 0 % |

La variante ponderada sí produjo avisos, pero su calibración fue peor y las evaluaciones anteriores no encontraron un umbral aceptable en validación. La variante sin ponderación reduce el Brier a casi el baseline porque asigna puntuaciones bajas a casi todos los días; no aprendió a encontrar los días positivos. En ambos modelos, diciembre solo tenía cuatro días-sector positivos y ningún umbral cumplió el requisito de 80 % de precisión proxy con al menos cinco avisos. El test de enero tiene seis inicios independientes cerca de sectores, no 31 observaciones independientes.

**Conclusión:** cambiar la ponderación no mejora la capacidad de emitir alertas fiables. No se selecciona ningún umbral, no se presenta el score como probabilidad y no se habilita el candidato en la app.

## Reproducción

Desde la raíz del repositorio:

```powershell
.venv-ai\Scripts\python.exe training/python/compare_snmf_report_proxy_class_weight.py --weather-model gfs
.venv-ai\Scripts\python.exe training/python/compare_snmf_report_proxy_class_weight.py --weather-model jma_gsm
```

Los resultados completos y hashes de entradas están en [`fire-gfs-snmf-class-weight-comparison-2026-jan.json`](fire-gfs-snmf-class-weight-comparison-2026-jan.json) y [`fire-jma_gsm-snmf-class-weight-comparison-2026-jan.json`](fire-jma_gsm-snmf-class-weight-comparison-2026-jan.json). El script reutiliza los pronósticos archivados y las etiquetas oficiales; no crea observaciones sintéticas ni cambia el artefacto productivo.

## Límite de la afirmación

Los días sin incidente próximo en un parte no prueban ausencia física de fuego. Esta comparación sirve para descartar una decisión de entrenamiento con el proxy disponible; no demuestra precisión en incendios reales. Para una afirmación de precisión fiable todavía se requiere una cohorte de alertas independientes con positivos y ventanas sin fuego observadas, más una temporada intacta de prueba.
