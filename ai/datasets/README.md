# MiSendero AI datasets

This folder contains normalized CSV inputs for the offline AI training pipeline.

The project document defines three dataset families:

- Route difficulty: real Argentine trail geometry from OpenStreetMap plus Open-Elevation-derived
  route features, labeled by a documented formula (see below - the originally planned OSM
  `sac_scale` + NASA SRTM pairing isn't usable for this project, see "Route difficulty labeling"
  below).
- Fatigue detection: PAMAP2 and WESAD-derived wearable/activity windows.
- Physiological risk: BIDMC/PhysioNet physiological records plus documented synthetic trekking
  context.

## Training pipeline

Training itself is real Python/Scikit-learn, not a JS approximation: each dataset family is
trained by a script under `training/python/<model>/train.py` using
`sklearn.ensemble.RandomForestClassifier` (200 trees, max depth 4, balanced classes). The fitted
forest is flattened into a plain JSON structure (`feature_order`, `classes`, and one entry per
tree with `feature`/`threshold`/`left`/`right`/`value` arrays - see
`training/python/common/export_forest.py`) so the React Native app can walk the trees on-device
with no Python runtime and no network connectivity.

`ai/models/fatigueModel.json` and `ai/models/riskModel.json` are exactly that exported structure,
consumed by `ai/inferenceEngine.ts`'s `predictRandomForest`.

Route difficulty is not bundled in the app because it is fixed route metadata. Its training
pipeline lives in `training/route-difficulty/` (backed by `training/python/route_difficulty/`)
and produces a `predictions.json` file for a human/another script to apply to the backend later;
it does not write to any database itself.

## Data augmentation policy

The current training flow uses the processed local CSVs that represent the sources declared in
the PFI document. It applies approved synthetic data augmentation only after the train/test split.
Generated rows are added to the training fold only; the held-out test fold remains 100% real so
reported test metrics stay auditable.

`training/python/common/augment.py` creates synthetic rows by interpolating between two real rows
of the same label (SMOTE-style) plus a small amount of deterministic Gaussian jitter. Interpolating
keeps a synthetic row inside the region real observations for that label actually span, instead of
letting one feature drift independently of the others the way plain per-feature noise around a
single row could (e.g. inventing a long route with an implausibly small elevation gain). A label
with only one real row falls back to noise-only jitter around that row, since interpolation needs
two points. Jitter is scaled from each feature's real standard deviation and clipped to physically
sane lower bounds, e.g. heart rate cannot go below 40 bpm, speed and elevation cannot become
negative, and ordinal scores keep their minimum valid value. The random seed is fixed, so
`npm run train:ai` is reproducible across machines.

`training/python/common/tuning.py` replaces a hand-picked guess for the RandomForest's
`n_estimators`/`max_depth`/`min_samples_leaf` with a small grid search, cross-validated on the real
training fold only (never the augmented rows, so a synthetic point can't leak into a different CV
split than the real row it came from). Each model's `metrics.json` records the chosen values under
`hyperparameters`, including whether cross-validation was actually used or it fell back to the
original defaults because a label had too few real rows.

Audit checklist:

- Real data is validated and anonymized first.
- Real rows are split into stratified train and test folds.
- Augmentation runs only on the training fold.
- `metrics.json` records real rows, synthetic rows, train rows after augmentation, and test rows.
- Admin-facing metrics show accuracy, precision, recall, F1, cross-validation F1, F1 gap, and
  guardrail warnings.

## Regenerating the models

From the repository root, after installing the Python dependencies once
(`py -m pip install -r training/python/requirements.txt`):

```bash
npm run train:ai
```

This runs the three `train.py` scripts (fatigue, physio_risk, route_difficulty) and copies their
`model.forest.json` and `metrics.json` outputs into `ai/models/`. Each script can also be run
directly, e.g. `py training/python/fatigue/train.py`, which is useful when iterating on one model
at a time; it also writes `output/metrics.json` (train/test accuracy, precision, recall, F1,
cross-validation, augmentation metadata, guardrail warnings, confusion matrix, per-class report)
and `output/model.joblib` (the raw fitted scikit-learn estimator) next to itself for auditability.

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

- `training/route-difficulty/datasets/route_difficulty_training.csv`
  - declared source: real Argentine trail geometry (OpenStreetMap) + Open-Elevation, labeled by a
    documented formula - see "Route difficulty labeling" below
  - `distance_km`
  - `elevation_gain_m`
  - `avg_slope_percent`
  - `max_slope_percent`
  - `technical_score`
  - `label` (`Baja`, `Media`, `Alta`)

- `fatigue_windows.csv`
  - declared source: PAMAP2 + WESAD
  - `hr`
  - `speed_kmh`
  - `elapsed_minutes`
  - `hr_reserve_percent`
  - `label` (`bajo`, `medio`, `alto`)

