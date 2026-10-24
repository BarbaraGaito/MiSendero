"""Regression checks for official MODIS/VIIRS sinusoidal tile mapping."""
from __future__ import annotations

import unittest

from audit_viirs_daily_l3_candidate import tile


class ViirsDailyL3TileTests(unittest.TestCase):
    def test_origin_matches_nasa_modland_tile_calculator(self) -> None:
        # NASA's MODLAND calculator reports (0, 0) as vertical 9, horizontal 18.
        self.assertEqual(tile(0.0, 0.0), "h18v09")

    def test_barda_coordinate_maps_to_sinusoidal_tile(self) -> None:
        # Applying NASA's x=R*lambda*cos(phi), y=R*phi forward equations.
        self.assertEqual(tile(-71.5485388889, -41.9862333333), "h12v13")

    def test_boundary_tolerance_does_not_swallow_real_offsets(self) -> None:
        self.assertEqual(tile(-1e-8, 0.0), "h17v09")
        self.assertEqual(tile(1e-8, 0.0), "h18v09")
        self.assertEqual(tile(0.0, 1e-8), "h18v08")
        self.assertEqual(tile(0.0, -1e-8), "h18v09")


if __name__ == "__main__":
    unittest.main()
