# Catálogo unificado de eventos de fuego en las 41 rutas argentinas

Catálogo con procedencia de partes SNMF, focos INPE Aqua/MODIS y Global Fire Atlas. Las rutas se asociaron usando la polilínea completa y un radio de 10 km; no es un censo de incendios ni una tabla de negativos.

Se procesaron 41 rutas. El catálogo contiene 299 grupos de evidencia de 313 registros fuente; 12 grupos reúnen más de un registro y 32 pares posibles permanecen sin fusionar.

Conteos fuente: {"OFFICIAL_INCIDENT_REPORT": 165, "AQUA_MODIS_ACTIVE_FIRE": 63, "MODIS_DERIVED_FIRE_ATLAS": 85}. Posibles clases: {"satellite_positive_candidate_only": 127, "multiple_products_same_satellite_family": 7, "official_report_plus_satellite_corroboration": 5, "official_report_only": 160}.

INPE AMS y GFA comparten la familia MODIS. Los negativos de entrenamiento no se infieren del silencio de estas fuentes; en el dataset unido solo se consideran no-detecciones con QA MODIS despejado.

## Eventos por ruta

- aconquija-el-pozon: 1
- aconquija-puesto-chorizos: 1
- aguilas: 3
- alerces-alto-petiso: 6
- alerces-arroyo-hacha: 4
- alerces-cerro-cocinero: 8
- alerces-laguna-escondida: 7
- bateaMirador: 14
- bosqueTallado: 16
- cerroAlto: 6
- condores: 3
- condorito: 4
- condorito-secretos-pies: 3
- encantadoMirador: 8
- esquelCruz: 9
- frey: 6
- fuego-pampa-alta: 1
- hito: 1
- lanin-rosales-san-martin: 10
- llao-llao-villa-tacul: 1
- mburucuya-che-roga: 20
- mburucuya-tape-pora: 16
- namuncura: 6
- porito: 7
- puertaCielo: 23
- sanBernardo: 89
- tabaquillo: 8
- uritorco: 12
- ventana: 6

El JSON conserva identificadores, fechas, coordenadas, distancias, enlaces posibles y SHA-256 de cada insumo. Este catálogo no es, por sí solo, un dataset listo para inferencia.
