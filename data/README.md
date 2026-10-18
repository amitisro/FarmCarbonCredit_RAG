# Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG

The current workflow consumes boundary request files from `input_farmboundary/` and public Sentinel-2 L2A observations from the Microsoft Planetary Computer STAC API. Its per-request outputs are written to `outputs/farm_boundary_reports/`; it does not train a crop classifier.

The legacy artifacts `fao_crop_reference.csv` and `satellite_embeddings.npy` remain for traceability only. The CSV contains generated synthetic US crop examples (not observed Haryana labels), and the NPY is a demonstration feature matrix. Neither file is an input to the current workflow. See `dataset_registry.json` and `schemas/` for machine-readable status and data contracts.

Never treat synthetic input examples, generated demo labels, or spectral screening output as ground truth for burning, crop class, farmer eligibility, or credits.
