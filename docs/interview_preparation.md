# Interview preparation guide

**Project:** Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG
**Purpose:** A truthful interview narrative and question bank grounded in this repository. Distinguish implemented prototype behavior from proposed embeddings/RAG/carbon accounting.

## 1. One-minute project introduction

> I built a specification-driven prototype for agricultural field evidence intake. It accepts GeoJSON, shapefiles, and bounding-box CSVs, validates and normalizes field geometry, then uses public Sentinel-2 Level-2A scenes to compare seasonal NDVI/NBR behavior over five complete years. A LangGraph workflow writes per-field JSON evidence, a SQLite request queue tracks retries, and MLflow records the screening configuration and dNBR metrics. The current burn-scar output is a provisional screening signal—not proof of stubble burning—and the system deliberately does not predict crop type, credit eligibility, or avoided emissions. Satellite embeddings and cited RAG over approved methodologies are planned extensions that require local validation and governance before any credit estimate.

Use this wording as a project explanation, not as a claim that embeddings, RAG, or verified carbon accounting are implemented.

## 2. Demo walkthrough (5–7 minutes)

1. Show the README and this project's non-goals; emphasize that carbon-credit claims are not inferred from the prototype.
2. Inspect `data/dataset_registry.json` and `models/model_registry.json`. Explain why the old generated US-crop CSV, embedding array and classifier are quarantined as legacy demos.
3. Show `input_farmboundary/examples/`: one synthetic ~2 ha Haryana parcel represented as GeoJSON, bbox CSV and shapefile. Explain that it is generated test data and deliberately lives below the watcher's top-level inbox.
4. Open `models/sentinel2_screening_v1.json`; identify the model/version, provisional threshold, temporal windows, cloud limit and max scenes.
5. Walk through boundary validation, WGS84 conversion and geodesic area in `src/boundaries.py`.
6. Explain STAC search, Sentinel-2 bands, SCL mask, seasonal medians and NBR/dNBR in `src/satellite.py`.
7. Show the report schema, one example output if available, and the MLflow run. Point out `indeterminate`, `not_assessed`, and null credit fields.
8. Run `python -m pytest` and, only with connectivity and time, the live section of `notebooks/agricultural_field_carbon_credit_sdd_deployment.ipynb`.

Do not present a `possible_burn_scar_signal` as confirmed burning or a test result as model accuracy.

## 3. Likely questions and defensible answers

### Why does this use dNBR instead of an embedding classifier today?

The repository does not contain Haryana ground-truth labels or a validated crop classifier. A simple spectral-index screen is explainable and lets the team test the intake, data-access, and reporting path without pretending synthetic US labels transfer to Haryana. The dNBR cutoff is provisional; next steps are local calibration, independent spatial/temporal holdouts, uncertainty reporting, and comparison against a documented embedding baseline.

### What evidence would show that a field was burned?

This output alone is insufficient. I would combine the satellite signal with independent field observations and suitable fire/reference evidence, account for clouds and harvest/tillage/moisture confounders, and report error rates on held-out Haryana sites. A negative screening result is not proof of no burning.

### Where do satellite embeddings and RAG fit?

Embeddings are a candidate representation for temporally aligned satellite features; they require documented weights, preprocessing, source-scene provenance and evaluation against simpler baselines. RAG should retrieve versioned, approved methodologies and evidence requirements with citations. They must remain separate: an LLM cannot turn retrieval into sensor truth, a burn label, or a credit decision.

### Why include carbon-credit estimation in the project title if it does not estimate credits?

The title states the intended research direction. The implemented scope is explicitly a screening prototype. A valid estimate requires a named approved methodology, baseline, verified practice evidence, uncertainty/leakage treatment, monitoring and independent verification; until those exist, the correct output is unassessed/null rather than an invented score.

### How is missing satellite data handled?

If usable observations are absent from either temporal window, that year becomes `indeterminate`. Failed scenes are logged and the report explains insufficient evidence; missingness is not converted into a no-burn outcome.

### What would change before multi-user production?

I would replace the single-host SQLite watcher with a concurrency-tested queue and database, add authenticated API access and role-based controls, protect parcel geometry and reports, add backup/retention and alerting, pin dependencies, and operationalize data/model version lineage.

### How would you validate a credit estimate?

First freeze a specific recognized methodology and define baseline/activity data. Then build independently verified field labels and audit inputs, quantify uncertainty and leakage, test on spatially/temporally independent parcels, document monitoring and reversal risks as applicable, and require independent validation/verification plus an authorized human approval process.

## 4. STAR-style engineering story outline

- **Situation:** Multiple geospatial file formats need a repeatable route into seasonal satellite evidence, but the existing classifier artifacts are synthetic and unsuitable for local decisions.
- **Task:** Build a traceable prototype and avoid presenting unvalidated outputs as crop labels or carbon credits.
- **Action:** Added geometry/CRS validation, a low-cloud Sentinel-2 STAC workflow, conservative missing-data states, a LangGraph pipeline, an idempotent hourly watcher, schemas, model/data registries, MLflow tracking, and an executable SDD notebook.
- **Result:** Report measurable engineering checks: parser format coverage, unit-test result, report-schema validation, and whether live STAC integration was run. Do not claim predictive performance or credit impact unless independently measured.

Replace the result with the actual test/run evidence available for the interview; do not invent accuracy, farmer outcomes, emissions reductions, or personal deployment experience.

## 5. Preparation checklist

- Be able to explain NBR/dNBR, SCL masking, seasonal windows, CRS transformation and geodesic area.
- Be ready to defend why `indeterminate` differs from `burn_scar_not_detected`.
- Know which files implement the watcher, parser, STAC processing, API, model configuration, schemas, and tests.
- State clearly that vLLM is Linux-only in the current install context; the prototype does not need an LLM to make measurement decisions.
- Separate achieved work from roadmap: embedding generation, RAG retrieval, crop classification, validated burn detection and carbon accounting are not currently implemented.
- Discuss privacy risks in parcel geometry and why authentic farm data must not be put in public Git or notebook output.
