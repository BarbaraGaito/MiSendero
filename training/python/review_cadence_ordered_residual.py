"""Fitting-only evidence and fixed mathematical basis for a smaller residual."""
import json
from pathlib import Path
import numpy as np
import fatigue_cadence_delta_regularization as study
from public_sources import digest


def review():
    path = study.DIRECTORY/'selection.json'
    audit_path = study.DOCS/'cadence-delta-regularization-verification.json'
    diagnostic_path = study.DOCS/'cadence-delta-regularization-generalization-diagnostic.json'
    audit = json.loads(audit_path.read_text())
    diagnostic = json.loads(diagnostic_path.read_text())
    assert audit['verification']=='passed' and audit['selection_sha256']==digest(path)
    assert diagnostic['diagnostic']=='passed' and diagnostic['verification_sha256']==digest(audit_path)
    assert diagnostic['selection_sha256']==digest(path) and diagnostic['new_test_predictions_computed']==0
    assert diagnostic['diagnostic_code_sha256']==digest(Path(__file__).with_name('diagnose_cadence_delta_regularization_generalization.py'))
    delta = np.arange(-10,11,dtype=float)
    raw = np.column_stack([delta,delta**2,delta==0])
    centered = raw-raw.mean(axis=0,keepdims=True)
    q,_ = np.linalg.qr(centered,mode='reduced')
    basis = q*np.sqrt(21.)
    np.testing.assert_allclose(basis.mean(axis=0),0.,atol=1e-12)
    np.testing.assert_allclose(basis.T@basis/21.,np.eye(3),atol=1e-12)
    assert np.linalg.matrix_rank(centered)==3
    reconstructed = basis@(basis.T@centered/21.)
    np.testing.assert_allclose(reconstructed,centered,atol=1e-12)
    prior = Path(__file__).parent
    reviewed = ['fatigue_emap_ordered_functions.py','fatigue_spectral_correction.py',
        'fatigue_cadence_binary_gate.py','fatigue_cadence_full_delta.py','fatigue_cadence_delta_regularization.py']
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'selection_sha256':digest(path),'verification_sha256':digest(audit_path),'diagnostic_sha256':digest(diagnostic_path),
        'reviewed_implementation_sha256':{name:digest(prior/name) for name in reviewed},
        'original_fitting_queries':487,'original_fitting_people':28,
        'evidence':'Cat/source penalty100 recovered18/lost7vs penalty1,but corrected0/lost1vs global. '
            'Its validation NLL.891629568 is nearly identical to original.891629768. '
            'Core prefers10to100. Strong shrinkage mainly restores the old baseline.',
        'existing_methods':{'emap_ordered_functions':'separate observed source-order teacher regressors;no native delta-logit basis',
            'spectral_residual':'nested residual-class classifier;no fixed smooth native delta-logit basis',
            'cadence_binary_gate':'one scalar change/no-change gate with frozen nonzero ratios',
            'cadence_full_delta':'free centered21-logit residual with189last-layer parameters'},
        'proposed_residual':{'coefficient_outputs':3,'logit_outputs':21,'last_layer_parameters':27,
            'basis_span':['integer_delta','integer_delta_squared','zero_delta_indicator'],
            'basis_convention':'center columns;reduced QR;scale Q by sqrt21 for uniform orthonormality',
            'basis':basis.tolist(),'basis_rank':3,'expanded_l2_equals_coefficient_l2':True,
            'shared_numeric_and_missing_inputs':11,'native_private_features':16,
            'source_actual_binary_pairs':851,'source_reserved_pairs_not_fitted':206,
            'base_weights_remain_frozen':True,'nonzero_relative_probabilities_may_change':True},
        'basis_is_class_geometry_not_training_observations_or_targets':True,
        'model_comparison_predeclared':False,'new_predictive_estimator_fits':0,
        'new_test_predictions_computed':0,'test_labels_inspected':False,'synthetic_rows':0,
        'interpretation':'A small smooth residual can alter magnitude and zero-change mass while reducing '
            'output degrees of freedom. This is an untrained design rationale,not evidence of improved '
            'accuracy. Preserve source-zero controls,exact native labels and unchanged public datasets; '
            'predeclare penalties and compare against scalar/full/native controls before fitting.'}
    output = study.DOCS/'cadence-ordered-residual-review.json'
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='proposed_residual'}),flush=True)
    return report


if __name__=='__main__':
    review()
