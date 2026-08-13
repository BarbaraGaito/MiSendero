# MiSendero AI datasets

This folder contains normalized CSV inputs for the offline AI training pipeline.

The project document defines three dataset families:

- Route difficulty: OpenStreetMap route attributes plus NASA SRTM elevation features.
- Fatigue detection: PAMAP2 and WESAD-derived wearable/activity windows.
- Physiological risk: BIDMC-derived physiological records plus synthetic trekking context.

For this app MVP, the training script consumes compact CSV files with the same feature
families and produces small JSON models under `ai/models/`. Those JSON files are imported by
the React Native app and run fully offline.

## Privacy requirements

Before any dataset is used for training, it must be cleaned and anonymized. Do not include
personal identifiers or exact location fields such as name, email, phone, DNI, user IDs, session
IDs, exact latitude/longitude, address, or free-text location. The training script rejects CSVs
that contain those columns.

Physiological data such as heart rate and activity metrics is sensitive. In the app, this data is
stored locally and should only be used after explicit consent. If user-generated records are ever
exported to create new training rows, aggregate or bucket the data first and remove identifiers
before it reaches this folder.

Expected CSV schemas:

- `route_difficulty.csv`
  - `distance_km`
  - `elevation_gain_m`
  - `avg_slope_percent`
  - `max_slope_percent`
  - `technical_score`
  - `label` (`Baja`, `Media`, `Alta`)

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

To regenerate the offline models:

```bash
npm run train:ai
```

The sample rows included here let the app train and run without downloading large public
datasets during development. Replace or append rows with processed OSM/SRTM, PAMAP2/WESAD,
and BIDMC exports when those datasets are available locally.
