from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from shapely.geometry import mapping

from src.boundaries import parse_boundary_file
from src.satellite import Sentinel2Analyzer

LOGGER = logging.getLogger(__name__)


class WorkflowState(TypedDict, total=False):
    request_path: str
    boundaries: list[dict[str, Any]]
    analyses: list[dict[str, Any]]
    report_paths: list[str]
    report_path: str


def _build_graph(root: Path, analyzer: Any) -> Any:
    def validate_node(state: WorkflowState) -> dict[str, Any]:
        source = Path(state["request_path"])
        boundaries = parse_boundary_file(source)
        field_ids = [boundary.field_id for boundary in boundaries]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError(f"{source.name}: each field in a request must have a unique field_id")
        return {
            "boundaries": [
                {
                    "field_id": boundary.field_id,
                    "source_file": str(boundary.source_file),
                    "geometry": mapping(boundary.geometry),
                    "area_ha": round(boundary.area_ha, 4),
                }
                for boundary in boundaries
            ]
        }

    def analyze_node(state: WorkflowState) -> dict[str, Any]:
        from shapely.geometry import shape

        return {
            "analyses": [
                analyzer.analyze(shape(boundary["geometry"]))
                for boundary in state["boundaries"]
            ]
        }

    def save_node(state: WorkflowState) -> dict[str, Any]:
        report_directory = root / "outputs" / "farm_boundary_reports"
        report_directory.mkdir(parents=True, exist_ok=True)
        report_paths = []
        for boundary, analysis in zip(state["boundaries"], state["analyses"], strict=True):
            field_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", boundary["field_id"]).strip("._") or "field"
            geometry_digest = hashlib.sha256(
                json.dumps(boundary["geometry"], sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:12]
            report_path = report_directory / f"{field_id}_{geometry_digest}.json"
            report = {
                "field": {
                    "field_id": boundary["field_id"],
                    "source_file": boundary["source_file"],
                    "area_ha": boundary["area_ha"],
                    "geometry_wgs84": boundary["geometry"],
                },
                "analysis": analysis,
                "limitations": [
                    "Screening output only; do not use as proof of burning or no burning.",
                    "Crop classification requires locally validated reference labels and is not inferred from the legacy demo model.",
                    "No carbon-credit eligibility or emissions estimate is provided.",
                ],
            }
            temporary_path = report_path.with_suffix(".json.tmp")
            temporary_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            temporary_path.replace(report_path)
            _log_mlflow_run(root, report_path, report)
            report_paths.append(str(report_path))
        result: dict[str, Any] = {"report_paths": report_paths}
        if len(report_paths) == 1:
            result["report_path"] = report_paths[0]
        return result

    builder = StateGraph(WorkflowState)
    builder.add_node("validate_boundary", validate_node)
    builder.add_node("analyze_sentinel2", analyze_node)
    builder.add_node("save_report", save_node)
    builder.add_edge(START, "validate_boundary")
    builder.add_edge("validate_boundary", "analyze_sentinel2")
    builder.add_edge("analyze_sentinel2", "save_report")
    builder.add_edge("save_report", END)
    return builder.compile()


def _log_mlflow_run(root: Path, report_path: Path, report: dict[str, Any]) -> None:
    import mlflow

    tracking_database = root / "outputs" / "mlflow.db"
    mlflow.set_tracking_uri(f"sqlite:///{tracking_database.as_posix()}")
    mlflow.set_experiment("agricultural-field-carbon-credit-estimation-rag")
    field = report["field"]
    with mlflow.start_run(run_name=field["field_id"]):
        mlflow.log_param("field_id", field["field_id"])
        mlflow.log_param("area_ha", field["area_ha"])
        mlflow.log_param("satellite_collection", report["analysis"]["collection"])
        screening_model = report["analysis"]["screening_model"]
        mlflow.log_param("screening_model_id", screening_model["model_id"])
        mlflow.log_param("screening_model_version", screening_model["version"])
        mlflow.log_param("dnbr_threshold", screening_model["dnbr_threshold"])
        for yearly in report["analysis"]["years"]:
            if yearly["dnbr"] is not None:
                mlflow.log_metric(f"dnbr_{yearly['year']}", yearly["dnbr"])
        mlflow.log_artifact(str(report_path))


def run_request(
    request_path: Path,
    project_root: Path,
    analyzer: Any | None = None,
) -> dict[str, Any]:
    graph = _build_graph(project_root.resolve(), analyzer if analyzer is not None else Sentinel2Analyzer())
    return graph.invoke({"request_path": str(request_path.resolve())})
