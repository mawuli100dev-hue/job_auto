# src/job_automation/documents/pdf_cv_renderer.py

from pathlib import Path

from pypdf import PdfReader
from xhtml2pdf import pisa

from documents.html_cv_renderer import (
    HtmlCvRenderer,
)
from domain.models import CvContent


class PdfCvRenderer:
    def __init__(
        self,
        html_renderer: HtmlCvRenderer,
    ) -> None:
        self.html_renderer = html_renderer

    def render_one_page(
        self,
        content: CvContent,
        destination: Path,
        start_scale: float = 1.15,
        minimum_scale: float = 0.83,
        step: float = 0.05,
    ) -> float:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        scale = start_scale

        while scale >= minimum_scale:
            html_content = (
                self.html_renderer.render(
                    content=content,
                    font_scale=scale,
                )
            )

            self._convert_to_pdf(
                html_content=html_content,
                destination=destination,
            )

            if self._count_pages(
                destination
            ) <= 1:
                return scale

            scale = round(
                scale - step,
                4,
            )

        html_content = self.html_renderer.render(
            content=content,
            font_scale=minimum_scale,
        )

        self._convert_to_pdf(
            html_content=html_content,
            destination=destination,
        )

        page_count = self._count_pages(
            destination
        )

        if page_count > 1:
            print(
                "ATTENTION : le CV contient encore "
                f"{page_count} pages à l'échelle minimale "
                f"{minimum_scale:.2f}."
            )

        return minimum_scale

    @staticmethod
    def _convert_to_pdf(
        html_content: str,
        destination: Path,
    ) -> None:
        with destination.open(
            mode="wb",
        ) as pdf_file:
            result = pisa.CreatePDF(
                src=html_content,
                dest=pdf_file,
                encoding="utf-8",
            )

        if result.err:
            raise RuntimeError(
                "La conversion du CV HTML interne "
                "vers PDF a échoué."
            )

    @staticmethod
    def _count_pages(
        pdf_path: Path,
    ) -> int:
        reader = PdfReader(
            str(pdf_path)
        )

        return len(reader.pages)