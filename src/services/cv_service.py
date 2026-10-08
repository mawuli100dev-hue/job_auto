# job_automation/src/job_automation/services/cv_service.py

from cv.artifact_writer import CvArtifactWriter
from cv.experience_selector import ExperienceSelector
from cv.skill_selector import SkillSelector
from cv.subtitle_generator import SubtitleGenerator
from documents.docx_cv_renderer import DocxCvRenderer
from documents.pdf_cv_renderer import PdfCvRenderer
from domain.models import (
    ApplicationTarget,
    CvContent,
    CvGenerationResult,
)
from paths import ApplicationPaths


class CvService:
    def __init__(
        self,
        subtitle_generator: SubtitleGenerator,
        experience_selector: ExperienceSelector,
        skill_selector: SkillSelector,
        pdf_renderer: PdfCvRenderer,
        docx_renderer: DocxCvRenderer,
        artifact_writer: CvArtifactWriter,
    ) -> None:
        self.subtitle_generator = subtitle_generator
        self.experience_selector = experience_selector
        self.skill_selector = skill_selector
        self.pdf_renderer = pdf_renderer
        self.docx_renderer = docx_renderer
        self.artifact_writer = artifact_writer

    def prepare(
        self,
        target: ApplicationTarget,
        experiences: list[dict],
        skills_pool: dict,
        paths: ApplicationPaths,
        top_n: int,
    ) -> CvGenerationResult:
        print(
            f"Offre ciblée : {target.job_title} "
            f"- {target.company_name}"
        )

        print(
            f"Type de candidature : "
            f"{target.contract_type}"
        )

        print(
            "\nGénération du sous-titre..."
        )

        subtitle = self.subtitle_generator.generate(
            target=target,
        )

        print(
            f"Sous-titre : {subtitle}"
        )

        print(
            "\nSélection des expériences..."
        )

        selected_experiences, diagnostics = (
            self.experience_selector.select(
                target=target,
                experiences=experiences,
                top_n=top_n,
            )
        )

        diagnostic_by_id = {
            diagnostic["id"]: diagnostic
            for diagnostic in diagnostics
        }

        for experience in selected_experiences:
            experience_id = experience.get(
                "id",
                "",
            )

            diagnostic = diagnostic_by_id.get(
                experience_id,
                {},
            )

            pinned = experience.get(
                "toujours_inclure",
                False,
            )

            if pinned:
                print(
                    f"- {experience.get('titre')} "
                    "[épinglée]"
                )
            else:
                print(
                    f"- {experience.get('titre')} "
                    f"[LLM={diagnostic.get('llm_score', 0)} "
                    f"+ bonus={diagnostic.get('bonus', 0)} "
                    f"= {diagnostic.get('final_score', 0)}]"
                )

        print(
            "\nSélection des compétences..."
        )

        skills = self.skill_selector.select(
            target=target,
            pool=skills_pool,
        )

        for category, items in skills.items():
            print(
                f"- {category} : "
                f"{', '.join(items)}"
            )

        content = CvContent(
            subtitle=subtitle,
            experiences=selected_experiences,
            skills=skills,
        )

        print(
            "\nGénération du PDF..."
        )

        scale_used = self.pdf_renderer.render_one_page(
            content=content,
            destination=paths.pdf,
        )

        print(
            "\nGénération du document Word..."
        )

        self.docx_renderer.render(
            content=content,
            destination=paths.docx,
        )

        self.artifact_writer.write_offer_snapshot(
            target=target,
            destination=paths.source_snapshot,
        )

        self.artifact_writer.write_cv_data(
            target=target,
            content=content,
            destination=paths.cv_data,
        )

        return CvGenerationResult(
            pdf_path=str(paths.pdf),
            docx_path=str(paths.docx),
            cv_data_path=str(paths.cv_data),
            scale_used=scale_used,
        )