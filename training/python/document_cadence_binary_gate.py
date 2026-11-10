"""Document the real-physiology binary gate and its global comparison."""
import json
import fatigue_cadence_binary_gate as study
from public_sources import digest

audit_path = study.DOCS/'cadence-binary-gate-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
summary = json.loads((study.DOCS/'cadence-binary-physiology-gate.json').read_text())
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(56,1892)
fmt = lambda value:f'{value*100:.4f}'.replace('.',',')
core,cat = [audit['best_positive_by_member'][m]['accuracy_mean'] for m in ('core','cat')]
zero_core,zero_cat = [audit['matched_zero_source_controls'][m]['accuracy_mean'] for m in ('core','cat')]
test = audit['new_test_evaluation']
test_text = ('No se abrió otro test. ' if test is None else
    f"El ganador congelado obtuvo **{test['test_correct']}/179 = {fmt(test['test_accuracy'])} %** en test tras guardar y recargar el artefacto. ")
paragraph = (
    'La etapa 56, `cadence-binary-physiology-gate-80-v1`, completó **6 configuraciones** del '
    '[plan predeclarado](cadence-binary-physiology-gate-plan.json): dos controles globales heredados '
    'y cuatro variantes con estado fisiológico previo, con/sin supervisión binaria CADENCE. '
    'El [adaptador auditado](cadence-binary-gate-input-verification.json) reconstruyó 1.057 pares '
    'contra celdas originales: **851 de ajuste y 206 reservados**, con 727 segundos antecedentes '
    'reales de ajuste y cuatro descensos conservados. También verificó los 666 casos y relojes '
    'nativos. Seis entradas numéricas de historia/pulso previo y cinco indicadores de disponibilidad '
    'real alimentan el encoder; cada dominio ajusta su propio normalizador solo con filas de '
    'ajuste. Los faltantes permanecen en el snapshot y no se generan vistas o reportes adicionales. '
    'La fuente usa pulso de la etapa anterior completada, una salida propia y Borg 6–20 original; '
    'no se convierten escalas ni se inventan edades o contexto nativo fuente. La mejor MLP con '
    f'fuente obtuvo **{fmt(core)} % CV**, frente al **{fmt(zero_core)} %** de su control medido; '
    f'CatBoost obtuvo **{fmt(cat)} %**, frente al **{fmt(zero_cat)} %** de su control. '
    'El control global conserva **63,7972 % CV**. [La auditoría](cadence-binary-gate-verification.json) '
    'verificó veinte artefactos y las seis métricas OOF, reprodujo las veinte redes con objetivos, '
    'pérdidas, gradientes y backward reales, y comprobó los normalizadores, pesos base congelados, '
    'proporciones entre cambios no nulos y recarga sin verdad actual o identificadores. Las cinco '
    '[pruebas nuevas](cadence-binary-gate-tests.log) pasaron en 8,595 segundos; se acumulan '
    '**297 pruebas distintas**, sin volver a ejecutar todas las suites históricas. '+test_text+
    f'El test verificado sigue en **{status["best_verified_test_correct"]}/179 = '
    f'{fmt(status["best_verified_test_accuracy"])} %**. La meta del 80 % continúa pendiente. '
    '[Resumen](cadence-binary-physiology-gate.json).\n\n'
    'La [revisión de errores pareados y estado reciente](cadence-gate-recent-native-state-review.json) '
    'muestra que CatBoost con fuente recuperó dos errores de su control medido y no dañó otros, '
    'pero no corrigió ningún error del control global y perdió dos aciertos respecto de él. '
    'El encoder incorpora pulso previo, mientras el contexto privado nativo sigue usando las '
    'trece entradas históricas. El pulso reciente y sus contrastes con el pulso previo están '
    'medidos antes de las 487 consultas de ajuste: pulso reciente sin faltantes y dos contrastes '
    'naturalmente ausentes. Esto permite preparar un ensayo de contexto reciente exclusivo '
    'nativo con controles; esos datos no se fabricarán para la fuente. Esa comparación aún '
    'no está predeclarada ni entrenada y su disponibilidad no demuestra una mejora.\n\n')
path = study.DOCS/'README.md'
code = path.read_text(encoding='utf-8')
if 'La etapa 56, `cadence-binary-physiology-gate-80-v1`' not in code:
    marker = '## Resultados comprobados de esta etapa\n'
    assert code.count(marker)==1
    code = code.replace(marker,paragraph+marker)
old = 'Las cincuenta y cinco búsquedas completas suman **1.886 configuraciones evaluadas**'
new = 'Las cincuenta y seis búsquedas completas suman **1.892 configuraciones evaluadas**'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
path.write_text(code,encoding='utf-8')
print('Documented audited study56and paired global-control comparison',flush=True)
