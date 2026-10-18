# Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG

## Intake

The inbox watcher accepts GeoJSON features/polygons, polygon shapefiles, and CSV bounding boxes. A multi-feature file produces one report per unique `field_id`. Shapefile sidecars are checked before processing; all boundaries are converted to WGS84 and their geodesic area is calculated. The API accepts GeoJSON and adds it to the same inbox.

## Satellite screening

LangGraph orchestrates boundary validation, Sentinel-2 analysis, and report generation. The analyzer queries Sentinel-2 L2A from the Planetary Computer STAC API over the last five complete calendar years. It reads B04, B08, B12, and SCL assets, masks invalid/cloud/shadow/snow pixels, and compares median NBR/NDVI before and after the seasonal window.

## Output and operations

- Per-field JSON: `outputs/farm_boundary_reports/`
- Idempotent request queue and failures: `outputs/request_queue.sqlite3`
- Local MLflow SQLite experiment/artifacts: `outputs/mlflow.db`
- Hourly polling: `python main.py --watch`
- FastAPI: `python main.py --serve`

## Interpretation limits

The output is a spectral burn-scar screening signal, not confirmation of crop-residue burning. No detected signal does not establish that burning did not occur. Crop type remains unclassified until a validated Haryana model and ground-truth data are available. No carbon-credit eligibility or emissions reduction is inferred. Every report includes these limitations.

The legacy synthetic US crop data and model under `data/` and `models/`, plus the retired `outputs/demo_report.*`, are not inputs to the new pipeline and must not be represented as Haryana validation data.

## Project capability boundary

This is a readiness-screening prototype, not a credit score or credit issuance service. The current implementation uses spectral indices and deterministic dNBR screening; learned satellite embeddings and RAG retrieval are not implemented in the measurement path. The title describes the planned RAG-ready direction, not a claim that those components already calculate farm scores.
