from __future__ import annotations

import logging
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from shapely import transform as transform_geometry
from shapely.geometry import mapping

LOGGER = logging.getLogger(__name__)
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
DEFAULT_MODEL_CONFIG = Path(__file__).resolve().parents[1] / "models" / "sentinel2_screening_v1.json"


@dataclass(frozen=True)
class YearAnalysis:
    year: int
    status: str
    crop_classification: str
    pre_observations: int
    post_observations: int
    pre_nbr: float | None
    post_nbr: float | None
    dnbr: float | None
    pre_ndvi: float | None
    post_ndvi: float | None
    reason: str


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _scene_metrics(
    item: Any,
    geometry: Any,
    *,
    excluded_scl_classes: tuple[int, ...],
    reflectance_scale: float,
) -> tuple[float, float] | None:
    import numpy as np
    import planetary_computer
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import from_bounds, transform as window_transform

    signed_item = planetary_computer.sign(item)
    assets = signed_item.assets
    required_bands = ("B04", "B08", "B12", "SCL")
    missing = [band for band in required_bands if band not in assets]
    if missing:
        raise ValueError(f"Sentinel scene {item.id} is missing assets: {', '.join(missing)}")

    with rasterio.open(assets["B12"].href) as swir_dataset:
        left, bottom, right, top = transform_bounds(
            "EPSG:4326", swir_dataset.crs, *geometry.bounds
        )
        window = from_bounds(left, bottom, right, top, transform=swir_dataset.transform)
        window = window.round_offsets().round_lengths()
        if window.width < 1 or window.height < 1:
            return None
        swir = swir_dataset.read(1, window=window).astype("float32")
        if swir.size == 0:
            return None
        grid_transform = window_transform(window, swir_dataset.transform)
        grid_shape = swir.shape
        crs = swir_dataset.crs
        nodata = swir_dataset.nodata

    bands: dict[str, Any] = {"B12": swir}
    for name, resampling in (
        ("B04", Resampling.bilinear),
        ("B08", Resampling.bilinear),
        ("SCL", Resampling.nearest),
    ):
        with rasterio.open(assets[name].href) as dataset:
            with WarpedVRT(
                dataset,
                crs=crs,
                transform=grid_transform,
                width=grid_shape[1],
                height=grid_shape[0],
                resampling=resampling,
            ) as warped:
                bands[name] = warped.read(1).astype("float32")

    geometry_in_crs = geometry
    if str(crs) != "EPSG:4326":
        from pyproj import Transformer

        transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        geometry_in_crs = transform_geometry(geometry, transformer.transform, interleaved=False)
    inside = geometry_mask(
        [mapping(geometry_in_crs)],
        out_shape=grid_shape,
        transform=grid_transform,
        invert=True,
    )
    scl = bands["SCL"]
    valid = inside & np.isfinite(bands["B04"]) & np.isfinite(bands["B08"]) & np.isfinite(bands["B12"])
    valid &= ~np.isin(scl, excluded_scl_classes)
    if nodata is not None:
        valid &= bands["B12"] != nodata
    if not np.any(valid):
        return None

    red, nir, swir_2 = (bands[name][valid] for name in ("B04", "B08", "B12"))
    red = red / reflectance_scale
    nir = nir / reflectance_scale
    swir_2 = swir_2 / reflectance_scale
    ndvi_denom = nir + red
    nbr_denom = nir + swir_2
    ndvi_valid = np.abs(ndvi_denom) > 1e-6
    nbr_valid = np.abs(nbr_denom) > 1e-6
    if not np.any(ndvi_valid) or not np.any(nbr_valid):
        return None
    ndvi = (nir[ndvi_valid] - red[ndvi_valid]) / ndvi_denom[ndvi_valid]
    nbr = (nir[nbr_valid] - swir_2[nbr_valid]) / nbr_denom[nbr_valid]
    return float(np.median(nbr)), float(np.median(ndvi))


