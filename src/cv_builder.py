# src/cv_builder.py

from pathlib import Path

from documents.docx_cv_renderer import (
    DocxCvRenderer,
)
from documents.html_cv_renderer import (
    HtmlCvRenderer,
)
from documents.pdf_cv_renderer import (
    PdfCvRenderer,
)
from domain.models import CvContent


def build_html(
    selected_experiences: list[dict],
    competences: dict | None = None,
    sous_titre: str | None = None,
    font_scale: float = 1.0,
    margin_top_cm: float = 1.0,
    margin_side_cm: float = 1.2,
    margin_bottom_cm: float = 0.2,
) -> str:
    content = CvContent(
        subtitle=(
            sous_titre
            or "Recherche d'une opportunité en science des données"
        ),
        experiences=selected_experiences,
        skills=competences or {},
    )

    return HtmlCvRenderer().render(
        content=content,
        font_scale=font_scale,
        margin_top_cm=margin_top_cm,
        margin_side_cm=margin_side_cm,
        margin_bottom_cm=margin_bottom_cm,
    )


def fit_on_one_page(
    selected_experiences: list[dict],
    output_pdf: Path,
    output_html: Path | None = None,
    competences: dict | None = None,
    sous_titre: str | None = None,
    start_scale: float = 1.15,
    min_scale: float = 0.83,
    step: float = 0.05,
    margin_top_cm: float = 1.0,
    margin_side_cm: float = 1.2,
    margin_bottom_cm: float = 0.2,
) -> float:
    # output_html est conservé dans la signature pour ne pas
    # casser les anciens imports. Aucun fichier HTML n'est écrit.
    del output_html
    del margin_top_cm
    del margin_side_cm
    del margin_bottom_cm

    content = CvContent(
        subtitle=(
            sous_titre
            or "Recherche d'une opportunité en science des données"
        ),
        experiences=selected_experiences,
        skills=competences or {},
    )

    renderer = PdfCvRenderer(
        html_renderer=HtmlCvRenderer(),
    )

    return renderer.render_one_page(
        content=content,
        destination=Path(output_pdf),
        start_scale=start_scale,
        minimum_scale=min_scale,
        step=step,
    )


def build_docx(
    selected_experiences: list[dict],
    output_path: Path,
    competences: dict | None = None,
    sous_titre: str | None = None,
) -> None:
    content = CvContent(
        subtitle=(
            sous_titre
            or "Recherche d'une opportunité en science des données"
        ),
        experiences=selected_experiences,
        skills=competences or {},
    )

    DocxCvRenderer().render(
        content=content,
        destination=Path(output_path),
    )