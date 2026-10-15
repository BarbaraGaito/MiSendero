# Route difficulty: public-label research evaluation

The current evaluation is produced by `training/python/train_public.py --model route_difficulty` (or root `npm run train:route-difficulty`). It reads original OSM API snapshots and IGN MDE-Ar 30 m raster tiles. It retains mapper-published `sac_scale` labels and derives geometry/elevation predictors from complete public sources. Untagged ways or missing raster coverage are excluded. There is no slope/exertion-derived label or technical-score feature.

Complete regions, connected paths, equal names and shared relations stay together in both the held-out split and training-only grouped CV. Ushuaia and Mendoza are reserved in the source catalog; other regions are used for training/CV. Original raw files are pinned by SHA-256. Research artifacts are under `training/data/public/route_difficulty/`; validation recomputes scores from original labels and saved predictions.

The current forest is not approved for predicting route difficulty in the product. It reaches 47/49 test matches versus 46/49 for the majority-label baseline; macro F1 is 0.276. Its labels describe segment sac_scale values. The separate `npm run train:apn-difficulty` evaluates 52 complete routes against official APN difficulty labels, without converting between tasks. `index.js` rejects the historical unapproved model before writing predictions. No predictions are applied to a database.

The former trainer/datasets/output are retained solely as prototype audit evidence and cannot be retrained. See `ai/datasets/README.md` and `docs/datasets-argentina-2026-10-14.md` for source attribution, limitations and reproducible commands.
