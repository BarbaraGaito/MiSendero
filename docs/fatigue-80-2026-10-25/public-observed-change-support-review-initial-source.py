"""Profile actual public source change observations, without pooling scales."""
import json
from pathlib import Path
import numpy as np
import fatigue_observed_change_factorization as study
import fatigue_shoulder_history_inputs as source
from public_sources import digest


def review():
    inputs = study.load_inputs()
    external = inputs['source']
    assert len(external)==2336 and external.source_partition.eq('fitting').all()
    assert len(inputs['reserved_source'])==312
    assert set(external.group_key).isdisjoint(inputs['frame'].group_key)
    diagnostics_path = study.DOCS/'observed-change-stage-diagnostic.json'
    diagnostic = json.loads(diagnostics_path.read_text())
    assert diagnostic['diagnostic']=='passed' and diagnostic['new_predictive_estimator_fits']==0
    expected = {'emap':248,'worker':253,'sts':49,'resistance':866,'shoulder':920}
    assert external.groupby('source_domain').size().to_dict()==expected
    results = {}
    for domain,frame in external.groupby('source_domain'):
        current = frame[source.TARGETS[domain]].to_numpy(float)
        prior = frame[source.PRIOR].to_numpy(float)
        assert np.isfinite(current).all() and np.isfinite(prior).all()
        # Compare actual published cells at their original precision; no rounding.
        changed = current!=prior
        assert changed.any() and (~changed).any()
        results[domain] = {'original_fitting_rows':len(frame),'original_fitting_people':frame.group_key.nunique(),
            'original_current_target_column':source.TARGETS[domain],'original_prior_column':source.PRIOR,
            'actually_equal_current_and_prior_reports':int((~changed).sum()),
            'actually_different_current_and_prior_reports':int(changed.sum()),
            'actually_decreasing_reports':int((current<prior).sum()),
            'actual_second_priors':int(frame[source.SECOND].notna().sum()),
            'original_current_min':float(current.min()),'original_current_max':float(current.max()),
            'original_prior_min':float(prior.min()),'original_prior_max':float(prior.max()),
            'change_fraction':float(changed.mean())}
    assert sum(row['original_fitting_rows'] for row in results.values())==2336
    report = {'review':'passed','review_code_sha256':digest(Path(__file__)),
        'source_provenance_sha256':digest(source.DIRECTORY/'provenance.json'),
        'source_input_audit_sha256':digest(study.DOCS/'shoulder-history-input-verification.json'),
        'native_stage_diagnostic_sha256':digest(diagnostics_path),'source_domains':results,
        'actual_source_fitting_pairs':2336,'actual_source_reserved_pairs_not_used':312,
        'source_outcomes_pooled_into_native_labels':False,'source_scales_converted':False,
        'source_times_or_native_task_phases_assumed':False,'new_predictive_estimator_fits':0,
        'new_test_predictions_computed':0,'synthetic_rows':0,'next_model_comparison_predeclared':False,
        'interpretation':'Each predicate describes equality of two actually observed source reports on its '
            'original instrument and precision. Rates differ across protocols/scales and do not establish '
            'physiological equivalence or a shared native target. Separate source binary heads could be '
            'investigated for statistical representation learning; source rows must not become native '
            'Borg labels. Existing auxiliary history heads learned continuous source deltas,whereas '
            'study53native change detection is a binary task. A new comparison would need predeclared '
            'matched zero-source controls,independent target/gradient checks and complete native exact '
            'Borg evaluation. This fitting-only profile demonstrates no model improvement.'}
    output = study.DOCS/'public-observed-change-support-review.json'
    output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    review()
