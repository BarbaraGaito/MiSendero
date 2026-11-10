"""Document stronger regularization and the unchanged exact-Borg benchmark."""
import json
import fatigue_cadence_delta_regularization as study
from public_sources import digest

summary = json.loads((study.DOCS/'cadence-delta-regularization.json').read_text())
assert summary['verification_sha256']==digest(study.DOCS/'cadence-delta-regularization-verification.json')
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(59,1930)
paragraph = '''La etapa 59, `cadence-delta-regularization-80-v1`, completó **14 configuraciones** del
[plan predeclarado](cadence-delta-regularization-plan.json): seis controles globales o de
penalización 1 y ocho variantes con penalizaciones 10/100. Conservó exactamente el objetivo,
la arquitectura, las normalizaciones, los 851 pares externos y 206 reservados, las once entradas
compartidas, las dieciséis privadas nativas, los 80 pasos y los hiperparámetros restantes.

La mejor CatBoost con fuente, con penalización 100, alcanzó **63,6011 % CV**, frente al
**63,2090 %** del control nuevo sin fuente y el **61,3929 %** de su antecedente con penalización 1.
El control global mantiene **63,7972 % CV**. El diagnóstico pareado encontró dos aciertos
recuperados y ninguna pérdida respecto del control nuevo sin fuente, pero ningún error corregido
y un acierto perdido frente al control global. La MLP prefirió penalización 10 a 100.
[Diagnóstico](cadence-delta-regularization-generalization-diagnostic.json).

La [auditoría independiente](cadence-delta-regularization-verification.json) recalculó las catorce
métricas OOF, verificó los cuarenta artefactos y reprodujo las cuarenta redes, comprobando la
pérdida, los gradientes, la fuente real, los 80 backward por ajuste y los pesos base inmutables.
Las [seis pruebas nuevas](cadence-delta-regularization-tests.log) pasaron en 9,098 segundos;
el total acumulado es **315 pruebas distintas**, sin volver a ejecutar todas las suites históricas.
Ninguna variante habilitó otro test. El resultado verificado sigue en **108/179 = 60,3352 %**;
el objetivo de al menos **144/179** continúa pendiente. [Resumen](cadence-delta-regularization.json).

La [revisión de un residual ordenado pequeño](cadence-ordered-residual-review.json) verificó una
base matemática fija de tres direcciones —cambio, cambio al cuadrado e indicador de cambio cero—
centrada y ortonormal. Un cabezal de tres coeficientes reduciría los parámetros de la última capa
de 189 a 27 y permitiría modificar la magnitud del cambio con menos grados de libertad. La base
describe geometría de las clases; no genera observaciones ni etiquetas de entrenamiento. Esa
comparación aún no está predeclarada ni entrenada, y no establece una mejora de accuracy.

La [consulta renovada de metadatos oficiales](treadmill-cr10-access-refresh.json) confirmó que
[Zenodo 23208045](https://zenodo.org/records/23208045), ya revisado, continúa bajo embargo hasta
el 7 de abril de 2027 y no expone archivos públicos. Además, el campo de licencia indica CC BY 4.0
y la descripción CC BY-NC 4.0. No se descargaron señales ni se incorporaron filas de esa fuente.
La descripción mantiene el último Borg entre respuestas: esas repeticiones no se pueden contar
como autoevaluaciones originales independientes. No se programaron reintentos de descarga.

'''
path = study.DOCS/'README.md'
text = path.read_text(encoding='utf-8')
if 'La etapa 59, `cadence-delta-regularization-80-v1`' not in text:
    marker = '## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text = text.replace(marker,paragraph+marker)
old = 'Las cincuenta y ocho búsquedas completas suman **1.916 configuraciones evaluadas**'
new = 'Las cincuenta y nueve búsquedas completas suman **1.930 configuraciones evaluadas**'
if new not in text:
    assert text.count(old)==1
    text = text.replace(old,new)
text = text.replace('La siguiente comparación puede evaluar penalizaciones 10/100 con los demás componentes\ncongelados; todavía no está predeclarada ni entrenada.',
    'La comparación de penalizaciones 10/100 se completó en la etapa 59, documentada a continuación.')
path.write_text(text,encoding='utf-8')
print('Documented audited study59and unchanged global-control result',flush=True)
