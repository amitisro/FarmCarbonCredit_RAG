# Design-decision walkthrough

**Project:** Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG
**Decision record:** Prototype architecture, revision 1
**Status:** The title describes the research direction. The current implementation is a Sentinel-2 screening prototype: it does not yet generate satellite embeddings, run RAG retrieval, calculate a verified carbon-credit estimate, or decide eligibility.

## 1. Problem framing

The target user submits a field boundary and wants evidence about seasonal land-surface change over the last five complete years. The longer-term product could combine satellite-derived features, farmer practice evidence, and authoritative methodology documents to support a human-reviewed carbon project workflow.

The first engineering decision was to separate **observable screening evidence** from **agronomic attribution and credit accounting**. Sentinel-2 reflectance changes alone cannot establish that crop residue was burned, that a practice changed, or that emissions were avoided. Therefore, the prototype reports screening statuses and evidence, while crop classification, credit eligibility, and avoided-emissions values remain explicitly unassessed.

## 2. Decision log

| Concern | Current decision | Rationale and trade-off |
|---|---|---|
| Project maturity | Deliver a reproducible screening prototype; do not fabricate a trained model or credit score. | Provides an end-to-end intake and evidence trail now, while making missing validation data visible. |
| Boundary intake | Accept GeoJSON, ESRI Shapefile, and CSV bounding boxes; normalize to WGS84 and calculate geodesic area. | Fits the requested user workflow and common GIS exports. CRS and multi-field validation add implementation work but prevent silently mislocated fields. |
| Synthetic test data | Keep one deterministic, approximately 2 ha Haryana demo parcel in all three formats under `input_farmboundary/examples/`. | Reproducible smoke tests without pretending a generated parcel is a real farm. It remains outside the top-level watcher scan. |
| Satellite source | Search the public Microsoft Planetary Computer STAC collection `sentinel-2-l2a`. | STAC exposes collection metadata and assets through a standard API. It is external infrastructure: network, catalog availability, and asset-access failures must be surfaced. |
| Bands and QA | Use B04 (red), B08 (NIR), B12 (SWIR2), and SCL; exclude invalid, shadow, cloud, cirrus, snow/ice and unclassified SCL pixels. | Enables NDVI/NBR screening with an explicit QA mask. Remaining atmospheric, mixed-pixel, and land-management effects still require caution. |
| Temporal comparison | For each of five complete years, compare configured pre- and post-season windows; select at most three low-cloud scenes per window and take temporal medians. | Limits processing cost and reduces sensitivity to a single scene. The seasonal calendar must be locally reviewed; missing one window produces `indeterminate`, never an implicit no-burn label. |
| Screening statistic | Compute NBR = (B08 − B12)/(B08 + B12); dNBR = median(pre NBR) − median(post NBR). Emit possible signal when dNBR meets the configured threshold. | A simple interpretable baseline is easier to audit than an unvalidated opaque model. The configured 0.15 threshold is provisional and not calibrated for Haryana or carbon accounting. |
| Learned models | Do not load the legacy `crop_classifier.joblib` or `satellite_embeddings.npy`; register no production crop classifier. | Those are synthetic US-crop demonstrations, not satellite pixels or Haryana labels. Reusing them would create invalid crop predictions. |
| Embeddings | Treat time-series/pixel embeddings as a future feature extractor, not as something already computed. | Embeddings need a documented model, input preprocessing, versioned weights, training/validation data and measurable benefit over index baselines. |
| RAG | Reserve RAG for cited retrieval of approved methodology, monitoring requirements, policy documents and operator procedures. Keep it separate from sensor measurements and deterministic credit calculations. | Improves traceability for document questions without allowing generated text to become evidence or an eligibility decision. RAG is not currently on the runtime path. |
| Orchestration | Use LangGraph for explicit validate → analyze → report stages. | Makes stage boundaries and errors easier to trace. Avoids using an LLM as an orchestrator for the measurement decision. |
| API and queue | FastAPI validates/queues GeoJSON; hourly watcher hashes stable files, records status in SQLite, and avoids reprocessing identical successful requests. | Lightweight single-host prototype. SQLite is not a distributed queue; multi-worker deployments need a concurrency-tested queue/database and operational backup plan. |
| Observability | Save JSON reports and model/version/dNBR artifacts to SQLite-backed MLflow. | Reproducibility and audit metadata are available locally. Real deployment needs access controls, retention policy, backups and monitoring. |
| Carbon accounting | Return null eligibility and null avoided-emissions values. | Crediting requires an approved methodology, baseline, activity/practice evidence, uncertainty and leakage treatment, monitoring, and independent verification; spectral screening alone cannot supply them. |

## 3. Current data and model contracts

- `data/dataset_registry.json` distinguishes external Sentinel-2 inputs, farmer-supplied boundary inputs, screening outputs, and legacy synthetic artifacts.
- `data/schemas/boundary_request.schema.json` and `data/schemas/screening_report.schema.json` describe accepted geometry and report structure.
- `models/sentinel2_screening_v1.json` is the active deterministic screening configuration. Its ID, version, windows, threshold, cloud limit and observation limit are included in reports/MLflow.
- `models/model_registry.json` deliberately lists `production_crop_classifier` as null and marks the rule prototype as not locally validated.
- `tests/` validates parsing, CRS conversion, multi-field handling, queue idempotency, the conservative missing-data state and report-schema compatibility.

## 4. Proposed embedding + RAG extension (not implemented)

1. Collect authorized Haryana field boundaries, crop/residue-management labels, evidence dates, independent holdout sites and data provenance.
2. Build quality-screened Sentinel-2 seasonal time-series inputs; evaluate a documented embedding model against interpretable index baselines using spatial and temporal holdouts.
3. Store embedding model/version, preprocessing hash, source scene IDs, masks, resolution and uncertainty alongside each feature artifact.
4. Curate approved carbon methodologies and evidence requirements with source, jurisdiction, version, effective dates and licensing metadata. Build a separate RAG index over those documents.
5. Return RAG answers with exact citations and abstention when evidence is absent or superseded. Do not let retrieved/generated text alter satellite features or claim verified practice.
6. Only after independent scientific and carbon-methodology review should a separately versioned accounting engine compute a methodology-specific estimate. Retain a human approval gate and complete audit trail.

## 5. Deployment gate

Before production: establish privacy/access controls for parcel geometry, approve local seasonal windows and thresholds, obtain field validation, quantify omission/commission errors by crop/region/year, document data licensing and retention, review the carbon methodology, and load-test retry/concurrency/backup behavior. A successful unit test or a live STAC response is integration evidence, not evidence of scientific accuracy or credit eligibility.
