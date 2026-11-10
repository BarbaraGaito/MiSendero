"""Document full-delta source transfer,overfitting and preserved test result."""
import json
import fatigue_cadence_full_delta as study
from public_sources import digest

summary = json.loads((study.DOCS/'cadence-full-delta-residual.json').read_text())
assert summary['verification_sha256']==digest(study.DOCS/'cadence-full-delta-verification.json')
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(58,1916)
paragraph = '''La etapa 58, `cadence-full-delta-residual-80-v1`, completó **14 configuraciones** del
[plan predeclarado](cadence-full-delta-residual-plan.json): seis controles heredados y ocho variantes
con dos bases, pesos externos 0/0,1 y penalizaciones 0,1/1. La red ajusta 21 logits de cambio Borg
mediante entropía cruzada sobre las respuestas nativas reales. Los residuales comienzan en cero y
se centran por fila; los pesos del clasificador base permanecen congelados. La salida CADENCE
aprende por separado si dos respuestas originales 6–20 difieren. Se mantienen las once entradas
compartidas de historia/pulso previo y las dieciséis del contexto privado nativo, los 851 pares
externos de ajuste y 206 reservados. No se añaden ejemplos sintéticos ni contexto fuente supuesto.

La mejor variante nueva con fuente alcanzó **61,3929 % CV**, frente a **60,7849 %** de su control
sin fuente con la misma penalización. El control global continúa en **63,7972 % CV**. La
[auditoría independiente](cadence-full-delta-verification.json) verificó las catorce métricas OOF
y los cuarenta artefactos, reprodujo las cuarenta redes y comprobó los objetivos, la pérdida,
el gradiente de los 21 residuales, la contribución fuente, los 80 backward reales de cada ajuste
y la recarga con entradas únicamente. Las [seis pruebas](cadence-full-delta-tests.log) pasaron en
8,906 segundos; el total acumulado es **309 pruebas distintas**, sin repetir todas las suites
históricas. No se habilitó otro test. El resultado verificado permanece en
**108/179 = 60,3352 %**; el objetivo de al menos **144/179** sigue pendiente.
[Resumen de la etapa](cadence-full-delta-residual.json).

El [diagnóstico de generalización](cadence-full-delta-generalization-diagnostic.json) comprobó
que las ocho variantes redujeron la pérdida durante el ajuste, usando los offsets originales
de los folds internos, y la empeoraron en personas de validación. La penalización 1 superó a
0,1 en las cuatro parejas de arquitectura/peso externo. La mejor variante CatBoost con fuente
corrigió siete respuestas pero perdió diecinueve frente al control global. Su mejora de cinco
aciertos frente a dos pérdidas respecto del control nuevo sin fuente no establece una mejora
global. La siguiente comparación puede evaluar penalizaciones 10/100 con los demás componentes
congelados; todavía no está predeclarada ni entrenada. Ningún diagnóstico utiliza los 179 casos
de test para seleccionar hiperparámetros.

'''
path = study.DOCS/'README.md'
text = path.read_text(encoding='utf-8')
if 'La etapa 58, `cadence-full-delta-residual-80-v1`' not in text:
    marker = '## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text = text.replace(marker,paragraph+marker)
old = 'Las cincuenta y siete búsquedas completas suman **1.902 configuraciones evaluadas**'
new = 'Las cincuenta y ocho búsquedas completas suman **1.916 configuraciones evaluadas**'
if new not in text:
    assert text.count(old)==1
    text = text.replace(old,new)
text = text.replace('Esa comparación todavía no está predeclarada ni entrenada.',
    'Esa comparación se completó en la etapa 58, documentada a continuación.')
path.write_text(text,encoding='utf-8')
print('Documented audited study58and full-delta overfitting evidence',flush=True)
