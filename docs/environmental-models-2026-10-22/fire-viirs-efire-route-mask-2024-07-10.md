# Audit of two VIIRS passes near routes - 2024-07-10

## Result

Two public NOAA VIIRS E-FIRE I-band 375 m masks and their two GITCO geolocation files were downloaded (205,891,628 bytes total). Detailed geolocation was checked against the sampled coordinates before assigning route pixels.

| UTC pass | Nearby route | Resolved sampled vertices | Observed classes | Interpretation |
|---|---|---:|---|---|
| 04:30:30-04:31:54 | Refugio Frey | 106/106 | 46 bowtie (class 1), 60 cloud (class 4); DQF 3 and 2 | No clear-land pixel; cannot rule out fire. |
| 04:30:30-04:31:54 | Bosque Tallado | 103/103 | 30 bowtie (class 1), 73 cloud (class 4); DQF 3 and 2 | No clear-land pixel; cannot rule out fire. |
| 18:31:12-18:32:36 | Quebrada del Condorito | 127/127 | 127 cloud (class 4), DQF 2 | The pass over the JMA alert was cloud-covered at sampled vertices; observation is unknown. |
| 18:31:12-18:32:36 | Che Roga | 117/117 | 117 clear land (class 5), DQF 1 | Clear observation at sampled vertices; no fire class 7-9 was detected. |

Route points were assigned to their nearest geolocated pixel. This sample of route vertices is not an exhaustive scan of the surrounding area or a field inspection. The clear Che Roga pass is one partial negative observation from one sensor at one instant. Cloud and bowtie pixels are unknown, not negatives. One case cannot estimate precision, recall, or calibration. The JMA alert near Condorito was about 14 km from the coarse swath sample; the exact route pixels were cloud-covered, so this pass neither confirms nor refutes the alert.

## Reproduction

Downloaded files remain under 	raining/data/environmental/private/ and are not included in the repository. The private manifest records public NOAA object keys, sizes, and SHA-256 hashes. Results: [0430 UTC](fire-viirs-efire-route-mask-2024-07-10-0430-n21.json) and [1831 UTC](fire-viirs-efire-route-mask-2024-07-10-1831-n21.json).

Download script: [acquire_viirs_efire_route_screen_candidates.py](../../training/python/acquire_viirs_efire_route_screen_candidates.py). Audit script: [audit_viirs_efire_route_mask_pilot.py](../../training/python/audit_viirs_efire_route_mask_pilot.py).

`powershell
.venv-ai\Scripts\python.exe training\python\acquire_viirs_efire_route_screen_candidates.py --download
.venv-ai\Scripts\python.exe training\python\audit_viirs_efire_route_mask_pilot.py --efire <EFIRE.nc> --geolocation <GITCO.h5> --output <result.json>
`
