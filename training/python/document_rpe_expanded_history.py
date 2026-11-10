"""Document audited source expansion without claiming a new accuracy result."""
import json
import rpe_expanded_binary_history_inputs as source
from public_sources import digest

summary = json.loads((source.DOCS/'rpe-expanded-binary-history.json').read_text())
assert summary['combined_input_verification_sha256']==digest(source.DOCS/'rpe-expanded-binary-history-input-verification.json')
assert summary['source_raw_input_verification_sha256']==digest(source.AUDITS['gait_forecasting'])
assert summary['new_predictive_estimator_fits']==summary['new_test_predictions_computed']==0
paragraph = '''La preparación posterior a la etapa 60 incorporó datos originales de la segunda colección
de [RPE_Forecasting](https://github.com/sahand-hajifar/RPE_Forecasting), fijada en la revisión
`2e2233a6a755b05dc4dc0404d580d401ff7d520e`. Se recibieron únicamente los diecinueve workbooks de
ajuste, **271.700 bytes** en total, y se comprobaron sus hashes Git contra el inventario público.
Los cinco participantes reservados permanecen sin descargar. La colección del primer estudio,
normalizada por percentiles y filtrada, continúa excluida.

La [auditoría independiente de los XML originales](rpe-forecasting-history-input-verification.json)
reconstruyó las celdas de **6.147 filas de zancadas**, que no son 6.147 autoevaluaciones. Hay
**434 ensayos identificados y 432 respuestas RPE sin conflicto**. Dos ensayos contienen valores
RPE contradictorios; se conservaron en la procedencia y sus asociaciones ambiguas no se usaron
como objetivos. Cuarenta filas no tienen identificador de ensayo y tampoco se les inventó uno.
Se preservaron 167 respuestas fraccionarias sin redondear ni convertir la escala. La secuencia
usa los índices de ensayo originales y la extracción por ensayo descrita por los autores. Una
regresión de índice entre filas físicas quedó documentada; no se asumieron relojes ni edades de
respuesta, y las señales de marcha no se aprobaron como predictores anteriores a la respuesta.
El intento inicial que exigía orden físico perfecto se conserva con su log y fuente para trazabilidad.

De esas respuestas se obtuvieron **410 pares originales consecutivos**, con **388 segundos
antecedentes reales** y 22 ausentes. Hay 158 pares sin cambio y 252 con cambio. No se completaron
ensayos ausentes ni se generaron historias o etiquetas. La compatibilidad aprobada es para una
salida auxiliar separada que aprende si dos respuestas originales difieren; no autoriza mezclar
los valores de esa escala con las etiquetas Borg 0–10 nativas.

El [corpus común auditado](rpe-expanded-binary-history-input-verification.json) reúne
**3.548 pares auxiliares reales**: 2.287 de las cuatro fuentes históricas, 851 CADENCE y los
410 nuevos. Conserva **3.042 segundos antecedentes reales**, 518 registros reservados de las
fuentes ya disponibles y las reservas de cinco personas nuevas sin descargar. Cada fuente mantiene
sus valores originales y necesita su propia salida y normalización de entradas ajustada solo con
participantes de entrenamiento. No se fabricó contexto fisiológico fuente. El corpus no puede
sustituir silenciosamente los 851 pares de los modelos congelados: requiere otra comparación
predeclarada, con controles sin fuente nueva y sin supervisión auxiliar.
[Resumen de preparación](rpe-expanded-binary-history.json).

Esta preparación no ajustó modelos predictivos ni abrió otro test. Se mantienen **60 estudios,
1.956 configuraciones incluidos controles y 322 pruebas distintas acumuladas**. Los casos nativos
siguen siendo **487 de ajuste y 179 de test**; el resultado verificado continúa en
**108/179 = 60,3352 %**. La meta de al menos **144/179** permanece pendiente. El
[checkpoint de integridad](rpe-expanded-binary-history-checkpoint-integrity.log) verificó la
expansión y la conservación de los artefactos nativos sin repetir entrenamientos históricos.

'''
path = source.DOCS/'README.md'
text = path.read_text(encoding='utf-8')
if 'La preparación posterior a la etapa 60 incorporó datos originales' not in text:
    marker = '## Resultados comprobados de esta etapa\n'
    assert text.count(marker)==1
    text = text.replace(marker,paragraph+marker)
text = text.replace('No se descargaron aún los workbooks originales ni\nse aprobó su incorporación. La siguiente tarea es recuperar únicamente los diecinueve archivos\nde ajuste, comprobar sus hashes Git y verificar las respuestas originales, la escala y el orden\nreal de los ensayos.',
    'Al finalizar esa inspección inicial no se habían descargado los workbooks. La preparación\nposterior, documentada a continuación, recibió y auditó únicamente los diecinueve archivos de ajuste.')
path.write_text(text,encoding='utf-8')
print('Documented3548real auxiliary pairs with separate domains;no new model accuracy claimed',flush=True)
