"""Document the audited actual-source gate study and its measured limitation."""
import json
import fatigue_public_change_gate as study
from public_sources import digest

audit_path = study.DOCS/'public-change-gate-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
summary = json.loads((study.DOCS/'public-change-gate-transfer.json').read_text())
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(54,1868)
fmt = lambda value:f'{value*100:.4f}'.replace('.',',')
core,cat = [audit['best_positive_by_member'][member]['accuracy_mean'] for member in ('core','cat')]
test = audit['new_test_evaluation']
test_text = ('No se abrió otro test. ' if test is None else
    f"El único ganador congelado obtuvo **{test['test_correct']}/179 = {fmt(test['test_accuracy'])} %** en test, después de guardar y recargar el artefacto. ")
retained = status['best_verified_test_correct']
goal_text = 'La meta del 80 % está verificada.' if status['goal_achieved'] else 'La meta del 80 % continúa pendiente.'
paragraph = (
    'La etapa 54, `public-change-gate-transfer-80-v1`, completó las **10 configuraciones** del '
    '[plan predeclarado](public-change-gate-plan.json): cuatro controles heredados y seis redes de '
    'corrección de cambio/no cambio, con pesos fuente 0/0,1/1 y bases MLP/CatBoost congeladas. '
    'Los 2.287 pares reales EMAP, Worker, resistencia y hombro supervisan cuatro salidas binarias '
    'separadas; sus valores, escalas, resoluciones y protocolos no se convierten en etiquetas Borg '
    'nativas. Los 49 pares STS de una sola clase quedan fuera y los 312 pares fuente reservados '
    'no se usan para ajustar. Cada fuente usa únicamente antecedentes realmente observados; no '
    'se fabrican contexto nativo, tiempos o clases ausentes. Se corrige solo la probabilidad de '
    'cambio, conservando las proporciones entre las clases exactas de cambio no nulo del modelo '
    'base. La mejor MLP con fuente conserva '
    f'**{fmt(core)} % CV** y la mejor CatBoost **{fmt(cat)} %**, iguales a sus controles. '
    '[La auditoría](public-change-gate-verification.json) verificó los treinta artefactos de fold, '
    'las diez métricas OOF y treinta modelos internos nativos anteriores mediante nuevas pasadas '
    'de inferencia; reprodujo veinte redes, interceptó ochenta llamadas reales de backward por '
    'ajuste, reconstruyó pérdidas y objetivos binarios desde los pares originales, y comprobó '
    'gradientes fuente en el encoder, inicialización, cinco normalizadores por ajuste, pesos base '
    'congelados, proporciones no nulas conservadas y recarga sin etiquetas actuales o identificadores. '
    'Las cinco [pruebas nuevas](public-change-gate-tests.log) pasaron en 17,017 segundos; se '
    'acumulan **287 pruebas distintas**, sin repetir todas las suites históricas. '+test_text+
    f'El mejor test verificado permanece en **{retained}/179 = {fmt(status["best_verified_test_accuracy"])} %**. '+
    goal_text+' [Resumen](public-change-gate-transfer.json).\n\n'
    'El [diagnóstico de ajustes y umbrales](public-change-gate-margin-diagnostic.json), limitado '
    'a las personas de ajuste, comprobó que ninguna de las seis recetas nuevas cambió una '
    'decisión Borg OOF. La pérdida nativa disminuyó y los gradientes fuente fueron distintos de '
    'cero, pero el ajuste logarítmico mediano CatBoost con fuente fue aproximadamente 0,00176, '
    'frente a 1,00966 de distancia mediana al umbral de cambio de decisión. Esto permite estudiar '
    'una penalización menos restrictiva con controles pareados; no demuestra que una penalización '
    'menor mejore CV. Los límites de elección con oráculo del informe son hipotéticos y no '
    'representan accuracy conseguida. La siguiente comparación de penalizaciones todavía no '
    'está predeclarada ni entrenada.\n\n')
path = study.DOCS/'README.md'
code = path.read_text(encoding='utf-8')
if 'La etapa 54, `public-change-gate-transfer-80-v1`' not in code:
    marker = '## Resultados comprobados de esta etapa\n'
    assert code.count(marker)==1
    code = code.replace(marker,paragraph+marker)
old = 'Las cincuenta y tres búsquedas completas suman **1.858 configuraciones evaluadas**'
new = 'Las cincuenta y cuatro búsquedas completas suman **1.868 configuraciones evaluadas**'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
if retained>108:
    lines = code.splitlines()
    previous = next(line for line in lines if line.startswith('Meta pendiente. La referencia verificada anterior conserva'))
    updated = (('Meta verificada. ' if status['goal_achieved'] else 'Meta pendiente. ')+
        f'El mejor resultado verificado conserva **{retained}/179 = {fmt(status["best_verified_test_accuracy"])} %**. '+
        'El 80 % exige al menos **144/179 aciertos** sobre las mismas respuestas reservadas, sin cambiar el denominador ni agrupar Borg en bandas.')
    code = code.replace(previous,updated)
path.write_text(code,encoding='utf-8')
print('Documented audited study54and measured decision-level inertia',flush=True)
