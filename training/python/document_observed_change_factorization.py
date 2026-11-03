"""Document audited study53 and the unchanged full-task success criterion."""
import json
import fatigue_observed_change_factorization as study
from public_sources import digest

audit_path = study.DOCS/'observed-change-factorization-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
summary = json.loads((study.DOCS/'observed-change-factorization.json').read_text())
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(53,1858)
fmt = lambda value:f'{value*100:.4f}'.replace('.',',')
core,cat = [audit['best_factorized_by_member'][key]['accuracy_mean'] for key in ('core','cat')]
flat_core,flat_cat = [audit['matched_flat_controls'][key]['accuracy_mean'] for key in ('core','cat')]
retained = status['best_verified_test_correct']
test = audit['new_test_evaluation']
test_text = ('No se abrió otro test. ' if test is None else
    f"El único ganador congelado obtuvo **{test['test_correct']}/179 = {fmt(test['test_accuracy'])} %** en test, después de guardar y recargar el artefacto. ")
goal_text = 'La meta del 80 % está verificada.' if status['goal_achieved'] else 'La meta del 80 % continúa pendiente.'
paragraph = (
    'La etapa 53, `observed-change-factorization-80-v1`, completó las **10 configuraciones** del '
    '[plan predeclarado](observed-change-factorization-plan.json): dos controles heredados y ocho '
    'comparaciones de estructura directa/de dos etapas, con historia sola o las mismas tres mediciones '
    'de pulso adicionales. Se mantuvieron los hiperparámetros de cada familia. La primera etapa aprende '
    'si cambió Borg a partir de pares realmente observados; la segunda aprende la clase exacta de cambio '
    'solo sobre sus cambios no nulos de ajuste. Se conservaron los cambios negativos y los 487/179 '
    'casos originales. La mejor MLP de dos etapas obtuvo '
    f'**{fmt(core)} % CV**, frente al **{fmt(flat_core)} %** del control directo con las mismas entradas. '
    f'La mejor CatBoost de dos etapas obtuvo **{fmt(cat)} %**, frente al **{fmt(flat_cat)} %** de su control. '
    '[La auditoría](observed-change-factorization-verification.json) verificó los cuarenta artefactos de '
    'fold, las diez métricas OOF y la distribución completa de probabilidades; reprodujo '
    f"{audit['independent_candidate_fold_refits']} modelos completos y {audit['independent_stage_estimator_refits']} "
    'ajustes de etapa, interceptando filas y objetivos reales, y comprobó estadísticas exclusivas de ajuste '
    'y recarga sin verdad actual o identificadores. Las cinco [pruebas nuevas](observed-change-factorization-tests.log) '
    'pasaron en 175,639 segundos; se acumulan **282 pruebas distintas**, sin volver a ejecutar todas las '
    'suites históricas. '+test_text+f'El mejor test verificado queda en **{retained}/179 = '
    f"{fmt(status['best_verified_test_accuracy'])} %**. "+goal_text+' [Resumen](observed-change-factorization.json).\n\n'
    'El [diagnóstico por etapa](observed-change-stage-diagnostic.json) compara ajuste y validación en '
    'las personas de entrenamiento, sin nuevos ajustes ni consultas al test. Las accuracies de la '
    'detección binaria y de la magnitud condicional describen componentes internos; no sustituyen '
    'la accuracy Borg exacta del objetivo completo.\n\n'
    'La [revisión de cambios observados en fuentes públicas](public-observed-change-support-review.json) '
    'examinó los 2.336 pares fuente de ajuste, sin usar los 312 reservados. EMAP, Worker, resistencia '
    'y hombro reúnen **2.287 pares** con cambios y no cambios realmente observados; los 49 pares STS '
    'solo contienen cambios. La comprobación inicial exigía incorrectamente ambas clases en cada '
    'fuente; se conservó ese fallo y se corrigió el perfil sin inventar observaciones de la clase '
    'ausente. Las diferencias de escala, resolución y protocolo permanecen explícitas: los resultados '
    'no se mezclan con etiquetas nativas ni establecen equivalencia fisiológica. Todavía no se ha '
    'predeclarado ni entrenado una representación auxiliar de cambios binarios por fuente.\n\n')
path = study.DOCS/'README.md'
code = path.read_text(encoding='utf-8')
if 'La etapa 53, `observed-change-factorization-80-v1`' not in code:
    marker = '## Resultados comprobados de esta etapa\n'
    assert code.count(marker)==1
    code = code.replace(marker,paragraph+marker)
old = 'Las cincuenta y dos búsquedas completas suman **1.848 configuraciones evaluadas**'
new = 'Las cincuenta y tres búsquedas completas suman **1.858 configuraciones evaluadas**'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
if retained>108:
    lines = code.splitlines()
    old_line = next(line for line in lines if line.startswith('Meta pendiente. La referencia verificada anterior conserva'))
    current_line = (('Meta verificada. ' if status['goal_achieved'] else 'Meta pendiente. ')+
        f'El mejor resultado verificado conserva **{retained}/179 = {fmt(status["best_verified_test_accuracy"])} %**. '+
        'El 80 % exige al menos **144/179 aciertos** sobre las mismas respuestas reservadas, sin cambiar el denominador ni agrupar Borg en bandas.')
    code = code.replace(old_line,current_line)
path.write_text(code,encoding='utf-8')
print('Documented audited study53and full179case success criterion',flush=True)
