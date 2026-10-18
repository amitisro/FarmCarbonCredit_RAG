# Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG

**Current implementation status:** research prototype. It does not yet calculate a verified carbon-credit estimate or eligibility score. The implemented pipeline screens Sentinel-2 spectral indices; satellite embeddings and RAG are documented as design extensions, not live inference features.

Project documents: [SDD deployment notebook](./notebooks/agricultural_field_carbon_credit_sdd_deployment.ipynb), [design-decision walkthrough](./docs/design_decision_walkthrough.md), and [interview preparation guide](./docs/interview_preparation.md).

This project monitors `input_farmboundary/` for new field boundaries and screens public Sentinel-2 Level-2A observations. It accepts GeoJSON, ESRI Shapefile components kept together (`.shp`, `.shx`, `.dbf`, and preferably `.prj`), and CSV bounding boxes. CSVs may use `min_lon,min_lat,max_lon,max_lat`, `west,south,east,north`, `xmin,ymin,xmax,ymax`, `minx,miny,maxx,maxy`, or `left,bottom,right,top`. A CSV may specify `crs` or `bbox_crs`; otherwise coordinates are assumed to be EPSG:4326.

A GeoJSON FeatureCollection, shapefile with multiple polygon records, or CSV with multiple bbox rows produces one report per unique `field_id`.

## Install

Use Python 3.10 or later in a virtual environment. From PowerShell:

```powershell
git clone https://github.com/amitisro/FarmCarbonCredit_RAG.git
cd FarmCarbonCredit_RAG
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Open `notebooks/agricultural_field_carbon_credit_sdd_deployment.ipynb` in Jupyter for the requirements-to-deployment trace, format checks, automated acceptance tests, and optional live Sentinel-2/MLflow run.

The `vllm` package is included only on Linux; it is not supported on native Windows. On Windows, run the remaining pipeline and use a Linux/WSL deployment for vLLM model serving if needed.

## Make the three synthetic format examples

```powershell
python main.py --create-examples
```

This creates one synthetic approximately 2-hectare field in Haryana as GeoJSON, a CSV bounding box, and a shapefile in `input_farmboundary/examples/`. These are test fixtures, not a real farmer's parcel. The watcher only scans the top level of `input_farmboundary/`, so the examples are not submitted automatically. Copy a request and, for shapefiles, all sidecar files into the top-level inbox when ready.

## Process and schedule requests

Process files already in the inbox once:

```powershell
python main.py
```

Continuously poll the inbox once per hour (the default):

```powershell
python main.py --watch
```

Keep the process running for hourly polling. For a different interval, pass `--interval-seconds`. Files are processed only after their modification time is older than the copy-settling interval (`--settle-seconds`, default 10). Successfully processed identical file contents are not processed twice. Failed requests are recorded and retried on the next scan.

Run the optional API, which queues GeoJSON submissions and provides a manual inbox scan:

```powershell
python main.py --serve
```

Endpoints: `GET /health`, `POST /requests`, `POST /scan`, and `GET /requests`. The interactive API schema is at `http://127.0.0.1:8000/docs`.

## What the analysis does

- Reads and validates polygon geometry, converts it to WGS84, and records geodesic area.
- Searches the Microsoft Planetary Computer STAC catalog for Sentinel-2 L2A scenes for the last five complete calendar years.
- Selects up to three low-cloud scenes for each pre/post seasonal window (September 15–October 15 and October 16–November 30), masks clouds/shadows/snow with the Scene Classification Layer, and computes median NDVI, NBR, and seasonal dNBR.
- Labels a year `possible_burn_scar_signal`, `burn_scar_not_detected`, or `indeterminate`; all years are compared in a JSON report under `outputs/farm_boundary_reports/`.
- Records metrics and the report artifact in the `agricultural-field-carbon-credit-estimation-rag` MLflow experiment in `outputs/mlflow.db`. Request status and errors are persisted in `outputs/request_queue.sqlite3`.

Run tests without fetching satellite scenes:

```powershell
python -m pytest
```

## Important scientific and credit limitations

The title describes the research direction, not a completed estimation model. This release uses Sentinel-2 spectral indices and a deterministic dNBR rule. Satellite embeddings, crop classification, RAG retrieval, and numerical carbon-credit estimation are planned extensions and are not currently implemented in the inference path.

This is a **screening prototype**, not a validated stubble-burning detector or crop classifier. Sentinel-2 NBR changes can be caused by harvest, tillage, moisture, clouds, or other land-cover changes; Sentinel-2 does not by itself confirm a fire. `burn_scar_not_detected` does not mean that burning did not happen. The crop-classification output is explicitly `not_assessed` until Haryana ground-truth labels and a validated model are supplied. The old generated FAO-style sample, classifier model, and `outputs/demo_report.*` are retired synthetic US-crop demo artifacts; their former accuracy figures are not Haryana or Sentinel-2 validation results and are not consumed by this pipeline.

No emissions reduction, farmer eligibility, or carbon-credit claim is calculated. Credit issuance requires a specific approved methodology, credible baseline and practice evidence, uncertainty accounting, and independent verification. Validate detections against field observations and, where appropriate, independent fire evidence (for example, NASA FIRMS) before any such use.

The LLM/RAG packages in `requirements.txt` are available for future documentation and operator-assistance work, but are intentionally not put in the measurement or credit decision path. This avoids fabricating crop labels or letting an LLM make an environmental/financial eligibility decision. Ragas is not currently used to validate satellite measurements.
