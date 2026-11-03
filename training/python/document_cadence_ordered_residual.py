"""Document the ordered-residual result and newly inspected raw-data candidate."""
import json
import fatigue_cadence_ordered_residual as study
from public_sources import digest

summary = json.loads((study.DOCS/'cadence-ordered-residual.json').read_text())
assert summary['verification_sha256']==digest(study.DOCS/'cadence-ordered-residual-verification.json')
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(60,1956)
paragraph = '''La etapa 60, `cadence-ordered-residual-80-v1`, completó **26 configuraciones** del
[plan predeclarado](cadence-ordered-residual-plan.json): dieciocho controles heredados y ocho
variantes nuevas. Tres coeficientes se expanden a los 21 logits mediante una base matemática
centrada y ortonormal que representa cambio, cambio al cuadrado y masa de cambio cero. La
última capa pasó de 189 a 27 parámetros. Se conservaron exactamente la inicialización compartida
del encoder, la primera capa correctora y la salida externa, además de los datos, normalizaciones,
objetivos, 80 pasos y demás hiperparámetros. Los ocho controles libres con las mismas penalizaciones
permiten comparar las estructuras sin confundir el efecto con la elección de penalización.

La mejor variante nueva fue MLP con fuente y penalización 1: **61,0047 % CV**, frente a
**60,4156 %** de su control ordenado sin fuente y **60,6497 %** del residual libre con la misma
penalización. CatBoost con fuente obtuvo **60,9810 %**, frente a **60,7849 %** del control
ordenado sin fuente y **61,3929 %** del residual libre. Ninguna superó el control global de
**63,7972 % CV**. El [diagnóstico](cadence-ordered-residual-diagnostic.json) mostró que las ocho
variantes redujeron la pérdida en ajuste y la empeoraron al validar en otras personas. Reducir
la dimensión de salida no resolvió la generalización.

La [auditoría](cadence-ordered-residual-verification.json) recalculó las veintiséis métricas OOF,
verificó los cuarenta artefactos y reprodujo las cuarenta redes. Comprobó la base fija, su expansión,
la igualdad de inicialización, el gradiente real de los tres coeficientes, la fuente observada,
los 80 backward por ajuste y los pesos base inmutables. Las
[siete pruebas nuevas](cadence-ordered-residual-tests.log) pasaron en 11,571 segundos; el total
acumulado es **322 pruebas distintas**, sin repetir todas las suites históricas. La base matemática
no constituye observaciones ni etiquetas sintéticas. No se habilitó otro test. El resultado
verificado continúa en **108/179 = 60,3352 %**; el objetivo de al menos **144/179** sigue pendiente.
[Resumen](cadence-ordered-residual.json).

La [inspección de una posible fuente adicional](rpe-forecasting-candidate-inspection.json) fijó la
revisión `2e2233a6a755b05dc4dc0404d580d401ff7d520e` del
[repositorio público RPE_Forecasting](https://github.com/sahand-hajifar/RPE_Forecasting).
El contexto de los autores describe dos estudios. El primero usa series normalizadas por
percentiles y filtradas; se excluye de nuevos ajustes. El segundo dispone de archivos de 24
participantes y describe una respuesta RPE por periodo de sentadillas, repetida entre las zancadas
de la caminata siguiente. Antes de revisar celdas de resultados se separaron **19 participantes
de ajuste y 5 reservados**, con semilla 42. No se descargaron aún los workbooks originales ni
se aprobó su incorporación. La siguiente tarea es recuperar únicamente los diecinueve archivos
de ajuste, comprobar sus hashes Git y verificar las respuestas originales, la escala y el orden
real de los ensayos. Las zancadas repetidas no se contarán como reportes RPE independientes.
Los scripts de los autores se inspeccionaron como texto y no se ejecutaron.

'''
path = study.DOCS/'README.md'
text = path.read_text(encoding='utf-8')
if 'La etapa 60, `cadence-ordered-residual-80-v1`' not in text:
    marker = '## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text = text.replace(marker,paragraph+marker)
old = 'Las cincuenta y nueve búsquedas completas suman **1.930 configuraciones evaluadas**'
new = 'Las sesenta búsquedas completas suman **1.956 configuraciones evaluadas**'
if new not in text:
    assert text.count(old)==1
    text = text.replace(old,new)
text = text.replace('Esa\ncomparación aún no está predeclarada ni entrenada, y no establece una mejora de accuracy.',
    'Esa comparación se completó en la etapa 60, documentada a continuación.')
path.write_text(text,encoding='utf-8')
print('Documented audited study60and pinned public-source candidate inspection',flush=True)
