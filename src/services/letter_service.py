# job_automation/src/job_automation/services/letter_service.py

from documents.docx_letter_renderer import (
    DocxLetterRenderer,
)
from documents.pdf_letter_renderer import (
    PdfLetterRenderer,
)
from domain.models import (
    ApplicationTarget,
    LetterContent,
    LetterGenerationResult,
)
from letter.letter_artifact_writer import (
    LetterArtifactWriter,
)
from letter.letter_context import (
    LetterContextBuilder,
)
from letter.letter_generator import (
    LetterGenerator,
)
from letter.letter_validator import (
    LetterValidator,
)
from paths import ApplicationPaths


class LetterService:
    def __init__(
        self,
        context_builder: LetterContextBuilder,
        letter_generator: LetterGenerator,
        letter_validator: LetterValidator,
        pdf_renderer: PdfLetterRenderer,
        docx_renderer: DocxLetterRenderer,
        artifact_writer: LetterArtifactWriter,
        correction_attempts: int = 1,
        review: bool = False,
    ) -> None:
        self.review = review
        self.context_builder = context_builder
        self.letter_generator = letter_generator
        self.letter_validator = letter_validator
        self.pdf_renderer = pdf_renderer
        self.docx_renderer = docx_renderer
        self.artifact_writer = artifact_writer
        self.correction_attempts = correction_attempts

    def prepare(
        self,
        target: ApplicationTarget,
        cv_data: dict,
        paths: ApplicationPaths,
    ) -> LetterGenerationResult:
        print(
            f"Cible : {target.job_title} "
            f"- {target.company_name}"
        )

        print(
            f"Type : {target.contract_type}"
        )

        print(
            f"Source : {target.source_type}"
        )

        context = self.context_builder.build(
            target=target,
            cv_data=cv_data,
        )

        print(
            "\nGénération de la lettre..."
        )

        content = self.letter_generator.generate(
            context=context
        )

        self._print_analysis(content)

        if self.review:
            print(
                "\nRelecture de la lettre..."
            )

            try:
                content = self.letter_generator.review(
                    context=context,
                    content=content,
                )
            except Exception as error:
                print(
                    "ATTENTION : relecture impossible "
                    f"({error}). Le premier jet est conservé."
                )

        # Seules les erreurs bloquantes déclenchent un nouvel appel
        # payant ; les défauts de style sont signalés plus bas.
        errors = self.letter_validator.validate(
            content=content,
            context=context,
        )

        attempt = 0

        while (
            errors
            and attempt < self.correction_attempts
        ):
            attempt += 1

            print(
                f"\nCorrection automatique "
                f"{attempt}/{self.correction_attempts}..."
            )

            for error in errors:
                print(f"- {error}")

            content = self.letter_generator.correct(
                context=context,
                content=content,
                errors=errors,
            )

            errors = self.letter_validator.validate(
                content=content,
                context=context,
            )

        if errors:
            error_text = "\n".join(
                f"- {error}"
                for error in errors
            )

            raise RuntimeError(
                "La lettre reste invalide après "
                "les corrections automatiques :\n"
                f"{error_text}"
            )

        for warning in self.letter_validator.validate_style(
            content=content,
            context=context,
        ):
            print(
                f"ATTENTION (style, à relire) : {warning}"
            )

        print(
            "\nGénération du PDF..."
        )

        scale_used = (
            self.pdf_renderer.render_one_page(
                context=context,
                content=content,
                destination=paths.letter_pdf,
            )
        )

        print(
            "Génération du document Word..."
        )

        self.docx_renderer.render(
            context=context,
            content=content,
            destination=paths.letter_docx,
        )

        self.artifact_writer.save(
            context=context,
            content=content,
            destination=paths.letter_data,
        )

        return LetterGenerationResult(
            pdf_path=str(paths.letter_pdf),
            docx_path=str(paths.letter_docx),
            letter_data_path=str(
                paths.letter_data
            ),
            scale_used=scale_used,
        )

    @staticmethod
    def _print_analysis(
        content: LetterContent,
    ) -> None:
        for label, key in (
            ("Besoins identifiés", "besoins_cles"),
            ("Preuves retenues", "preuves"),
            ("Exigences couvertes", "exigences_couvertes"),
        ):
            values = content.analysis.get(key)

            if isinstance(values, list) and values:
                print(f"{label} :")

                for value in values:
                    print(f"  - {value}")

        hook = content.analysis.get("accroche")

        if hook:
            print(f"Accroche : {hook}")

        gap = content.analysis.get("ecart")

        if gap:
            print(f"Écart avec l'offre : {gap}")