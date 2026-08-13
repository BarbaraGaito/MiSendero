# Route difficulty training

This is a separate training project for fixed route difficulty metadata.

The React Native app does not bundle this model and does not calculate route difficulty offline.
This pipeline trains outside the app, predicts a difficulty label for each route, and updates
`backend/data/misendero.sqlite` in the `trails.difficulty` field.

## Inputs

- `datasets/route_difficulty_training.csv`: reference rows used to train the classifier.
- `datasets/trail_features.csv`: route-level features to apply to the backend trails.

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

From the repository root:

```bash
npm run train:route-difficulty
```

Preview changes without writing to the database:

```bash
npm --prefix training/route-difficulty run dry-run
```

The script writes the trained model only inside this project under `output/`, for auditability.
The app consumes only the updated backend route field.
