# Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG

The project is a satellite-evidence screening prototype with a RAG-ready extension path. It does not currently compute an official farm credit score, use learned satellite embeddings, or run RAG at inference.

`sentinel2_screening_v1.json` is the runtime configuration used by `src/satellite.py`. It defines the provisional dNBR threshold, cloud-cover limit, observation limit, five-year period, seasonal windows, SCL mask, and reflectance scale. Changes to this file alter the reported screening method and must be versioned and validated before deployment.

This is a deterministic spectral screening heuristic, **not** a trained ML model or a verified stubble-burning detector. `model_registry.json` intentionally has no production crop classifier. The `crop_classifier.joblib` in this directory is a retained legacy demo, trained against synthetic US-crop data; it is not loaded by the current pipeline and must not be used for Haryana predictions.

Do not estimate farmer eligibility, avoided emissions, or carbon credits from this configuration. Promotion to a validated model requires local ground truth, independent evaluation, and domain review.
