# job_automation/src/job_automation/letter/letter_artifact_writer.py

from dataclasses import asdict
from pathlib import Path

from common.json_utils import save_json
from domain.models import (
    LetterContent,
    LetterContext,
)


class LetterArtifactWriter:
    def save(
        self,
        context: LetterContext,
        content: LetterContent,
        destination: Path,
    ) -> None:
        data = {
            "schema_version": 1,

            "application": {
                "application_id": (
                    context.target.application_id
                ),
                "external_id": (
                    context.target.external_id
                ),
                "source_type": (
                    context.target.source_type
                ),
                "contract_type": (
                    context.target.contract_type
                ),
            },

            "target": asdict(
                context.target
            ),

            "recipient": asdict(
                context.recipient
            ),

            "letter": {
                "subject": content.subject,
                "greeting": content.greeting,
                "paragraphs": content.paragraphs,
                "closing": content.closing,
                "signature": content.signature,
            },

            "generation": {
                "date_label": context.date_label,
                "analysis": content.analysis,
            },
        }

        save_json(
            path=destination,
            data=data,
        )