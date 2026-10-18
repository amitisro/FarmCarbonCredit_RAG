from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import shapefile
from pyproj import CRS, Geod, Transformer
from shapely import transform as transform_geometry
from shapely.geometry import MultiPolygon, Polygon, box, shape


_GEOD = Geod(ellps="WGS84")
_BBOX_COLUMNS = (
    ("min_lon", "min_lat", "max_lon", "max_lat"),
    ("west", "south", "east", "north"),
    ("xmin", "ymin", "xmax", "ymax"),
    ("minx", "miny", "maxx", "maxy"),
    ("left", "bottom", "right", "top"),
)


@dataclass(frozen=True)
class FieldBoundary:
    field_id: str
    source_file: Path
    geometry: Polygon | MultiPolygon
    area_ha: float


def _to_wgs84(geometry: Polygon | MultiPolygon, crs_value: str | None) -> Polygon | MultiPolygon:
    source_crs = CRS.from_user_input(crs_value or "EPSG:4326")
    target_crs = CRS.from_epsg(4326)
    if source_crs != target_crs:
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        geometry = transform_geometry(geometry, transformer.transform, interleaved=False)
    return geometry


def _boundary(
    field_id: str,
    source_file: Path,
    geometry: Any,
    crs_value: str | None = None,
) -> FieldBoundary:
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{source_file.name}: expected a Polygon or MultiPolygon boundary")
    geometry = _to_wgs84(geometry, crs_value)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"{source_file.name}: boundary is empty or invalid")
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    if min_lon < -180 or max_lon > 180 or min_lat < -90 or max_lat > 90:
        raise ValueError(f"{source_file.name}: coordinates are outside valid WGS84 bounds")
    area_m2, _ = _GEOD.geometry_area_perimeter(geometry)
    area_ha = abs(area_m2) / 10_000
    if area_ha <= 0:
        raise ValueError(f"{source_file.name}: boundary has zero area")
    if not field_id.strip():
        raise ValueError(f"{source_file.name}: field identifier is empty")
    return FieldBoundary(field_id.strip(), source_file, geometry, area_ha)


def parse_geojson(data: dict[str, Any], source_file: Path) -> list[FieldBoundary]:
    document_type = data.get("type")
    if document_type == "Feature":
        features = [data]
    elif document_type == "FeatureCollection":
        features = data.get("features", [])
    else:
        features = [{"type": "Feature", "properties": {}, "geometry": data}]
    if not features:
        raise ValueError(f"{source_file.name}: GeoJSON contains no features")

    crs_value = None
    crs_document = data.get("crs")
    if isinstance(crs_document, dict):
        properties = crs_document.get("properties", {})
        crs_value = properties.get("name")

    boundaries = []
    for index, feature in enumerate(features, start=1):
        properties = feature.get("properties") or {}
        field_id = (
            properties.get("field_id")
            or properties.get("id")
            or feature.get("id")
            or (source_file.stem if len(features) == 1 else f"{source_file.stem}-{index}")
        )
        geometry_data = feature.get("geometry")
        if not geometry_data:
            raise ValueError(f"{source_file.name}: feature {index} has no geometry")
        boundaries.append(
            _boundary(str(field_id), source_file, shape(geometry_data), crs_value)
        )
    return boundaries


def _parse_csv(source_file: Path) -> list[FieldBoundary]:
    with source_file.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"{source_file.name}: CSV has no header row")
        fieldnames = {name.strip().lower(): name for name in reader.fieldnames if name}
        bbox_columns = next(
            (columns for columns in _BBOX_COLUMNS if all(name in fieldnames for name in columns)),
            None,
        )
        if bbox_columns is None:
            expected = "min_lon,min_lat,max_lon,max_lat (or west,south,east,north)"
            raise ValueError(f"{source_file.name}: CSV must contain bounding-box columns: {expected}")

        boundaries = []
        for index, row in enumerate(reader, start=1):
            lowered = {key.strip().lower(): value for key, value in row.items() if key}
            try:
                min_x, min_y, max_x, max_y = (
                    float(lowered[fieldnames[name]]) for name in bbox_columns
                )
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"{source_file.name}: row {index} has invalid bbox values") from exc
            if min_x >= max_x or min_y >= max_y:
                raise ValueError(f"{source_file.name}: row {index} bbox must have positive width and height")
            field_id = (
                lowered.get("field_id", "")
                or lowered.get("id", "")
                or (source_file.stem if index == 1 else f"{source_file.stem}-{index}")
            )
            crs_value = (
                lowered.get("crs", "")
                or lowered.get("bbox_crs", "")
                or "EPSG:4326"
            )
            boundaries.append(
                _boundary(str(field_id), source_file, box(min_x, min_y, max_x, max_y), crs_value)
            )
        if not boundaries:
            raise ValueError(f"{source_file.name}: CSV contains no boundary rows")
        return boundaries


def _parse_shapefile(source_file: Path) -> list[FieldBoundary]:
    projection_file = source_file.with_suffix(".prj")
    crs_value = projection_file.read_text(encoding="utf-8").strip() if projection_file.exists() else None
    reader = shapefile.Reader(str(source_file), encoding="utf-8")
    try:
        fields = [field[0].lower() for field in reader.fields[1:]]
        id_field = next((name for name in ("field_id", "id") if name in fields), None)
        boundaries = []
        for index, (record, feature_shape) in enumerate(
            zip(reader.records(), reader.shapes(), strict=True), start=1
        ):
            properties = dict(zip(fields, record, strict=True))
            field_id = (
                str(properties[id_field]).strip()
                if id_field and properties.get(id_field) not in (None, "")
                else (source_file.stem if index == 1 else f"{source_file.stem}-{index}")
            )
            boundaries.append(
                _boundary(field_id, source_file, shape(feature_shape.__geo_interface__), crs_value)
            )
        if not boundaries:
            raise ValueError(f"{source_file.name}: shapefile contains no features")
        return boundaries
    finally:
        reader.close()


def parse_boundary_file(source_file: Path) -> list[FieldBoundary]:
    source_file = source_file.resolve()
    suffix = source_file.suffix.lower()
    if suffix in {".geojson", ".json"}:
        with source_file.open("r", encoding="utf-8-sig") as file:
            return parse_geojson(json.load(file), source_file)
    if suffix == ".csv":
        return _parse_csv(source_file)
    if suffix == ".shp":
        return _parse_shapefile(source_file)
    raise ValueError(f"Unsupported boundary format: {suffix or '(no extension)'}")
