from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.boundaries import parse_geojson
from src.watcher import process_inbox


class BoundarySubmission(BaseModel):
    field_id: str = Field(min_length=1, max_length=120)
    geometry: dict[str, Any]


def create_app(project_root: Path | None = None) -> FastAPI:
    root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    inbox = root / "input_farmboundary"
    inbox.mkdir(parents=True, exist_ok=True)
    app = FastAPI(
        title="Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG",
        description="Submit WGS84 field boundaries for queued Sentinel-2 evidence screening.",
        version="1.0.0",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/requests", status_code=202)
    def submit_boundary(submission: BoundarySubmission) -> dict[str, str]:
        feature = {
            "type": "Feature",
            "properties": {"field_id": submission.field_id},
            "geometry": submission.geometry,
        }
        try:
            parse_geojson(feature, inbox / "api-submission.geojson")
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        request_id = uuid.uuid4().hex
        target = inbox / f"api-{request_id}.geojson"
        temporary = target.with_suffix(".geojson.tmp")
        temporary.write_text(json.dumps(feature), encoding="utf-8")
        temporary.replace(target)
        return {"request_id": request_id, "status": "queued", "filename": target.name}

    @app.post("/scan")
    def scan_inbox() -> dict[str, Any]:
        return {"results": process_inbox(inbox, root)}

    @app.get("/requests")
    def list_requests() -> list[dict[str, Any]]:
        database = root / "outputs" / "request_queue.sqlite3"
        if not database.exists():
            return []
        with sqlite3.connect(database) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT source_path, status, report_path, error, updated_at "
                "FROM requests ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]

    return app