class Sentinel2Analyzer:
    def __init__(
        self,
        *,
        stac_url: str = STAC_URL,
        cloud_cover_limit: float | None = None,
        dnbr_threshold: float | None = None,
        config_path: Path = DEFAULT_MODEL_CONFIG,
    ) -> None:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        self.project_name = str(config["project_name"])
        self.model_id = str(config["model_id"])
        self.model_version = str(config["version"])
        self.method = str(config["method"])
        self.analysis_years = int(config["analysis_years"])
        self.max_scenes_per_window = int(config["max_scenes_per_window"])
        self.reflectance_scale = float(config["reflectance_scale"])
        self.excluded_scl_classes = tuple(int(value) for value in config["excluded_scl_classes"])
        self.pre_window = config["pre_window"]
        self.post_window = config["post_window"]
        self.stac_url = stac_url
        self.cloud_cover_limit = float(
            config["cloud_cover_limit_percent"] if cloud_cover_limit is None else cloud_cover_limit
        )
        self.dnbr_threshold = float(
            config["dnbr_threshold"] if dnbr_threshold is None else dnbr_threshold
        )
        if not 0 <= self.cloud_cover_limit <= 100:
            raise ValueError("cloud_cover_limit must be in the range 0-100")
        if not 0 <= self.dnbr_threshold <= 2:
            raise ValueError("dnbr_threshold must be in the range 0-2")
        if self.analysis_years < 1 or self.max_scenes_per_window < 1:
            raise ValueError("analysis_years and max_scenes_per_window must be positive")
        if self.reflectance_scale <= 0:
            raise ValueError("reflectance_scale must be positive")

    @staticmethod
    def _date_range(year: int, window: dict[str, str]) -> str:
        return (
            f"{year}-{window['start']}T00:00:00Z/"
            f"{year}-{window['end']}T23:59:59Z"
        )

    def _observations(self, geometry: Any, year: int) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[str]]:
        from pystac_client import Client

        client = Client.open(self.stac_url)
        before: list[tuple[float, float]] = []
        after: list[tuple[float, float]] = []
        errors: list[str] = []
        windows = (
            (self._date_range(year, self.pre_window), before),
            (self._date_range(year, self.post_window), after),
        )
        for date_range, observations in windows:
            search = client.search(
                collections=[COLLECTION],
                intersects=mapping(geometry),
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": self.cloud_cover_limit}},
                sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
                max_items=self.max_scenes_per_window,
            )
            for item in search.items():
                try:
                    metrics = _scene_metrics(
                        item,
                        geometry,
                        excluded_scl_classes=self.excluded_scl_classes,
                        reflectance_scale=self.reflectance_scale,
                    )
                except Exception as exc:
                    message = f"{item.id}: {type(exc).__name__}: {exc}"
                    errors.append(message)
                    LOGGER.warning("Could not process Sentinel-2 scene %s: %s", item.id, exc)
                    continue
                if metrics is not None:
                    observations.append(metrics)
        return before, after, errors

    def analyze(self, geometry: Any, years: list[int] | None = None) -> dict[str, Any]:
        analysis_years = years or list(
            range(date.today().year - self.analysis_years, date.today().year)
        )
        yearly: list[YearAnalysis] = []
        for year in analysis_years:
            before, after, errors = self._observations(geometry, year)
            pre_nbr = _median([row[0] for row in before])
            post_nbr = _median([row[0] for row in after])
            pre_ndvi = _median([row[1] for row in before])
            post_ndvi = _median([row[1] for row in after])
            enough_data = len(before) >= 1 and len(after) >= 1
            dnbr = round(pre_nbr - post_nbr, 4) if enough_data and pre_nbr is not None and post_nbr is not None else None
            if not enough_data:
                status = "indeterminate"
                reason = (
                    "No usable clear Sentinel-2 observations in both seasonal windows."
                    if not errors
                    else f"Insufficient observations; {len(errors)} scene(s) could not be processed."
                )
            elif dnbr is not None and dnbr >= self.dnbr_threshold:
                status = "possible_burn_scar_signal"
                reason = (
                    f"Seasonal dNBR ({dnbr:.4f}) meets the screening threshold "
                    f"({self.dnbr_threshold:.2f}); field verification is required."
                )
            else:
                status = "burn_scar_not_detected"
                reason = "The screening threshold was not met; this does not prove that burning did not occur."
            yearly.append(
                YearAnalysis(
                    year=year,
                    status=status,
                    crop_classification="not_assessed_no_validated_training_data",
                    pre_observations=len(before),
                    post_observations=len(after),
                    pre_nbr=round(pre_nbr, 4) if pre_nbr is not None else None,
                    post_nbr=round(post_nbr, 4) if post_nbr is not None else None,
                    dnbr=dnbr,
                    pre_ndvi=round(pre_ndvi, 4) if pre_ndvi is not None else None,
                    post_ndvi=round(post_ndvi, 4) if post_ndvi is not None else None,
                    reason=reason,
                )
            )

        statuses = [row.status for row in yearly]
        return {
            "project_name": self.project_name,
            "provider": "Microsoft Planetary Computer STAC",
            "collection": COLLECTION,
            "screening_model": {
                "model_id": self.model_id,
                "version": self.model_version,
                "method": self.method,
                "dnbr_threshold": self.dnbr_threshold,
                "cloud_cover_limit_percent": self.cloud_cover_limit,
                "max_scenes_per_window": self.max_scenes_per_window,
            },
            "years": [asdict(row) for row in yearly],
            "comparison": {
                "possible_burn_scar_signal_years": [
                    row.year for row in yearly if row.status == "possible_burn_scar_signal"
                ],
                "not_detected_years": [
                    row.year for row in yearly if row.status == "burn_scar_not_detected"
                ],
                "indeterminate_years": [
                    row.year for row in yearly if row.status == "indeterminate"
                ],
                "trend": (
                    "single_year_only"
                    if len(yearly) == 1
                    else "insufficient_data_all_years"
                    if statuses and all(status == "indeterminate" for status in statuses)
                    else
                    "mixed_or_insufficient"
                    if "indeterminate" in statuses
                    else "screening_signals_vary_by_year"
                    if len(set(statuses)) > 1
                    else "same_screening_result_all_years"
                ),
                "interpretation": (
                    "Sentinel-2 spectral screening only; a detected scar is not proof of stubble burning, "
                    "and no detected signal is not proof of no burning."
                ),
            },
            "crop_classification": {
                "status": "not_assessed",
                "reason": (
                    "No Haryana ground-truth labels or validated crop model are configured. "
                    "The legacy synthetic classifier is intentionally not used."
                ),
            },
            "carbon_credit": {
                "eligible": None,
                "estimated_emissions_avoided_tco2e": None,
                "reason": (
                    "No emissions or credit estimate is made from satellite screening alone. "
                    "Eligibility requires verified practices, an approved methodology, and independent validation."
                ),
            },
        }
