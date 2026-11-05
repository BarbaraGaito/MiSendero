"""Offline checks for CMR query construction and tile selection."""
from __future__ import annotations

import unittest
import urllib.parse

from acquire_viirs_daily_l3_event_cohort import GRANULE, cmr_query_url, safe_data_url, tile_center


class ViirsDailyL3AcquisitionTests(unittest.TestCase):
    def test_tile_center_is_inside_requested_tile(self) -> None:
        from audit_viirs_daily_l3_candidate import tile

        for tile_id in ("h12v11", "h12v12", "h12v13", "h13v11", "h13v12", "h18v09"):
            with self.subTest(tile=tile_id):
                longitude, latitude = tile_center(tile_id)
                self.assertEqual(tile(longitude, latitude), tile_id)

    def test_cmr_query_uses_product_version_date_and_tile_center(self) -> None:
        item = {"product": "VNP14A1", "date": "2025-01-05", "tile": "h12v13"}
        query = urllib.parse.parse_qs(urllib.parse.urlparse(cmr_query_url(item)).query)

        self.assertEqual(query["short_name"], ["VNP14A1"])
        self.assertEqual(query["version"], ["002"])
        self.assertEqual(query["temporal[]"], ["2025-01-05T00:00:00Z,2025-01-05T23:59:59Z"])
        self.assertNotIn("point", query)
        self.assertNotIn("producer_granule_id[]", query)
        self.assertNotIn("options[producer_granule_id][pattern]", query)

    def test_cmr_producer_id_does_not_require_h5_suffix(self) -> None:
        granule_id = "VJ214A1.A2023279.h12v12.002.2025277093953"
        self.assertIsNotNone(GRANULE.fullmatch(granule_id))
        self.assertIsNone(GRANULE.fullmatch(granule_id + ".h5"))

    def test_data_url_is_restricted_to_exact_lp_daac_file_path(self) -> None:
        item = {"product": "VJ114A1"}
        granule_id = "VJ114A1.A2023279.h12v12.002.2023280081955"
        good = ("https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/"
                f"VJ114A1.002/{granule_id}/{granule_id}.h5")
        self.assertTrue(safe_data_url(item, granule_id, good))
        self.assertFalse(safe_data_url(item, granule_id, good.replace("https://", "http://")))
        self.assertFalse(safe_data_url(item, granule_id, good.replace("data.lpdaac", "evil.example")))
        self.assertFalse(safe_data_url(item, granule_id, good + "?redirect=https://evil.example"))

    def test_rejects_invalid_tile_ids(self) -> None:
        for tile_id in ("h99v09", "h18v99", "h18v9", "h18v09/../h19v09"):
            with self.subTest(tile=tile_id), self.assertRaises(ValueError):
                tile_center(tile_id)


if __name__ == "__main__":
    unittest.main()
