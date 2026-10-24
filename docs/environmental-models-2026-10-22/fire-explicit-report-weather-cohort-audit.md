# Cohorte SNMF explícita unida con pronósticos históricos

Se unieron únicamente etiquetas de incidentes SNMF dentro de 10 km de senderos y fechas cuyo parte nacional dice explícitamente que no hubo incendios reportados. Para cada fecha se asociaron variables JMA GSM archivadas con vigencia UTC ese día y emitidas en la corrida previa. No se mezclaron positivos satelitales de otros productos con la etiqueta de partes oficiales.

El cruce produjo **277 pares sendero-fecha**: 21 positivos de 20 fechas de incidente y 256 negativos de 32 fechas de parte. En el test temporal 2025 hay **5 positivos y 8 negativos**, pero esos negativos pertenecen a solo **1 fecha**.

Como referencia de tamaño muestral, hacen falta al menos **29 episodios de alerta independientes y todos correctos** para que el límite inferior unilateral exacto al 95 % supere el 90 %; con falsas alarmas se necesitan más. El test disponible no alcanza esa escala.

Si se toma como positivo cualquier señal de las tres fuentes unificadas, aparecen 44 fechas-sendero positivas alineadas (11 en 2025), pero cambia el significado del objetivo y se mantienen solo ocho negativos de una fecha en el test. Esa unión sirve para estudiar concordancia de fuentes, no para atribuir una única precisión de predicción.

Por esa concentración no entrené ni ajusté hiperparámetros: una precisión calculada aquí sería inestable. El CSV comprimido conserva ruta, fecha, clase, procedencia y siete variables meteorológicas; el JSON registra hashes y conteos.

**Resultado:** se confirmó que el empalme de fuentes y pronósticos funciona, pero la cohorte aún no permite afirmar una precisión fiable. Se requieren más fechas negativas explícitas y más eventos independientes en el período posterior reservado.