- `physio_risk.csv`
  - declared source: BIDMC/PhysioNet + documented synthetic physiological trekking context
  - `hr`
  - `spo2`
  - `speed_kmh`
  - `elapsed_minutes`
  - `elevation_gain_m`
  - `fatigue_score`
  - `label` (`bajo`, `medio`, `alto`)

  `spo2` was added after the first real BIDMC ingest showed the model could never predict `alto`:
  the label is partly derived from SpO2 (`spo2 < 90` / `spo2 < 94` thresholds in
  `build_datasets.py`'s `_label_risk`), but the original schema never exposed SpO2 to the
  classifier, so the exact signal that defines that minority class was invisible to it. The app
  already records `oxygen_saturation` per wearable sample (`services/wearableMetrics.ts`), so
  `ai/inferenceEngine.ts`'s `predictPhysioRisk` now takes an optional `spo2` and passes it through;
  a missing reading defaults to a normal 97%, not 0, since 0 reads as a critical desaturation
  rather than "no data". This is a breaking schema change - the placeholder seed rows predated
  `spo2` and were dropped rather than backfilled with an invented value, now that real BIDMC rows
  (which do have real SpO2) are available.

### Route difficulty labeling

The PFI document's original plan for route difficulty (OSM `sac_scale` + NASA SRTM) doesn't work in
practice: `sac_scale` tagging is dense in the Alps but sparse to nonexistent on Argentine trails
(most Argentine ways have no `sac_scale` at all), and NASA SRTM distribution requires an Earthdata
login. `build_datasets.py`'s `build_route_difficulty_from_osm` replaces both pieces with sources
that actually work for Argentina:

- **Trail geometry and names** come live from the public Overpass API
  (`https://overpass-api.de`), scoped to Argentina's main hiking regions (Bariloche/Nahuel Huapi,
  El Bolson/San Martin de los Andes, El Chalten/Los Glaciares, Cordoba sierras, Mendoza
  cordillera, Ushuaia/Tierra del Fuego - see `ARGENTINA_HIKING_REGIONS`). This is still real OSM
  data, just not relying on `sac_scale` being present; querying `highway=path` ways with a `name`
  tag keeps the result to real named trails instead of every mapped path in the country.
- **Elevation** comes from the free Open-Elevation API (point lookups against its underlying DEM),
  not SRTM. It needs no raster download or GDAL/rasterio, matching this project's otherwise light
  Python dependencies.
- Because no public labeled difficulty dataset for Argentine trails exists, `label` is computed
  from two independently documented, citable formulas instead of a human rating - a trail is only
  as easy as its hardest dimension, so the final label is whichever formula rates it higher:
  1. **Steepness** (`_slope_bucket`), inspired by the qualitative criteria of the SAC hiking scale -
     the same standard `sac_scale` encodes ([wiki.openstreetmap.org/wiki/Key:sac_scale](https://wiki.openstreetmap.org/wiki/Key:sac_scale)).
     The exact percent thresholds in the code are this project's own calibration from those
     descriptions, not official published numbers - the SAC scale's public documentation is
     qualitative, not a numeric table.
  2. **Exertion** (`_exertion_bucket`), via the Shenandoah National Park hiking-difficulty formula
     (`sqrt(elevation_gain_ft * 2 * distance_miles)`), a long-published, citable method for
     combining distance and climb into one score, adapted from its original 5-bucket scale down to
     this project's 3 labels.
  `technical_score` uses the real `sac_scale` value when an OSM way happens to have one (a
  handful do), otherwise it falls back to the same slope thresholds as the label - it is a
  best-effort numeric feature for the model, not an independently sourced rating.

Results are cached under `training/data/raw/osm_argentina/<region>.json` after the first live
fetch, so re-running the build stays offline and doesn't repeatedly hit the public APIs (delete a
region's cache file to re-fetch it). Elevation readings closer together than ~30m are dropped from
the slope calculation, and any single-segment slope over 150% is discarded as DEM/sampling noise
rather than real terrain - Open-Elevation's resolution is coarser than a purpose-built high-res
DEM, so a few meters of noise over a very short distance can otherwise read as an impossible grade.

The sample rows included here let the app train and run without downloading the full public
datasets during development. Replace or append rows with processed PAMAP2/WESAD and BIDMC/PhysioNet
exports when those datasets are available locally.

### Ingesting the raw public datasets

`training/python/build_datasets.py` reads raw downloads from `training/data/raw/` (gitignored,
never committed) and merges normalized, anonymized rows into the CSVs above. Expected layout:

- `training/data/raw/pamap2/**/*.dat` - PAMAP2 per-subject files, used as-is from the UCI archive.
- `training/data/raw/wesad/**/S*.pkl` - WESAD per-subject pickles, used as-is from the dataset
  download.
- `training/data/raw/bidmc/**/*Numerics.csv` - BIDMC per-record numerics CSVs from PhysioNet.

Run `py training/python/build_datasets.py` for a dry run (reports rows that would be added) or
add `--write` (or `npm run prepare:ai-datasets`) to update the CSVs. Only the declared feature
columns are ever copied out of the raw files - subject/record identifiers are never read into the
output, and `training/python/validate_datasets.py` (`npm run validate:privacy`) re-checks every
tracked CSV against the same anonymization rules `train.py` enforces, so a bad column is caught at
build time instead of only at training time.

## Interpreting current metrics

High `accuracy` values in the generated `metrics.json` files should be read together with
`guardrails.status`, train/test F1 gap, and cross-validation variance. The current CSVs are small,
so the metrics prove that the export, loading and local inference pipeline is wired correctly;
they are not enough evidence of real-world predictive performance. For a field pilot, replace the
seed CSVs with representative processed records and keep reporting held-out metrics.
