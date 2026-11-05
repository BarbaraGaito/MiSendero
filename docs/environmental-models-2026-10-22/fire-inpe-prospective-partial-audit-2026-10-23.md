# INPE prospective partial observation audit

Cutoff: `2026-10-23T21:57:46Z`. Forecast windows: 8; windows with any available source file: 3; windows with at least one matured CSV date segment: 1; windows with 24 hours of matured CSV date segments: 0; detections within 10 km of full route polylines in available files: 0.

This is a partial positive-detection screen against full trail lines. Incomplete windows are not scored, and a zero count is not a verified no-fire outcome. The forecast index was sampled at route-sector centers.

Available CSVs were checked against their SHA-256 manifests. CSV date segments passing the following-day 06:00 UTC maturity rule are labeled mature; immature files contribute positive detections only. A CSV date segment is not a sensor-coverage mask, and no-detection results do not prove fire absence.
