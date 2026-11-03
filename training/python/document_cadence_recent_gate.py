"""Document the recent native pulse comparison and unchanged global result."""
import json
import fatigue_cadence_recent_gate as study
from public_sources import digest

summary = json.loads((study.DOCS/'cadence-recent-native-gate.json').read_text())
audit_path = study.DOCS/'cadence-recent-gate-verification.json'
assert summary['verification_sha256']==digest(audit_path)
status = json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(57,1902)
paragraph = '''La etapa 57, `cadence-recent-native-gate-80-v1`, completó **10 configuraciones**: seis
controles heredados y cuatro variantes nuevas con pulso reciente en el contexto privado nativo.
El [adaptador auditado](cadence-recent-gate-input-verification.json) verificó los valores y relojes
de los 666 casos: pulso reciente, diferencia y razón respecto del pulso anterior real. Conservó
los faltantes y todos los casos. El contexto privado pasó de 13 a 16 variables; los 851 pares
CADENCE, sus 206 pares reservados, el encoder compartido y las entradas de la fuente permanecieron
iguales. Los datos recientes del contexto nativo no se fabricaron para la fuente.

La mejor variante nueva sin fuente obtuvo **63,2090 % CV**; con fuente obtuvo **63,1877 % CV**.
El control global mantiene **63,7972 % CV**. La [auditoría](cadence-recent-gate-verification.json)
recalculó las diez métricas OOF, comprobó los veinte artefactos y reprodujo las veinte redes,
incluidos los 80 pasos reales de pérdida y backward por ajuste. Las
[seis pruebas nuevas](cadence-recent-gate-tests.log) pasaron en 9,500 segundos; se acumulan
**303 pruebas distintas**, sin volver a ejecutar todas las suites históricas. Ninguna variante
cumplió el umbral predeclarado para abrir otro test. El resultado verificado continúa en
**108/179 = 60,3352 %**; la meta de **144/179 o más** sigue pendiente.
[Resumen de la etapa](cadence-recent-native-gate.json).

El [diagnóstico de errores](cadence-recent-gate-error-diagnostic.json) muestra que CatBoost con
fuente corrigió una respuesta y empeoró otra frente al nuevo control sin fuente. Frente al control
global no corrigió errores y perdió tres aciertos. Su pérdida binaria de validación bajó ligeramente
de 0,522336 a 0,521586, lo que no mejoró la exactitud Borg. La
[revisión del residual completo](cadence-full-delta-residual-review.json) distingue los residuales
anteriores, que usaban dos antecedentes y salidas continuas externas, de una posible comparación
con pulso previo compartido, contexto reciente nativo y una salida binaria CADENCE separada.
Esa comparación todavía no está predeclarada ni entrenada. Los conteos que usan la verdad para
describir qué respuestas puede alcanzar una compuerta son diagnósticos de ajuste; no son accuracy
lograda. Todos los análisis de errores excluyen los 179 casos de test.

'''
path = study.DOCS/'README.md'
text = path.read_text(encoding='utf-8')
if 'La etapa 57, `cadence-recent-native-gate-80-v1`' not in text:
    marker = '## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text = text.replace(marker,paragraph+marker)
old = 'Las cincuenta y seis búsquedas completas suman **1.892 configuraciones evaluadas**'
new = 'Las cincuenta y siete búsquedas completas suman **1.902 configuraciones evaluadas**'
if new not in text:
    assert text.count(old)==1
    text = text.replace(old,new)
text = text.replace('Esa comparación aún no está predeclarada ni entrenada y su disponibilidad no demuestra una mejora.',
    'Esa comparación se completó en la etapa 57, documentada a continuación.')
path.write_text(text,encoding='utf-8')
print('Documented audited study57and unchanged global-control result',flush=True)
