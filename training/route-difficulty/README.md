# Route difficulty training

This is a separate training project for fixed route difficulty metadata.

The React Native app does not bundle this model and does not calculate route difficulty offline.
Training happens in Python (`training/python/route_difficulty/train.py`, a
`sklearn.ensemble.RandomForestClassifier`); this project's `index.js` only *applies* that trained
model to `datasets/trail_features.csv` and writes the results to `output/predictions.json`.

`index.js` does not read or write any database. The backend is being migrated to PostgreSQL, so
applying `predictions.json` to the `trails.difficulty` column is a separate, manual/future step
outside this script's scope.

## Inputs

- `datasets/route_difficulty_training.csv`: reference rows used to train the classifier (read
  directly by `training/python/route_difficulty/train.py`, augmented with synthetic rows — see
  `training/python/common/augment.py` and `ai/datasets/README.md` for the synthetic-data
  rationale — and fit with a RandomForest).
- `datasets/trail_features.csv`: route-level features evaluated against the trained model by
  `index.js`.

Both files must avoid personal data and exact user location. Route names are public route
metadata and are used only to match existing backend records.

Expected features:

- `distance_km`
- `elevation_gain_m`
- `avg_slope_percent`
- `max_slope_percent`
- `technical_score`

Labels:

- `Baja`
- `Media`
- `Alta`

## Usage

1. Train the model (from the repository root, Python dependencies installed once via
   `py -m pip install -r training/python/requirements.txt`):

   ```bash
   py training/python/route_difficulty/train.py
   ```

   This writes `training/python/route_difficulty/output/model.forest.json` (the model
   `index.js` reads), `metrics.json` (accuracy, confusion matrix, per-class report), and
   `model.joblib` (the raw fitted estimator, for auditability). `npm run train:ai` from the
   repository root runs this together with the fatigue and physio-risk models.

2. Evaluate every trail in `datasets/trail_features.csv` against the trained model:

   ```bash
   npm run train:route-difficulty
   ```

   or, from this directory:

   ```bash
   npm run predict
   ```

   This writes `output/predictions.json`, an array of `{ route_name, difficulty, confidence }`,
   and never touches any database.

Applying `output/predictions.json` to the backend's `trails.difficulty` field is intentionally out
of scope for this script — the backend's storage is being migrated in parallel, and a human (or a
separate, future script written against whatever the backend's finished schema looks like) should
review and apply the predictions.
