"""Publish audited study61 results without changing its frozen experiment."""
import json
import fatigue_expanded_public_gate as study
from public_sources import digest

summary=json.loads((study.DOCS/'expanded-public-gate.json').read_text())
diagnostic=json.loads((study.DOCS/'expanded-public-gate-diagnostic.json').read_text())
assert summary['verification_sha256']==digest(study.DOCS/'expanded-public-gate-verification.json')
status=json.loads((study.DOCS/'current-research-status.json').read_text())
assert (status['completed_studies'],status['evaluated_configurations_including_controls'])==(61,1980)
by_id={r['candidate']['id']:r for r in summary['results']}
table=['| Base | Penalización | Sin fuentes | Cinco fuentes anteriores | Seis fuentes | Control mismo peso total |',
       '| --- | ---: | ---: | ---: | ---: | ---: |']
for member in ('core','cat'):
    for penalty in (1.,10.):
        part=[r for r in summary['results'] if r['candidate'].get('member')==member and r['candidate']['correction_penalty']==penalty]
        values=[next(r['accuracy_mean'] for r in part if r['candidate']['source_mode']==mode) for mode in
                ('native_only','legacy_sources','expanded_sources','matched_total_weight')]
        table.append(f"| {'MLP' if member=='core' else 'CatBoost'} | {penalty:g} | "+' | '.join(f'{v*100:.4f} %' for v in values)+' |')
oracle=diagnostic['frozen_nonzero_gate_oracle_upper_bounds']
paragraph='''La etapa 61, `expanded-public-history-gate-80-v1`, completó **24 configuraciones** del
[plan predeclarado](expanded-public-history-gate-plan.json): ocho controles heredados y dieciséis
variantes nuevas. Comparó dos bases nativas, penalizaciones 1/10 y cuatro condiciones de supervisión.
La nueva fuente aporta 410 pares originales de 19 personas; el conjunto auxiliar contiene 3.548 pares
reales. El encoder comparte solo dos antecedentes RPE y su indicador de ausencia. Las seis fuentes
conservan salidas separadas y normalizaciones propias de ajuste; las veinte entradas de historia y
fisiología nativa no se inventan para las fuentes. Las bases y las proporciones entre cambios no
nulos permanecen congeladas.

El control de cinco fuentes conserva sus pesos cuando se agrega caminata; otro control iguala el
peso auxiliar total sin agregar esa fuente. Los resultados siguientes son **accuracy exacta Borg en
CV por participante**, sobre las mismas 487 respuestas:

'''+ '\n'.join(table) + f'''

La mejor variante ampliada iguala **{summary['best_cv_accuracy']*100:.4f} %**, sin superar el control
global. [La auditoría independiente](expanded-public-gate-verification.json) reprodujo ochenta redes,
los 24 vectores OOF y los 160 archivos de fold; verificó ochenta pasos de backpropagation por red,
las pérdidas ponderadas de las seis fuentes, gradientes propios de los datos nuevos, exclusión de
etiquetas inactivas, bases congeladas y recargas que solo reciben predictores. Pasaron las siete
[pruebas con datos reales](expanded-public-gate-tests.log): **329 pruebas distintas acumuladas**.

El [diagnóstico limitado al ajuste](expanded-public-gate-diagnostic.json) compara las cuatro recetas
ampliadas con sus controles pareados y mide las pérdidas antes/después. También calcula un límite
optimista para esta familia: aun eligiendo con la respuesta real entre la predicción de cambio cero y
el cambio no nulo congelado, los máximos medios por fold serían **{oracle['core']['mean_fold_upper_accuracy']*100:.4f} %
para MLP y {oracle['cat']['mean_fold_upper_accuracy']*100:.4f} % para CatBoost**. Este cálculo usa verdad de ajuste
solo para analizar la limitación de la arquitectura; no es un modelo, una métrica conseguida ni una
predicción de test.

Ninguna receta nueva superó el umbral predeclarado de 65 % CV para otro test. Se conservan
**108/179 = 60,3352 %** verificados y la meta de **144/179** sigue pendiente. No se agruparon etiquetas,
ampliaron denominadores ni crearon observaciones sintéticas. [Resumen](expanded-public-gate.json)
y [checkpoint sin reajustes históricos](expanded-public-gate-checkpoint-integrity.log).

'''
path=study.DOCS/'README.md'
text=path.read_text(encoding='utf-8')
if 'La etapa 61, `expanded-public-history-gate-80-v1`' not in text:
    marker='## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text=text.replace(marker,paragraph+marker)
old='Las sesenta búsquedas completas suman **1.956 configuraciones evaluadas**'
new='Las sesenta y una búsquedas completas suman **1.980 configuraciones evaluadas**'
if new not in text:
    assert text.count(old)==1
    text=text.replace(old,new)
text=text.replace('Esta preparación no ajustó modelos predictivos ni abrió otro test. Se mantienen **60 estudios,',
                  'Al finalizar esta preparación, antes de la etapa 61, no se ajustaron modelos ni se abrió otro test. Se conservaron **60 estudios,')
text=text.replace('predeclarada, con controles sin fuente nueva y sin supervisión auxiliar.\n[Resumen de preparación]',
                  'predeclarada, con controles sin fuente nueva y sin supervisión auxiliar; se completó en la etapa 61.\n[Resumen de preparación]')
if 'expanded_public_gate_geometry_review' in status:
    review_path=study.DOCS/status['expanded_public_gate_geometry_review']['document']
    assert digest(review_path)==status['expanded_public_gate_geometry_review']['sha256']
    review_paragraph='''La [revisión de geometría condicional](expanded-public-gate-geometry-review.json), posterior
a la etapa 61 y limitada a las 487 respuestas de ajuste, confirma que el corrector recibe la
probabilidad total de cambio, pero no el máximo, la separación de los dos máximos, la entropía,
la esperanza del cambio, su magnitud esperada o el margen de decisión de la distribución no nula.
Se calcularon perfiles de esas seis entradas a partir de probabilidades de modelos nativos ya
congelados: OOF interno para ajuste y predicción externa por participante para validación.
Se propone un adaptador privado de seis a ocho entradas, inicialmente cero, que conserve
exactamente la inicialización anterior. La comparación requerirá diez controles y ocho recetas
nuevas; todavía no está predeclarada ni entrenada, y esta revisión no demuestra una mejora de accuracy.

'''
    if 'La [revisión de geometría condicional]' not in text:
        text=text.replace('## Resultados comprobados de esta etapa\n',review_paragraph+'## Resultados comprobados de esta etapa\n')
path.write_text(text,encoding='utf-8')
print('Documented independently audited study61 and its unchanged native-test result',flush=True)
