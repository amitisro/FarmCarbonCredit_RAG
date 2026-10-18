from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

import shapefile
from pyproj import Geod


def create_examples(input_directory: Path) -> list[Path]:
    output_directory = input_directory / "examples"
    output_directory.mkdir(parents=True, exist_ok=True)
    field_id = "synthetic_haryana_2ha"
    random_generator = random.Random(20261018)
    center_lon = 76.0 + random_generator.uniform(-0.08, 0.08)
    center_lat = 29.3 + random_generator.uniform(-0.08, 0.08)

    half_width_m = 100
    half_height_m = 50
    distance_m = math.hypot(half_width_m, half_height_m)
    corner_bearings = (math.degrees(math.atan2(half_width_m, half_height_m)),
                       360 - math.degrees(math.atan2(half_width_m, half_height_m)),
                       180 + math.degrees(math.atan2(half_width_m, half_height_m)),
                       180 - math.degrees(math.atan2(half_width_m, half_height_m)))
    geod = Geod(ellps="WGS84")
    ring = [
        geod.fwd(center_lon, center_lat, bearing, distance_m)[:2]
        for bearing in corner_bearings
    ]
    ring.append(ring[0])
    coordinates = [list(point) for point in ring]
    polygon = {"type": "Polygon", "coordinates": [coordinates]}
    feature = {
        "type": "Feature",
        "properties": {
            "field_id": field_id,
            "demo": "synthetic; not a real farmer or verified parcel",
        },
        "geometry": polygon,
    }
    geojson_path = output_directory / f"{field_id}.geojson"
    geojson_path.write_text(json.dumps(feature, indent=2), encoding="utf-8")

    longitudes = [point[0] for point in coordinates[:-1]]
    latitudes = [point[1] for point in coordinates[:-1]]
    csv_path = output_directory / f"{field_id}_bbox.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("field_id", "min_lon", "min_lat", "max_lon", "max_lat", "crs"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "field_id": field_id,
                "min_lon": min(longitudes),
                "min_lat": min(latitudes),
                "max_lon": max(longitudes),
                "max_lat": max(latitudes),
                "crs": "EPSG:4326",
            }
        )

    shapefile_base = output_directory / f"{field_id}_shape"
    with shapefile.Writer(str(shapefile_base), shapeType=shapefile.POLYGON, encoding="utf-8") as writer:
        writer.field("field_id", "C", size=80)
        writer.field("demo", "C", size=80)
        writer.poly([list(reversed(coordinates))])
        writer.record(field_id, "synthetic example only")
    projection_path = shapefile_base.with_suffix(".prj")
    projection_path.write_text(
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],'
        'AUTHORITY["EPSG","4326"]]',
        encoding="ascii",
    )
    return [
        geojson_path,
        csv_path,
        shapefile_base.with_suffix(".shp"),
        shapefile_base.with_suffix(".shx"),
        shapefile_base.with_suffix(".dbf"),
        projection_path,
    ]
