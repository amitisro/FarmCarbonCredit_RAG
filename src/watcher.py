from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.pipeline import run_request

LOGGER = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".geojson", ".json", ".csv", ".shp"}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    if path.suffix.lower() == ".shp":
        for sidecar in (
            path.with_suffix(".shx"),
            path.with_suffix(".dbf"),
            path.with_suffix(".prj"),
            path.with_suffix(".cpg"),
        ):
            if sidecar.exists():
                digest.update(sidecar.name.encode())
                with sidecar.open("rb") as file:
                    for block in iter(lambda: file.read(1024 * 1024), b""):
                        digest.update(block)
    return digest.hexdigest()


def _stable(path: Path, settle_seconds: int) -> bool:
    required_files = [path]
    if path.suffix.lower() == ".shp":
        required_files.extend((path.with_suffix(".shx"), path.with_suffix(".dbf")))
        if not path.with_suffix(".prj").exists():
            LOGGER.warning("%s has no .prj; coordinates will be assumed to be EPSG:4326", path.name)
    if not all(candidate.is_file() for candidate in required_files):
        return False
    newest_update = max(candidate.stat().st_mtime for candidate in required_files)
    return time.time() - newest_update >= settle_seconds


def _connect(project_root: Path) -> sqlite3.Connection:
    database = project_root / "outputs" / "request_queue.sqlite3"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            request_key TEXT PRIMARY KEY,
            source_path TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            report_path TEXT,
            error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def process_inbox(
    input_directory: Path,
    project_root: Path,
    *,
    settle_seconds: int = 10,
    analyzer: Any | None = None,
) -> list[dict[str, Any]]:
    input_directory = input_directory.resolve()
    project_root = project_root.resolve()
    input_directory.mkdir(parents=True, exist_ok=True)
    candidates = sorted(
        (
            path
            for path in input_directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )
    outcomes: list[dict[str, Any]] = []
    with closing(_connect(project_root)) as connection:
        for source in candidates:
            if not _stable(source, settle_seconds):
                LOGGER.info("Waiting for boundary file to finish copying: %s", source.name)
                continue
            content_sha = _file_hash(source)
            request_key = hashlib.sha256(
                f"{source.resolve()}:{content_sha}".encode("utf-8")
            ).hexdigest()
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT status, updated_at FROM requests WHERE request_key = ?", (request_key,)
            ).fetchone()
            if previous and previous[0] == "succeeded":
                connection.commit()
                continue
            if previous and previous[0] == "processing":
                previous_time = datetime.fromisoformat(previous[1])
                elapsed = datetime.now(timezone.utc) - previous_time
                if elapsed.total_seconds() < 6 * 60 * 60:
                    connection.commit()
                    LOGGER.info("Request is already being processed: %s", source.name)
                    continue
            connection.execute(
                """
                INSERT INTO requests
                    (request_key, source_path, content_sha256, status, report_path, error, updated_at)
                VALUES (?, ?, ?, 'processing', NULL, NULL, ?)
                ON CONFLICT(request_key) DO UPDATE SET
                    status = 'processing', error = NULL, updated_at = excluded.updated_at
                """,
                (request_key, str(source.resolve()), content_sha, now),
            )
            connection.commit()
            try:
                state = run_request(source, project_root, analyzer)
                report_paths = state["report_paths"]
                report_value = state.get("report_path") or json.dumps(report_paths)
                connection.execute(
                    "UPDATE requests SET status = 'succeeded', report_path = ?, updated_at = ? "
                    "WHERE request_key = ?",
                    (report_value, datetime.now(timezone.utc).isoformat(), request_key),
                )
                outcomes.append(
                    {
                        "source": str(source),
                        "status": "succeeded",
                        "reports": report_paths,
                    }
                )
                LOGGER.info("Processed %s -> %s", source.name, ", ".join(report_paths))
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                connection.execute(
                    "UPDATE requests SET status = 'failed', error = ?, updated_at = ? "
                    "WHERE request_key = ?",
                    (error, datetime.now(timezone.utc).isoformat(), request_key),
                )
                outcomes.append({"source": str(source), "status": "failed", "error": error})
                LOGGER.exception("Failed to process boundary request %s", source)
            connection.commit()
    return outcomes


def watch_forever(
    input_directory: Path,
    project_root: Path,
    *,
    interval_seconds: int = 3600,
    settle_seconds: int = 10,
) -> None:
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be at least 1")
    LOGGER.info("Watching %s every %s seconds", input_directory.resolve(), interval_seconds)
    while True:
        process_inbox(input_directory, project_root, settle_seconds=settle_seconds)
        time.sleep(interval_seconds)
