"""Update the user-facing research record only after the independent audit."""
import json
import fatigue_causal_transition_memory as study
from public_sources import digest

audit_path = study.DOCS/'causal-transition-memory-verification.json'
audit = json.loads(audit_path.read_text())
assert audit['verification']=='passed' and audit['selection_sha256']==digest(study.DIRECTORY/'selection.json')
summary = json.loads((study.DOCS/'causal-transition-memory.json').read_text())
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(52,1848)
core = audit['best_positive_by_member']['core']['accuracy_mean']*100
cat = audit['best_positive_by_member']['cat']['accuracy_mean']*100
fmt = lambda number:f'{number:.4f}'.replace('.',',')
paragraph = (
    'La etapa 52, `causal-transition-memory-80-v1`, completó las **36 configuraciones** del '
    '[plan predeclarado](causal-transition-memory-plan.json): dos controles heredados, dos controles '
    'sin memoria y 32 combinaciones de consulta de transiciones anteriores reales. Reutiliza diez '
    'clasificadores base completos; los 170 imputadores y normalizadores nuevos usan exclusivamente '
    'personas de ajuste de cada fold. Cada consulta recibe un paquete separado con reportes reales '
    'de la misma persona y sesión —opcionalmente de la misma tarea— de al menos un minuto antes. '
    'El artefacto de población no guarda la memoria personal. La mejor MLP con memoria obtuvo '
    f'**{fmt(core)} % CV**, frente al **60,8206 %** de su control; la mejor CatBoost obtuvo '
    f'**{fmt(cat)} %**, frente al **63,7972 %** del control. '
    '[La auditoría independiente](causal-transition-memory-verification.json) recalculó las 36 métricas OOF, '
    'los 170 casos receta/fold, los objetivos anteriores y los relojes originales; repitió los 170 '
    'ajustes de preprocesamiento y comprobó veinte recargas sin memoria personal guardada. '
    'Pasaron cinco [pruebas con registros reales](causal-transition-memory-tests.log), para **277 '
    'pruebas distintas acumuladas**, sin repetir todas las suites históricas. No se abrió otro test; '
    '**108/179** sigue retenido y el 80 % continúa pendiente. [Resumen](causal-transition-memory.json).\n\n'
    'El [diagnóstico de errores de memoria](causal-transition-memory-error-diagnostic.json), limitado '
    'a personas de ajuste, encontró 174 de 391 consultas con antecedentes de la tarea sin un cambio '
    'Borg anterior idéntico. La mejor memoria CatBoost corrigió dos errores del control y desplazó '
    'diez respuestas correctas. No se justifica repetir esa grilla por sí sola. La [revisión de '
    'estructura de cambios](native-change-factorization-review.json) identifica 229 transiciones '
    'nativas sin cambio y 258 con cambio, incluidas dos negativas; confirma que los regresores '
    'continuos y la corrección de residuos anteriores no implementan un clasificador separado de '
    'cambio observado y magnitud condicional. Esa alternativa todavía no está predeclarada ni '
    'entrenada, y la revisión no demuestra una mejora de accuracy.\n\n')
path = study.DOCS/'README.md'
code = path.read_text(encoding='utf-8')
if 'La etapa 52, `causal-transition-memory-80-v1`' not in code:
    marker = '## Resultados comprobados de esta etapa\n'
    assert code.count(marker)==1
    code = code.replace(marker,paragraph+marker)
old = 'Las cincuenta y una búsquedas completas suman **1.812 configuraciones evaluadas**'
new = 'Las cincuenta y dos búsquedas completas suman **1.848 configuraciones evaluadas**'
if new not in code:
    assert code.count(old)==1
    code = code.replace(old,new)
path.write_text(code,encoding='utf-8')
print('Documented audited study52and preserved the original80percent goal',flush=True)
