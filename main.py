from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.api import create_app
from src.example_boundaries import create_examples
from src.watcher import process_inbox, watch_forever


def main() -> None:
    project_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG. "
            "Monitor field boundaries and screen Sentinel-2 evidence."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="Poll the input folder every hour.")
    mode.add_argument("--serve", action="store_true", help="Run the FastAPI service.")
    mode.add_argument("--create-examples", action="store_true", help="Create synthetic GeoJSON, CSV, and shapefile examples.")
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--settle-seconds", type=int, default=10)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    input_directory = project_root / "input_farmboundary"
    if args.create_examples:
        print(json.dumps([str(path) for path in create_examples(input_directory)], indent=2))
    elif args.watch:
        watch_forever(
            input_directory,
            project_root,
            interval_seconds=args.interval_seconds,
            settle_seconds=args.settle_seconds,
        )
    elif args.serve:
        import uvicorn

        uvicorn.run(create_app(project_root), host=args.host, port=args.port)
    else:
        results = process_inbox(
            input_directory,
            project_root,
            settle_seconds=args.settle_seconds,
        )
        print(json.dumps(results, indent=2))
        if any(result["status"] == "failed" for result in results):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
