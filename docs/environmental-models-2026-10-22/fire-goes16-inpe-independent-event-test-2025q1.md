# Contraste externo de horizontes GOES-16 vs. focos INPE, marzo de 2025

Se aplicaron los modelos GOES-16 congelados de 1, 2, 3, 6 y 12 horas, sin reentrenarlos, al test temporal de marzo de 2025. Los resultados se contrastaron con el archivo anual abierto del satélite de referencia del [Programa Queimadas del INPE](https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/anual/AMS_sat_ref/), una fuente de detecciones distinta de las escenas GOES usadas para el ajuste.

En ese test hubo un día-sector con foco INPE a menos de 10 km del centro de un sendero: Che Roga–Mburucuyá, el 20/03/2025 a las 18:49 UTC, a 9,58 km del centro. Las cinco emisiones GOES disponibles (de 1 a 12 horas) predijeron la escena de las 19:00, cuyo inicio quedó a 11 minutos de la hora del foco INPE. Ningún horizonte alertó con el corte diagnóstico fijo 0,5, ni tampoco la persistencia. En esa escena GOES, dentro del buffer de 10 km había 13 píxeles válidos clasificados sin fuego y uno desconocido; no había píxeles positivos. A menos de 5 km del foco INPE, los tres píxeles GOES válidos también estaban etiquetados sin fuego.

| Anticipo | Score máximo en 10 km | Score máximo a 5 km del foco | Alerta a 0,5 |
|---:|---:|---:|---:|
| 1 h | 0,000238 | 0,000223 | No |
| 2 h | 0,000189 | 0,000178 | No |
| 3 h | 0,0000064 | 0,0000060 | No |
| 6 h | 0,0000000028 | 0,0000000026 | No |
| 12 h | 0,000000083 | 0,000000080 | No |

Para el objetivo de detectar fuego real cerca del sendero, el modelo no dio aviso ante el foco INPE independiente. La escena GOES objetivo también quedó negativa en los píxeles evaluables, lo que muestra que el modelo aprende a pronosticar la máscara GOES, no necesariamente la ocurrencia física detectada por otro sensor. Este único caso no cuantifica sensibilidad general, y como el archivo INPE aporta positivos sin negativos observados no permite estimar precisión. La hora del foco satelital no equivale a hora de ignición, y el score GOES no está calibrado como probabilidad.

El [JSON con hashes, cobertura espacial y temporal](fire-goes16-inpe-independent-route-event-test-2025q1.json) se reproduce con [`evaluate_goes16_inpe_reference_route_events.py`](../../training/python/evaluate_goes16_inpe_reference_route_events.py). El informe congelado GOES ya mostraba que su test de marzo tenía AP de 0,075 frente a 0,222 de persistencia a una hora y Brier 0,00645 frente a 0,000012; el cruce externo confirma que ninguno de los cinco horizontes alertó en el foco cercano evaluable.
