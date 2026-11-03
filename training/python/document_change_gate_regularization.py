"""Document audited study55 and its public-data eligibility follow-up."""
import json
import fatigue_change_gate_regularization as study
from public_sources import digest

audit_path = study.DOCS/'change-gate-regularization-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
summary = json.loads((study.DOCS/'change-gate-regularization.json').read_text())
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(55,1886)
fmt = lambda value:f'{value*100:.4f}'.replace('.',',')
core,cat = [audit['best_positive_by_member'][m]['accuracy_mean'] for m in ('core','cat')]
zero_core,zero_cat = [audit['matched_zero_source_controls'][m]['accuracy_mean'] for m in ('core','cat')]
test = audit['new_test_evaluation']
test_text = ('No se abrió otro test. ' if test is None else
    f"El único ganador congelado obtuvo **{test['test_correct']}/179 = {fmt(test['test_accuracy'])} %** en test, después de guardar y recargar el artefacto. ")
goal_text = 'La meta del 80 % está verificada.' if status['goal_achieved'] else 'La meta del 80 % continúa pendiente.'
paragraph = (
    'La etapa 55, `change-gate-regularization-80-v1`, completó las **18 configuraciones** del '
    '[plan predeclarado](change-gate-regularization-plan.json): seis controles heredados y doce '
    'combinaciones de penalización 0/0,1/1 con peso fuente 0/0,1 y bases MLP/CatBoost. Se '
    'mantuvieron la implementación anterior, las 80 épocas, inicializaciones, optimizador, '
    'normalizadores, cachés de personas y probabilidades relativas entre cambios no nulos. '
    'La mejor MLP con fuentes obtuvo '
    f'**{fmt(core)} % CV**, frente al **{fmt(zero_core)} %** de su control sin fuentes a la misma penalización; '
    f'la mejor CatBoost obtuvo **{fmt(cat)} %**, igual a su control. El control global conserva '
    '**63,7972 % CV**. [La auditoría](change-gate-regularization-verification.json) verificó los '
    'sesenta artefactos de fold y las dieciocho métricas OOF; reprodujo veinte redes, sus '
    'coeficientes reales en la pérdida, objetivos originales, gradientes y ochenta llamadas '
    'de backward por ajuste. También comprobó pesos base congelados, proporciones no nulas '
    'conservadas, normalización exclusiva de ajuste y recarga sin verdad actual o identificadores. '
    'Las cinco [pruebas nuevas](change-gate-regularization-tests.log) pasaron en 17,683 segundos; '
    'se acumulan **292 pruebas distintas**, sin repetir todas las suites históricas. '+test_text+
    f'El test verificado sigue en **{status["best_verified_test_correct"]}/179 = '
    f'{fmt(status["best_verified_test_accuracy"])} %**. '+goal_text+
    ' [Resumen](change-gate-regularization.json).\n\n'
    'El [diagnóstico de márgenes](change-gate-regularization-margin-diagnostic.json) confirmó '
    'que bajar la penalización produjo entre 6 y 27 cambios de decisión Borg por receta. '
    'Por tanto, la ausencia de mejora ya no puede atribuirse solo a un ajuste inmóvil. '
    'Ninguna variante superó al control global y no se justifica ampliar esta misma grilla. '
    'Los límites hipotéticos con oráculo siguen separados de la accuracy realmente obtenida.\n\n'
    'La [revisión fisiológica CADENCE](cadence-binary-physiology-review.json) comprobó contra '
    'celdas originales **851 pares adyacentes de ajuste de 123 personas**, con 299 no cambios, '
    '552 cambios, cuatro descensos y 727 segundos antecedentes genuinos. Los 206 pares de '
    'otras 32 personas permanecen reservados; la separación se había fijado sobre las 156 '
    'personas originales antes de exigir pares elegibles. El pulso fuente proviene de la '
    'etapa previa completada y se verificaron las ventanas de pulso previo y base de los '
    '487 casos nativos de ajuste. Se conservan dos pulsos previos y cuatro bases ausentes. '
    'Las definiciones de reposo y las escalas fuente/nativa siguen siendo distintas; no '
    'se inventan relojes de respuesta, edades o fases equivalentes. Una representación '
    'auxiliar binaria con fisiología real requiere un adaptador auditado y una comparación '
    'predeclarada con controles; todavía no se ha predeclarado ni entrenado ese modelo.\n\n')
path = study.DOCS/'README.md'
code = path.read_text(encoding='utf-8')
if 'La etapa 55, `change-gate-regularization-80-v1`' not in code:
    marker = '## Resultados comprobados de esta etapa\n'
    assert code.count(marker)==1
    code = code.replace(marker,paragraph+marker)
old = 'Las cincuenta y cuatro búsquedas completas suman **1.868 configuraciones evaluadas**'
new = 'Las cincuenta y cinco búsquedas completas suman **1.886 configuraciones evaluadas**'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
path.write_text(code,encoding='utf-8')
print('Documented audited study55and separate851pair physiology eligibility review',flush=True)
