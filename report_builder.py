from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer


def build_detail_pdf(output_path: Path, repo_url: str = "") -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        name="PipelineBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        leading=14,
    )
    story = [
        Paragraph(
            "Agricultural Field Carbon Credit Estimation using coupling of Satellite Embeddings and RAG",
            styles["Title"],
        ),
        Spacer(1, 12),
        Paragraph(
            "A satellite-evidence screening prototype with an hourly boundary inbox, "
            "Sentinel-2 L2A analysis, reports, and operational tracking. RAG integration "
            "is a future extension, not part of current measurements.",
            body,
        ),
        Spacer(1, 12),
        Paragraph("Processing stages", styles["Heading2"]),
        ListFlowable(
            [
                ListItem(Paragraph(text, body))
                for text in (
                    "Validate GeoJSON, shapefile, or CSV bounding-box requests and calculate geodesic area.",
                    "Query Sentinel-2 L2A scenes for five complete years and mask invalid/cloud/shadow/snow pixels.",
                    "Compare seasonal NDVI and NBR and emit a cautious possible-burn-scar screening status.",
                    "Save a per-field JSON report and track request state and metrics locally.",
                )
            ],
            bulletType="1",
        ),
        Spacer(1, 12),
        Paragraph("Limitations", styles["Heading2"]),
        Paragraph(
            "Satellite spectral changes do not prove residue burning, and a missing signal does not prove no burning. "
            "Crop classification needs locally validated reference data. No carbon-credit eligibility or emissions "
            "reduction is estimated. Reports are screening outputs that require independent validation.",
            body,
        ),
    ]
    if repo_url:
        story.extend((Spacer(1, 12), Paragraph("Project reference", styles["Heading2"]), Paragraph(repo_url, body)))
    document.build(story)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    build_detail_pdf(project_root / "outputs" / "farm_boundary_pipeline_overview.pdf")
