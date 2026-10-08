# src/documents/html_cv_renderer.py

"""
Rendu HTML du CV (converti ensuite en PDF par xhtml2pdf).

Structure identique au CV manuel :

    Nom
    Sous-titre (adapté à l'offre)
    Coordonnées (ville | téléphone | e-mail | portfolio | LinkedIn | GitHub)

    FORMATION
    RÉFÉRENCES
    COMPÉTENCES
        <section spécialisée selon l'offre>   (ex. Télédétection & SIG)
        Traitement de données
        Développement
        Atouts
        Bases de données
        Langues
        Loisirs
    EXPÉRIENCES
"""

import html
import re

from config.candidate_profile import (
    CANDIDATE_PROFILE,
    DEFAULT_SKILLS,
    CandidateProfile,
)
from domain.models import CvContent


COLOR_BLUE = "#1f3a5f"
COLOR_BAND = "#eef2f7"
FONT_FAMILY = "'Times New Roman', Times, serif"


def format_bold_markdown(text: object) -> str:
    escaped = html.escape(str(text))

    return re.sub(
        r"\*\*(.*?)\*\*",
        r"<strong>\1</strong>",
        escaped,
    )


def experience_metadata(experience: dict) -> str:
    """
    Ligne en italique sous le titre d'une expérience :
    « Sous-titre, Structure | Période ».
    """

    left = ", ".join(
        value
        for value in (
            str(experience.get("sous_titre", "")).strip(),
            str(experience.get("structure", "")).strip(),
        )
        if value
    )

    period = str(experience.get("periode", "")).strip()

    return " | ".join(
        value
        for value in (left, period)
        if value
    )


class HtmlCvRenderer:
    def __init__(
        self,
        profile: CandidateProfile = CANDIDATE_PROFILE,
    ) -> None:
        self.profile = profile

    def render(
        self,
        content: CvContent,
        font_scale: float = 1.0,
        margin_top_cm: float = 0.9,
        margin_side_cm: float = 1.2,
        margin_bottom_cm: float = 0.5,
    ) -> str:
        skills = content.skills or DEFAULT_SKILLS

        base = 10 * font_scale
        name_size = 16 * font_scale
        subtitle_size = 11 * font_scale
        section_size = 11.5 * font_scale
        gap = 4 * font_scale

        body = "".join(
            [
                self._header(content.subtitle),
                self._section_title("Formation", section_size, gap),
                self._formations(gap),
                self._references(section_size, gap),
                self._section_title("Compétences", section_size, gap),
                self._skills(skills, gap),
                self._section_title("Expériences", section_size, gap),
                self._experiences(content.experiences, gap),
            ]
        )

        return f"""<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin-top: {margin_top_cm}cm;
        margin-right: {margin_side_cm}cm;
        margin-bottom: {margin_bottom_cm}cm;
        margin-left: {margin_side_cm}cm;
    }}
    body {{
        font-family: {FONT_FAMILY};
        font-size: {base}pt;
        line-height: 1.2;
        color: #1a1a1a;
    }}
    .name {{
        text-align: center;
        font-size: {name_size}pt;
        font-weight: bold;
        color: {COLOR_BLUE};
    }}
    .subtitle {{
        text-align: center;
        font-size: {subtitle_size}pt;
        font-weight: bold;
        margin-top: 1px;
    }}
    .contact {{
        text-align: center;
        font-size: {base * 0.88}pt;
        color: #333333;
        margin-bottom: {gap}px;
    }}
    .bold {{ font-weight: bold; }}
    .italic {{ font-style: italic; color: #333333; }}
    .cat {{
        font-weight: bold;
        color: {COLOR_BLUE};
        margin-top: {gap * 0.6}px;
    }}
    ul {{ margin: 0 0 0 16px; padding: 0; }}
    li {{ margin: 0; padding: 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""

    # ------------------------------------------------------------------
    # Blocs
    # ------------------------------------------------------------------

    def _header(self, subtitle: str) -> str:
        return (
            f'<div class="name">{html.escape(self.profile.name)}</div>'
            f'<div class="subtitle">{html.escape(subtitle)}</div>'
            f'<div class="contact">'
            f'{html.escape(self.profile.contact)}</div>'
        )

    @staticmethod
    def _section_title(text: str, size: float, gap: float) -> str:
        padding = round(size * 0.3, 1)

        return (
            f'<table cellpadding="0" cellspacing="0" style="width:100%;'
            f'border-collapse:collapse;margin-top:{gap * 1.5}px;'
            f'margin-bottom:{gap}px"><tr>'
            f'<td style="background-color:{COLOR_BAND};'
            f'padding:{padding}px 6px;color:{COLOR_BLUE};'
            f'font-weight:bold;font-size:{size}pt;line-height:1;'
            f'text-transform:uppercase">{html.escape(text)}</td>'
            f'</tr></table>'
        )

    def _formations(self, gap: float) -> str:
        return "".join(
            f'<div style="margin-bottom:{gap * 0.4}px">'
            f'<div class="bold">{html.escape(formation.title)}</div>'
            f'<div class="italic">{html.escape(formation.detail)}</div>'
            f'</div>'
            for formation in self.profile.formations
        )

    def _references(self, size: float, gap: float) -> str:
        line = self.profile.references_line

        if not line:
            return ""

        return (
            self._section_title("Références", size, gap)
            + f"<div>{html.escape(line)}</div>"
        )

    @staticmethod
    def _skills(skills: dict[str, list[str]], gap: float) -> str:
        blocks = []

        for category, bullets in skills.items():
            if not bullets:
                continue

            items = "".join(
                f"<li>{html.escape(str(bullet))}</li>"
                for bullet in bullets
            )

            blocks.append(
                f'<div class="cat">{html.escape(category)}</div>'
                f"<ul>{items}</ul>"
            )

        return "".join(blocks)

    @staticmethod
    def _experiences(experiences: list[dict], gap: float) -> str:
        blocks = []

        for index, experience in enumerate(experiences):
            bullets = "".join(
                f'<li style="margin-bottom:{gap * 0.25}px">'
                f"{format_bold_markdown(bullet)}</li>"
                for bullet in experience.get("bullets", [])
            )

            padding_top = 0 if index == 0 else gap * 2

            blocks.append(
                f'<div class="bold" style="margin-top:{padding_top}px">'
                f'{html.escape(str(experience.get("titre", "")))}</div>'
                f'<div class="italic" style="margin-bottom:2px">'
                f"{html.escape(experience_metadata(experience))}</div>"
                f"<ul>{bullets}</ul>"
            )

        return "".join(blocks)
