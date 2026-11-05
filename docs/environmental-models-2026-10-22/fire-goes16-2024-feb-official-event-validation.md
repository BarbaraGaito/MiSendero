# Auditoría oficial de episodios GOES-16 de febrero de 2024

## Resultado

Los dos perímetros GlobFire cercanos a los sectores de trekking corresponden a incendios reales reportados por el Sistema Federal de Manejo del Fuego (SNMF). El parte oficial del 5/2/2024 registra un incendio activo en Arroyo Creton, Río Negro, iniciado ese día, y el incendio del Parque Provincial Ernesto Tornquist, iniciado el 3/2 y extinguido el 5/2, con 300 ha informadas. El reporte mensual de febrero vuelve a listar ambos eventos. Esto aporta corroboración administrativa independiente del perímetro satelital para la existencia y fecha aproximada de los episodios.

Al contrastar la cohorte NOAA GOES-16 completa del 1 al 13 de febrero con GlobFire, el evento de Arroyo Creton/Brazo Tristeza tuvo una detección GOES de alta calidad a 0,806 km del perímetro el 5/2 a las 18:00 UTC, el mismo día de inicio reportado. Para Tornquist, el muestreo no encontró una detección de alta calidad en la ventana definida. El informe oficial de Río Negro indica que el incendio de Brazo Tristeza comenzó entre las 2 y las 4 de la madrugada del 5/2; por eso la detección vespertina es posterior al inicio, no una anticipación.

La superficie de GlobFire para Brazo Tristeza es 473 ha, mientras que una nota publicada el 1/3 informa alrededor de 650 ha acumuladas y el parte SNMF del 5/2 todavía no consigna superficie para Arroyo Creton. No se deben mezclar estas cifras como si midieran el mismo instante o utilizar el perímetro final como etiqueta de ignición. La coincidencia de Tornquist también es una asociación espacial-temporal probable: el parte SNMF nombra el Parque Provincial Ernesto Tornquist y registra un punto cercano al sector Cerro Ventana, pero no identifica exactamente el polígono GlobFire.

## Qué sí y qué no prueba

La revisión mejora la validez de dos etiquetas de evento: SNMF confirma que hubo incendios reales. No valida precisión predictiva. Son solo dos episodios elegidos retrospectivamente a partir de perímetros inspeccionados, un sensor de fuego tampoco es verdad de terreno, los puntos representan centros aproximados de sectores y una falta de detección no demuestra ausencia de fuego. El único acierto GOES ocurre el día del inicio reportado; por tanto, esta muestra no contiene un acierto de anticipación. No se calcula una precisión ni una probabilidad a partir de 1/2.

El análisis de coincidencia reproducible está en [`evaluate_goes_globfire_matches.py`](../../training/python/evaluate_goes_globfire_matches.py) y sus resultados en [`goes16-2024feb-globfire-matches.json`](goes16-2024feb-globfire-matches.json) y [`goes16-2024feb-globfire-matches-r20km.json`](goes16-2024feb-globfire-matches-r20km.json). El radio principal sigue siendo 10 km; los 20 km son una sensibilidad separada, necesaria para incluir el perímetro del Brazo Tristeza, cuyo centro está a 16,249 km del centro de sector de Frey.

## Fuentes

- [SNMF, parte diario del 5 de febrero de 2024](https://www.argentina.gob.ar/sites/default/files/2024/01/reporte_diario_05-02-2024.pdf): lista Arroyo Creton (Río Negro) como activo, con inicio 5/2, y Parque Provincial Ernesto Tornquist (Buenos Aires), inicio 3/2, extinguido 5/2, 300 ha.
- [SNMF, estadística mensual de febrero de 2024](https://www.argentina.gob.ar/sites/default/files/2024/01/informe_ocurrencia_febrero2024.pdf): fuente oficial adicional sobre ocurrencia reportada y focos VIIRS.
- [Gobierno de Río Negro, 5 de febrero de 2024](https://rionegro.gov.ar/articulo/48232/el-splif-se-sumara-para-combatir-el-incendio-en-bariloche): informa el incendio en Brazo Tristeza entre las 2 y las 4 de la mañana.
- [Parque Nacional Nahuel Huapi, crónica publicada el 1 de marzo de 2024](https://www.lanacion.com.ar/sociedad/finalmente-se-detuvo-el-incendio-en-el-parque-nacional-nahuel-huapi-se-quemaron-650-hectareas-nid01032024/): ubica el incendio cerca del arroyo Cretón, informa unas 650 ha a esa fecha y el cierre del sendero al lago Frey.
