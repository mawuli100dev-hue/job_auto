# job_automation/src/job_automation/documents/pdf_letter_renderer.py

from pathlib import Path

from pypdf import PdfReader
from xhtml2pdf import pisa

from documents.html_letter_renderer import (
    HtmlLetterRenderer,
)
from domain.models import (
    LetterContent,
    LetterContext,
)


class PdfLetterRenderer:
    def __init__(
        self,
        html_renderer: HtmlLetterRenderer,
    ) -> None:
        self.html_renderer = html_renderer

    def render_one_page(
        self,
        context: LetterContext,
        content: LetterContent,
        destination: Path,
        start_scale: float = 1.0,
        minimum_scale: float = 0.82,
        step: float = 0.04,
    ) -> float:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        scale = start_scale

        while scale >= minimum_scale:
            html_content = (
                self.html_renderer.render(
                    context=context,
                    content=content,
                    font_scale=scale,
                )
            )

            self._convert(
                html_content=html_content,
                destination=destination,
            )

            if self._page_count(
                destination
            ) <= 1:
                return scale

            scale = round(
                scale - step,
                4,
            )

        final_html = self.html_renderer.render(
            context=context,
            content=content,
            font_scale=minimum_scale,
        )

        self._convert(
            html_content=final_html,
            destination=destination,
        )

        number_of_pages = self._page_count(
            destination
        )

        if number_of_pages > 1:
            print(
                "ATTENTION : la lettre contient encore "
                f"{number_of_pages} pages."
            )

        return minimum_scale

    @staticmethod
    def _convert(
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
                "La conversion de la lettre en PDF "
                "a échoué."
            )

    @staticmethod
    def _page_count(
        destination: Path,
    ) -> int:
        reader = PdfReader(
            str(destination)
        )

        return len(reader.pages)