# job_automation/src/letter_builder.py

from pathlib import Path

from documents.docx_letter_renderer import (
    DocxLetterRenderer,
)
from documents.html_letter_renderer import (
    HtmlLetterRenderer,
)
from documents.pdf_letter_renderer import (
    PdfLetterRenderer,
)
from domain.models import (
    LetterContent,
    LetterContext,
)


def build_html(
    context: LetterContext,
    content: LetterContent,
    font_scale: float = 1.0,
) -> str:
    return HtmlLetterRenderer().render(
        context=context,
        content=content,
        font_scale=font_scale,
    )


def build_letter_html(
    context: LetterContext,
    content: LetterContent,
    font_scale: float = 1.0,
) -> str:
    return build_html(
        context=context,
        content=content,
        font_scale=font_scale,
    )


def fit_on_one_page(
    context: LetterContext,
    content: LetterContent,
    output_pdf: str | Path,
    output_html: str | Path | None = None,
    start_scale: float = 1.0,
    min_scale: float = 0.82,
    step: float = 0.04,
) -> float:
    # Conservé dans la signature pour la compatibilité.
    # Aucun fichier HTML n'est écrit.
    del output_html

    renderer = PdfLetterRenderer(
        html_renderer=HtmlLetterRenderer(),
    )

    return renderer.render_one_page(
        context=context,
        content=content,
        destination=Path(output_pdf),
        start_scale=start_scale,
        minimum_scale=min_scale,
        step=step,
    )


def fit_letter_on_one_page(
    context: LetterContext,
    content: LetterContent,
    output_pdf: str | Path,
    output_html: str | Path | None = None,
    start_scale: float = 1.0,
    min_scale: float = 0.82,
    step: float = 0.04,
) -> float:
    return fit_on_one_page(
        context=context,
        content=content,
        output_pdf=output_pdf,
        output_html=output_html,
        start_scale=start_scale,
        min_scale=min_scale,
        step=step,
    )


def build_docx(
    context: LetterContext,
    content: LetterContent,
    output_path: str | Path,
) -> None:
    DocxLetterRenderer().render(
        context=context,
        content=content,
        destination=Path(output_path),
    )


def build_letter_docx(
    context: LetterContext,
    content: LetterContent,
    output_path: str | Path,
) -> None:
    build_docx(
        context=context,
        content=content,
        output_path=output_path,
    )