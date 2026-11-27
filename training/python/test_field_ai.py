"""Causality and immutable real-data evidence. Unit fixtures never train artifacts."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
import field_ai as pipeline
import field_sources as sources

class FieldPipelineTests(unittest.TestCase):
    def test_history_excludes_current_future_other_people_and_previous_session(self):
        now=pd.Timestamp("2026-01-01T10:00:00Z")
        reports=pd.DataFrame({"id":["p1"]*5+["p2"], "time":[now-pd.Timedelta(minutes=n) for n in [0,-1,1,5,20,2]], "borg_scale":[10,9,4,3,2,8]})
        sessions={"p1":[{"start_time":str(now-pd.Timedelta(minutes=10)),"end_time":str(now+pd.Timedelta(minutes=10))}]}
        self.assertEqual(sources.source_borg_history(reports,sessions,"p1",now),{"prior_borg":4,"prior_age_minutes":1,"prior2_borg":3,"prior2_age_minutes":5})
        with self.assertRaisesRegex(ValueError,"Ambiguous"):
            sources.source_borg_history(reports,{"p1":[]},"p1",now)

    def test_canonical_denominator_labels_and_historical_split_survive(self):
        frame,provenance=sources.fatigue_dataset()
        self.assertEqual(len(frame),666)
        self.assertEqual(frame.partition.value_counts().to_dict(),{"train":487,"test":179})
        self.assertFalse(set(frame[frame.partition=="train"].person)&set(frame[frame.partition=="test"].person))
        self.assertTrue(provenance["historical_test_reused"])
        self.assertTrue(frame.prior_age_minutes.between(1,15).all())
        stored=pd.read_csv(pipeline.ROOT/"training/data/field-ai/v1/fatigue/dataset.csv")
        self.assertEqual(frame.row_key.tolist(),stored.row_key.tolist())
        self.assertEqual(frame.label.tolist(),stored.label.tolist())

    def test_trekking_target_uses_next_symptoms_not_published_future_flag(self):
        raw=(pipeline.ROOT/"training/data/raw/field-ai/boos-2018.csv").read_bytes()
        frame,provenance=sources.boos_dataset(raw)
        self.assertEqual(len(frame),377)
        self.assertEqual(provenance["audit"]["ambiguous_keys"],1)
        self.assertGreater(provenance["audit"]["published_future_disagreements"],0)
        self.assertTrue((frame.outcome_visit==frame.source_visit+1).all())
        self.assertEqual(frame.label.eq("AMS+").tolist(),((frame.future_score>=3)&(frame.future_headache>0)).tolist())
        self.assertNotIn("future_score",sources.FEATURES["ams"])
        rows=list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        for row in rows[1:]:
            if len(row)>40: row[40]="1"
        buffer=io.StringIO(); csv.writer(buffer).writerows(rows)
        changed=buffer.getvalue().encode()
        with patch.object(sources,"BOOS_SHA",hashlib.sha256(changed).hexdigest()):
            rebuilt,_=sources.boos_dataset(changed)
        pd.testing.assert_frame_equal(frame,rebuilt)
        with self.assertRaisesRegex(ValueError,"snapshot changed"):
            sources.boos_dataset(changed)

    def test_training_imputation_preserves_missingness_and_rejects_infinity(self):
        np.testing.assert_array_equal(pipeline.impute([[np.nan,8],[4,np.nan]],[2,3]),[[2,8,1,0],[4,3,0,1]])
        with self.assertRaisesRegex(ValueError,"Infinite"):
            pipeline.impute([[np.inf]],[0])

    def test_evidence_cannot_be_overwritten_and_uncertainty_is_paired_by_person(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"frozen.json"
            pipeline.write_once(path,{"a":1}); pipeline.write_once(path,{"a":1})
            with self.assertRaisesRegex(ValueError,"Frozen artifact differs"):
                pipeline.write_once(path,{"a":2})
        truth=np.array([1.,2.,3.,4.]); people=np.array(["a","a","b","b"])
        self.assertEqual(pipeline.paired_interval(truth,truth,truth+1,people,"fatigue"),{"replicates":2000,"lower":1.,"upper":1.})

    def test_frozen_selection_never_uses_test_and_folds_are_disjoint(self):
        directory=pipeline.ROOT/"training/data/field-ai/v1"
        protocol=json.loads((directory/"protocol.json").read_text())
        self.assertEqual(protocol["code_sha256"],pipeline.code_hashes())
        self.assertFalse(protocol["selection_uses_test"])
        for task in pipeline.TASKS:
            _,training,test,_=pipeline.load_task(directory,task)
            selection=json.loads((directory/task/"selection.json").read_text())
            self.assertFalse(selection["test_used_for_selection"])
            self.assertEqual(len(selection["results"]),76)
            self.assertFalse(set(training.split_group)&set(test.split_group))
            for fold in selection["folds"]:
                self.assertFalse(set(fold["train_people"])&set(fold["validation_people"]))

if __name__=="__main__": unittest.main()
