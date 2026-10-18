from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.boundaries import parse_boundary_file
from src.example_boundaries import create_examples


class BoundaryParsingTests(unittest.TestCase):
    def test_examples_parse_as_three_formats(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            paths = create_examples(Path(temporary_directory))
            boundary_files = [path for path in paths if path.suffix in {".geojson", ".csv", ".shp"}]
            parsed = [parse_boundary_file(path)[0] for path in boundary_files]
            self.assertEqual(len(parsed), 3)
            self.assertTrue(all(boundary.field_id == "synthetic_haryana_2ha" for boundary in parsed))
            self.assertTrue(all(1.95 <= boundary.area_ha <= 2.05 for boundary in parsed))

    def test_bbox_csv_accepts_common_aliases_and_projected_crs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "projected.csv"
            path.write_text(
                "id,xmin,ymin,xmax,ymax,crs\nparcel-1,500000,3200000,500100,3200100,EPSG:32643\n",
                encoding="utf-8",
            )
            boundary = parse_boundary_file(path)[0]
            self.assertEqual(boundary.field_id, "parcel-1")
            self.assertAlmostEqual(boundary.area_ha, 1.0, delta=0.03)

    def test_invalid_csv_bbox_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.csv"
            path.write_text(
                "field_id,min_lon,min_lat,max_lon,max_lat\nparcel-1,76,29,75,30\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "positive width and height"):
                parse_boundary_file(path)

    def test_geojson_feature_collection_supports_multiple_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "fields.geojson"
            polygon = {
                "type": "Polygon",
                "coordinates": [[[76, 29], [76.001, 29], [76.001, 29.001], [76, 29.001], [76, 29]]],
            }
            path.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {"type": "Feature", "id": "one", "properties": {}, "geometry": polygon},
                            {"type": "Feature", "id": "two", "properties": {}, "geometry": polygon},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fields = parse_boundary_file(path)
            self.assertEqual([field.field_id for field in fields], ["one", "two"])


if __name__ == "__main__":
    unittest.main()
