from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from jsonschema import validate

from src.example_boundaries import create_examples
from src.pipeline import run_request
from src.satellite import Sentinel2Analyzer
from src.watcher import process_inbox


class FakeAnalyzer:
    def analyze(self, geometry: Any) -> dict[str, Any]:
        self.geometry = geometry
        return {
            "years": [{"year": 2025, "status": "indeterminate"}],
            "crop_classification": {"status": "not_assessed"},
            "carbon_credit": {"eligible": None},
        }


class PipelineTests(unittest.TestCase):
    def test_workflow_writes_screening_report_without_satellite_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request_file = next(
                path for path in create_examples(root / "input_farmboundary")
                if path.suffix == ".geojson"
            )
            with patch("src.pipeline._log_mlflow_run"):
                result = run_request(request_file, root, analyzer=FakeAnalyzer())
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["field"]["field_id"], "synthetic_haryana_2ha")
            self.assertIsNone(report["analysis"]["carbon_credit"]["eligible"])
            self.assertIn("do not use as proof", report["limitations"][0])

    def test_csv_with_multiple_bounding_boxes_writes_each_field_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inbox = root / "input_farmboundary"
            inbox.mkdir()
            request_file = inbox / "two_fields.csv"
            request_file.write_text(
                "field_id,min_lon,min_lat,max_lon,max_lat\n"
                "field-one,76,29,76.001,29.001\n"
                "field-two,76.01,29.01,76.011,29.011\n",
                encoding="utf-8",
            )
            with patch("src.pipeline._log_mlflow_run"):
                result = run_request(request_file, root, analyzer=FakeAnalyzer())
            self.assertEqual(len(result["report_paths"]), 2)
            self.assertTrue(all(Path(path).exists() for path in result["report_paths"]))

    def test_active_screening_config_produces_schema_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request_file = next(
                path for path in create_examples(root / "input_farmboundary")
                if path.suffix == ".geojson"
            )
            analyzer = Sentinel2Analyzer()
            analyzer._observations = lambda geometry, year: ([(0.6, 0.7)], [(0.3, 0.4)], [])
            with patch("src.pipeline._log_mlflow_run"):
                result = run_request(request_file, root, analyzer=analyzer)
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            schema_path = Path(__file__).resolve().parents[1] / "data" / "schemas" / "screening_report.schema.json"
            validate(report, json.loads(schema_path.read_text(encoding="utf-8")))
            self.assertEqual(len(report["analysis"]["years"]), 5)
            self.assertEqual(
                report["analysis"]["screening_model"]["model_id"],
                "sentinel2-dnbr-screening",
            )

    def test_inbox_records_success_and_skips_duplicate_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inbox = root / "input_farmboundary"
            request_file = next(path for path in create_examples(inbox) if path.suffix == ".geojson")
            inbox_file = inbox / request_file.name
            inbox_file.write_bytes(request_file.read_bytes())
            with patch("src.pipeline._log_mlflow_run"):
                outcomes = process_inbox(inbox, root, settle_seconds=0, analyzer=FakeAnalyzer())
            self.assertEqual(outcomes[0]["status"], "succeeded")
            with patch("src.pipeline._log_mlflow_run"):
                self.assertEqual(process_inbox(inbox, root, settle_seconds=0, analyzer=FakeAnalyzer()), [])


if __name__ == "__main__":
    unittest.main()
