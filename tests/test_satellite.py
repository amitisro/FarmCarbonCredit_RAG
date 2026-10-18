from __future__ import annotations

import unittest
from typing import Any

from shapely.geometry import box

from src.satellite import Sentinel2Analyzer


class StubAnalyzer(Sentinel2Analyzer):
    def __init__(self, observations: dict[int, tuple[list[tuple[float, float]], list[tuple[float, float]], list[str]]]) -> None:
        super().__init__()
        self.observations = observations

    def _observations(
        self, geometry: Any, year: int
    ) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[str]]:
        return self.observations[year]


class SatelliteAnalysisTests(unittest.TestCase):
    def test_single_year_signal_is_screening_only_and_not_a_credit_decision(self) -> None:
        analyzer = StubAnalyzer({2025: ([(0.6, 0.7)], [(0.3, 0.4)], [])})
        result = analyzer.analyze(box(76, 29, 76.001, 29.001), years=[2025])
        self.assertEqual(
            result["project_name"],
            "Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG",
        )
        self.assertEqual(result["screening_model"]["model_id"], "sentinel2-dnbr-screening")
        self.assertEqual(result["years"][0]["status"], "possible_burn_scar_signal")
        self.assertEqual(result["comparison"]["trend"], "single_year_only")
        self.assertEqual(result["crop_classification"]["status"], "not_assessed")
        self.assertIsNone(result["carbon_credit"]["eligible"])

    def test_unavailable_years_are_not_reported_as_no_burning(self) -> None:
        analyzer = StubAnalyzer(
            {
                2024: ([(0.6, 0.7)], [(0.58, 0.68)], []),
                2025: ([], [], []),
            }
        )
        result = analyzer.analyze(box(76, 29, 76.001, 29.001), years=[2024, 2025])
        self.assertEqual(result["years"][0]["status"], "burn_scar_not_detected")
        self.assertEqual(result["years"][1]["status"], "indeterminate")
        self.assertEqual(result["comparison"]["trend"], "mixed_or_insufficient")
        self.assertIn("does not prove", result["years"][0]["reason"])

    def test_all_missing_years_have_explicit_insufficient_data_trend(self) -> None:
        analyzer = StubAnalyzer({2024: ([], [], []), 2025: ([], [], [])})
        result = analyzer.analyze(box(76, 29, 76.001, 29.001), years=[2024, 2025])
        self.assertEqual(result["comparison"]["trend"], "insufficient_data_all_years")


if __name__ == "__main__":
    unittest.main()
