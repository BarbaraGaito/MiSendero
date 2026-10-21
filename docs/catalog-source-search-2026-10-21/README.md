# Datos documentados para la tesis

Revisión del 21/10/2026 de los nueve tiempos totales y ocho ascensos acumulados señalados en el informe previo. Se localizaron dos referencias utilizables de duración. Los otros quince campos se excluyen de los análisis que requieren esa variable; no se completan con ceros, promedios, duplicaciones o etiquetas de sustitución.

## Referencias incorporadas

| Sendero | Tiempo publicado | Alcance | Fuente |
| --- | --- | --- | --- |
| Cerro Tres Picos en el día | Aproximadamente 9 horas | Actividad de ascenso y regreso desde el estacionamiento de Estancia Funke | Documento del administrador, página 3 |
| Base norte del Lanín - Refugio BIM | 9 horas de trekking | Programa desde la seccional Río Turbio hasta BIM y descenso | Ficha técnica del operador Destino Andino |

En Tres Picos se consultó el documento enlazado por el propio administrador: [Fundación Funke](https://fundacionfunke.org.ar/turismo/) → [información pública](https://linktr.ee/turismofun) → [PDF de circuitos](https://drive.google.com/file/d/1qGcyDs0k1Zo_X0dMARqLEBIHd2KHf-Uk/view). Se verificó visualmente la página correspondiente: distingue la caminata de ida y vuelta del acceso vehicular y de la variante con pernocte. Se utiliza la referencia actual del administrador en lugar del intervalo histórico de una tesis de 2014.

En BIM, [Destino Andino](https://www.destinoandino.tur.ar/servicios/Trekking-en-San-Martin-de-los-Andes---Refugio-Volcan-Lanin,-cara-norte/UUWX1T8MIKSM/) identifica el refugio y el descenso y distingue la duración de trekking del horario de toda la excursión. No se adopta la duración de un ascenso a la cumbre del volcán.

Ambos son tiempos orientativos publicados, no mediciones cronometradas de participantes ni observaciones de aptitud o seguridad. La fuente del segundo registro es el operador del programa, no APN; ese origen permanece explícito. Si el estudio requiere exclusivamente mediciones de campo o datos publicados por el administrador del área, debe filtrar por `source_kind` y `evidence_kind`; no puede presentar ambos registros como mediciones directas.

Los valores, unidades, alcance y fuentes están en [datos-confirmados.json](datos-confirmados.json). Ese archivo contiene únicamente los registros incorporados, sin campos pendientes ni filas de relleno.

## Criterio de inclusión y exclusión

Se incorpora un tiempo cuando una fuente técnica identificable refiere al mismo destino y objetivo, explicita el recorrido completo y distingue la caminata de traslados u otros circuitos. Se conserva la clase de fuente y el carácter orientativo del valor. No se transforma automáticamente un tiempo de ida en un tiempo de regreso.

Para ascenso acumulado se requiere que la fuente identifique expresamente esa medida para el mismo itinerario, con procedencia técnica suficiente, o una traza completa que permita un cálculo reproducible. La altura de una cumbre, la diferencia de cotas y un valor rotulado solo como desnivel no se intercambian con la suma de ascensos. Las referencias del modelo de elevación ya verificadas se mantienen como estimaciones derivadas, en su grupo de análisis correspondiente.

La unidad de exclusión es **sendero y variable**: omitir un ascenso no elimina datos respaldados de distancia o duración del mismo sendero. Cada cálculo utiliza únicamente sus registros incluidos y declara su propio tamaño de muestra. Una tabla que requiera tiempo y ascenso simultáneamente debe usar la intersección de los registros que cumplen ambos criterios. Los quince campos excluidos no participan de medias, comparaciones, puntuaciones ni denominadores de resultados que requieran su valor.

Se conserva [exclusiones.json](exclusiones.json) como registro de revisión, separado de las tablas de resultados. Contiene el motivo y las fuentes consultadas, sin asignar valores a los campos descartados. Esto documenta la selección de datos sin ocultar cómo se construyó la muestra.

## Texto para metodología

> Se incluyeron únicamente valores con fuente identificable y alcance compatible con el itinerario analizado. Los campos que no cumplieron ese criterio se excluyeron de los cálculos de la variable correspondiente, sin imputación. Se distinguieron referencias orientativas publicadas, mediciones y estimaciones derivadas. Cada análisis informa la cantidad de registros efectivamente incluidos; las exclusiones se conservan en un registro de revisión separado.

## Alcance de los cambios

Esta revisión agrega evidencia y criterios para el conjunto documental de la tesis. No modifica código, el seed, las definiciones de ejecución ni la base de datos. Los conteos y escenarios del informe funcional anterior describen su snapshot original; no se los presenta como una evaluación nueva de la app. Las reglas documentadas aquí reemplazan el tratamiento de pendientes propuesto para la tesis, sin inventar nuevos resultados del recomendador.
