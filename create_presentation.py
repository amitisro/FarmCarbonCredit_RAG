from __future__ import annotations

from pathlib import Path

from report_builder import build_detail_pdf


def build_presentation(project_root: Path) -> Path:
    output_path = project_root / "outputs" / "farm_boundary_pipeline_overview.pdf"
    build_detail_pdf(output_path)
    return output_path


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    print(f"Presentation created: {build_presentation(root)}")
