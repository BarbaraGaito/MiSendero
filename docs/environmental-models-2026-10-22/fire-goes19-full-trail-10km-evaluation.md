# GOES G19: sensibilidad espacial a 10 km de la polilínea completa

Se reusaron los cinco clasificadores congelados y el corte temporal original (validación diciembre de 2025; test enero de 2026), contando solo píxeles muestreados a ≤10 km de las polilíneas completas. No se reentrenó ni calibró ningún modelo.

| Horizonte | Píxeles núcleo | Horas ruta train | Positivos GOES train | Horas ruta val. | Positivos GOES val. | Umbral validado | Horas ruta test | Positivos GOES test | Avisos test (0,5 diag.) |
|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 1 | 116 | 6618 | 15 | 3351 | 0 | no; mejor 0/5 (0.0%) | 4170 | 0 | 0 |
| 2 | 116 | 6387 | 14 | 3221 | 0 | no; mejor 0/3221 (0.0%) | 4053 | 0 | 0 |
| 3 | 116 | 6205 | 14 | 3125 | 0 | no; mejor 0/3125 (0.0%) | 4005 | 0 | 0 |
| 6 | 116 | 5794 | 13 | 2991 | 0 | no; mejor 0/2991 (0.0%) | 3854 | 0 | 0 |
| 12 | 116 | 5302 | 10 | 2814 | 0 | no; mejor 0/5 (0.0%) | 3725 | 0 | 0 |

El objetivo es una detección GOES en el corredor cercano al recorrido, no un incendio físico confirmado. Un umbral se selecciona solo si supera la puerta de validación; si ninguno la supera, los conteos a 0,5 son diagnósticos. Los píxeles desconocidos no se convierten en negativos.

Las ocho polilíneas tienen 116 píxeles muestreados dentro de 10 km (por ruta: {"Bosque Tallado desde la plataforma del Piltriquitron": 11, "Cerro Ventana - Hueco de la Ventana": 14, "Quebrada del Condorito - Balcon Norte": 18, "Refugio Frey desde Villa Catedral": 18, "Sendero Che Roga - Mburucuyá": 16, "Sendero La Chuña - El Rey": 18, "Sendero Macuco - Salto Arrechea": 9, "Sendero Namuncura": 12}).

La ausencia de etiquetas GOES cercanas no demuestra ausencia de incendio. Durante el test, el SNMF registró Barda de La Loma (CONTROLADO), a 5.939 km del recorrido. El auditor independiente encontró 13 píxeles GOES válidos pero score máximo 0 y ningún aviso del modelo. Es un caso preocupante de posible omisión de un evento reportado; el parte diario no fija la hora de ignición. [Detalle del cruce SNMF](goes19-snmf-2026-jan-event-audit.json).

La comparación evalúa transferencia espacial de modelos entrenados con sectores más amplios. Incluso si mejora frente al análisis sectorial, no mide probabilidad de incendio ni justifica una alerta de seguridad; para eso siguen faltando observaciones independientes completas, incluidas ventanas sin incendio verificadas y tiempo de publicación del dato.

Criterios, datos por horizonte y hashes: [JSON reproducible](fire-goes19-full-trail-10km-evaluation.json). Reproducción: [`evaluate_goes_hourly_full_trail_radius.py`](../../training/python/evaluate_goes_hourly_full_trail_radius.py). Evaluación sectorial previa: [informe](fire-goes19-short-lead-route-sector-evaluation.md).
