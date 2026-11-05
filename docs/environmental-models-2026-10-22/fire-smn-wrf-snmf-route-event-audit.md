# Evaluación independiente WRF-SMN frente a eventos SNMF, segundo semestre de 2023

El pronóstico meteorológico WRF-SMN de 27 h se cruzó con el inicio y las coordenadas de incendios reportados oficialmente por SNMF. Se mantuvieron congelados el modelo y el umbral diagnóstico 0,5; el modelo no se reajustó con estos episodios.

En el radio fijado de 10 km se encontraron **2 días sector-ruta** con un inicio de incendio reportado. Solo **1** tenían cobertura válida del modelo; ese único caso recibió alerta. El segundo evento no se cuenta como acierto ni error porque no tuvo cobertura.

Esto mide coincidencia/sensibilidad frente a los casos reportados, no precisión: el archivo diario del SNMF no es exhaustivo y sus días sin parte no son negativos. El score 0,5 no es una probabilidad. Los detalles por evento, hashes y límites están en el JSON asociado.
