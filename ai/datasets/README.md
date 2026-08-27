# MiSendero AI datasets

This folder contains normalized CSV inputs for the offline AI training pipeline.

The project document defines three dataset families:

- Fatigue detection: PAMAP2 and WESAD-derived wearable/activity windows.
- Physiological risk: BIDMC-derived physiological records plus synthetic trekking context.

## Training pipeline

Training itself is real Python/Scikit-learn, not a JS approximation: each dataset family is
trained by a script under `training/python/<model>/train.py` using
`sklearn.ensemble.RandomForestClassifier` (50 trees, max depth 6). The fitted forest is flattened
into a plain JSON structure (`feature_order`, `classes`, and one entry per tree with
`feature`/`threshold`/`left`/`right`/`value` arrays — see `training/python/common/export_forest.py`)
so the React Native app can walk the trees on-device with no Python runtime and no network
connectivity. `ai/models/fatigueModel.json` and `ai/models/riskModel.json` are exactly that
exported structure, consumed by `ai/inferenceEngine.ts`'s `predictRandomForest`.

Route difficulty is not bundled in the app because it is fixed route metadata. Its training
pipeline lives in `training/route-difficulty/` (backed by `training/python/route_difficulty/`)
and produces a `predictions.json` file for a human/another script to apply to the backend later;
it does not write to any database itself.

## Synthetic data augmentation (documented limitation)

Each CSV here has only a handful of hand-curated real rows. This mirrors the thesis's own
documented approach (section 2.1.6.3): given no bundled access to full public datasets such as
PAMAP2, WESAD, or BIDMC in this academic prototype, real sample rows are combined with synthetic
rows sampled from Gaussian noise around each real, labeled observation before training. This is a
disclosed, intentional stand-in for real data collection, not something hidden from evaluators —
see `training/python/common/augment.py` for the implementation and rationale, and swap or extend
these CSVs with real processed exports whenever they become available.

## Regenerating the models

From the repository root, after installing the Python dependencies once
(`py -m pip install -r training/python/requirements.txt`):

```bash
npm run train:ai
```

This runs the three `train.py` scripts (fatigue, physio_risk, route_difficulty) and copies their
`model.forest.json` outputs into `ai/models/`. Each script can also be run directly, e.g.
`py training/python/fatigue/train.py`, which is useful when iterating on one model at a time; it
also writes `output/metrics.json` (accuracy, confusion matrix, per-class report) and
`output/model.joblib` (the raw fitted scikit-learn estimator) next to itself for auditability.

## Privacy requirements

Before any dataset is used for training, it must be cleaned and anonymized. Do not include
personal identifiers or exact location fields such as name, email, phone, DNI, user IDs, session
IDs, exact latitude/longitude, address, or free-text location. Each `training/python/*/train.py`
script calls `training/python/common/privacy.py`'s `assert_no_restricted_columns`, which rejects
CSVs that contain those columns, before training starts.

Physiological data such as heart rate and activity metrics is sensitive. In the app, this data is
stored locally and should only be used after explicit consent. If user-generated records are ever
exported to create new training rows, aggregate or bucket the data first and remove identifiers
before it reaches this folder.

Expected CSV schemas:

- `fatigue_windows.csv`
  - `hr`
  - `speed_kmh`
  - `elapsed_minutes`
  - `hr_reserve_percent`
  - `label` (`bajo`, `medio`, `alto`)

- `physio_risk.csv`
  - `hr`
  - `speed_kmh`
  - `elapsed_minutes`
  - `elevation_gain_m`
  - `fatigue_score`
  - `label` (`bajo`, `medio`, `alto`)

The sample rows included here let the app train and run without downloading large public
datasets during development. Replace or append rows with processed PAMAP2/WESAD and BIDMC
exports when those datasets are available locally — `augment_dataset` will use them as the real
seed points for synthetic augmentation instead of (or alongside) the current samples.

## Interpreting current metrics

The `accuracy: 1.0` values in the generated `metrics.json` files should be read as a smoke-test
result over small, separable, synthetic/augmented samples. They prove that the export, loading
and local inference pipeline is wired correctly; they are not evidence of real-world predictive
performance. For a field pilot, replace the seed CSVs with representative processed records and
report held-out metrics separately from these development fixtures.
