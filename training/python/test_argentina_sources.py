"""Source parsing and geography checks. Fixtures never enter model datasets."""
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

import argentina_sources
from argentina_sources import IgnElevationAtlas, parse_apn_page, terrain_features
from train_public import baseline_for, group_split


class ArgentinaSourceTests(unittest.TestCase):
    def test_numeric_parsers_reject_long_malformed_values_without_partial_matches(self):
        for text in ("1" * 50000 + " unknown", "1" + " " * 50000 + "unknown"):
            with self.subTest(value=text[:20]), self.assertRaises(ValueError):
                argentina_sources.distance_km(text)
            with self.subTest(value=text[:20]), self.assertRaises(ValueError):
                argentina_sources.duration_minutes(text)
        self.assertIsNone(argentina_sources.DIFFICULTY.search("Dificultad" + " " * 50000 + "unknown"))

    def test_published_units_and_compound_label_whitespace_are_preserved(self):
        self.assertEqual(argentina_sources.distance_km("Distancia: 1,5 km"), 1.5)
        self.assertEqual(argentina_sources.distance_km("500 metros"), 0.5)
        self.assertEqual(argentina_sources.duration_minutes("Duración:30 min"), 30)
        self.assertEqual(argentina_sources.duration_minutes("1:30 horas y 5 min"), 95)
        rows, discarded = self.parse('<p>Ruta A. 8 km   |   3 h / Dificultad : media / alta.</p>')
        self.assertFalse(discarded)
        self.assertEqual(rows[0]["label"], "media-alta")
        self.assertEqual(rows[0]["lineage"]["published_label"], "media / alta")

    def parse(self, html, exclusions=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source.html"
            path.write_text('<article class="content_format"><h4>Senderismo y trekking</h4>' + html + '</article>', encoding="utf-8")
            return parse_apn_page(path, "fixture", exclusions or {})

    def test_published_label_and_separate_distance_time_bases(self):
        rows, discarded = self.parse('<p>Ruta A. 1:30 horas (ida y vuelta) / 1,5 km (ida) / Dificultad alta.</p>')
        self.assertFalse(discarded)
        row = rows[0]
        self.assertEqual(row["label"], "alta")
        self.assertEqual(row["published_distance_km"], 1.5)
        self.assertEqual(row["published_duration_minutes"], 90)
        self.assertEqual(row["distance_basis_one_way"], 1)
        self.assertEqual(row["duration_basis_round_trip"], 1)
        self.assertEqual(row["distance_basis_round_trip"], 0)

    def test_ambiguous_missing_and_horseback_values_are_excluded(self):
        rows, discarded = self.parse(
            '<h5>Variantes</h5><p>4 km y 6 km / 2 h / Dificultad media.</p>'
            '<h5>Sin tiempo</h5><p>500 m (ida) / Dificultad baja.</p>'
            '<h5>Cabalgata</h5><p>30 km / 12 horas a caballo / Dificultad alta.</p>'
            '<h5>Conflicto</h5><p>1 km / 30 min / Dificultad media.</p>',
            {"Conflicto": "Source conflict"},
        )
        self.assertFalse(rows)
        self.assertEqual(len(discarded), 4)
        self.assertIn("Source conflict", [item["reason"] for item in discarded])

    def test_duplicate_html_and_compound_labels_not_coarsened(self):
        paragraph = '<p>Ruta A. 8 km / 3 h / Dificultad media/alta.</p>'
        rows, _ = self.parse(paragraph + paragraph)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "media-alta")
        self.assertEqual(rows[0]["lineage"]["published_label"], "media/alta")
        self.assertEqual(rows[0]["distance_basis_unspecified"], 1)

    def test_other_activities_do_not_supply_walking_labels(self):
        rows, _ = self.parse('<h4>Bicicleta</h4><p>Ruta ciclista. 8 km / 3 h / Dificultad alta.</p>')
        self.assertFalse(rows)

    def test_original_raster_sampling_rejects_nodata_and_missing_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            image = base / "fixture.img"
            with rasterio.open(image, "w", driver="HFA", width=2, height=2, count=1,
                               dtype="float32", crs="EPSG:4326", nodata=-999999,
                               transform=from_origin(-65, -23, 0.1, 0.1)) as ds:
                ds.write(np.array([[100, -999999], [120, 130]], dtype="float32"), 1)
            with zipfile.ZipFile(base / "fixture.zip", "w") as archive:
                archive.write(image, "fixture.img")
            with patch.object(argentina_sources, "RAW", base), IgnElevationAtlas([{"path": "fixture.zip"}]) as atlas:
                reading, tiles = atlas.sample([(-23.05, -64.95)])
                self.assertEqual(reading.tolist(), [100])
                self.assertEqual(tiles, ["fixture.zip"])
                for point in [(-23.05, -64.85), (-24, -66)]:
                    with self.assertRaisesRegex(ValueError, "never fabricate"):
                        atlas.sample([point])

    def test_dem_profile_is_independent_of_osm_node_density(self):
        class FixtureAtlas:
            def sample(self, points):
                return np.array([lon * 1000 for _, lon in points]), ["fixture"]
        sparse = [(-41, -71.5), (-41, -71.49)]
        dense = [sparse[0], (-41, -71.495), sparse[-1]]
        a, _ = terrain_features(sparse, FixtureAtlas())
        b, _ = terrain_features(dense, FixtureAtlas())
        np.testing.assert_allclose(list(a.values()), list(b.values()), rtol=1e-8, atol=1e-8)

    def test_prespecified_park_test_is_exact_and_cannot_silently_change(self):
        frame = pd.DataFrame({"group_key": [f"park-{i}" for i in range(5) for _ in range(3)],
                              "lineage": [{"park": f"p{i}"} for i in range(5) for _ in range(3)]})
        train, test = group_split(frame, {"unit": "park", "test_units": ["p4"]})
        self.assertEqual(test.tolist(), [12, 13, 14])
        self.assertEqual(len(train), 12)
        with self.assertRaisesRegex(ValueError, "absent"):
            group_split(frame, {"unit": "park", "test_units": ["unknown"]})

    def test_network_crossing_test_boundary_is_rejected(self):
        frame = pd.DataFrame({"group_key": list("abcd"), "lineage": [{"regions": ["a"]}, {"regions": ["b"]}, {"regions": ["c"]}, {"regions": ["a", "d"]}]})
        with self.assertRaisesRegex(ValueError, "crosses"):
            group_split(frame, {"unit": "region", "test_units": ["d"]})

    def test_training_baseline_tie_is_disclosed_without_selecting_on_test(self):
        training = pd.Series(["A", "B", "B", "A"])
        baseline = baseline_for(training, pd.Series(["B"] * 3))
        self.assertEqual(baseline["label"], "A")
        self.assertEqual(baseline["test_accuracy"], 0)
        self.assertEqual(baseline["tied_labels_test_accuracy"], {"A": 0.0, "B": 1.0})


if __name__ == "__main__":
    unittest.main()
