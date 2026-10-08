# job_automation/src/job_automation/documents/html_letter_renderer.py

import html

from config.letter_profile import (
    LETTER_PROFILE,
    LetterProfile,
)
from domain.models import (
    LetterContent,
    LetterContext,
)


class HtmlLetterRenderer:
    def __init__(
        self,
        profile: LetterProfile = LETTER_PROFILE,
    ) -> None:
        self.profile = profile

    def render(
        self,
        context: LetterContext,
        content: LetterContent,
        font_scale: float = 1.0,
    ) -> str:
        font_size = 10.5 * font_scale
        line_height = 1.35
        paragraph_gap = 10 * font_scale

        sender_lines = "<br>".join(
            html.escape(line)
            for line in (
                self.profile.full_name,
                *self.profile.address_lines,
                self.profile.phone,
                self.profile.email,
                self.profile.portfolio,
                self.profile.github,
            )
            if line
        )

        recipient_lines = "<br>".join(
            html.escape(line)
            for line in (
                context.recipient.postal_lines
            )
        )

        paragraphs_html = "".join(
            f"""
<p style="
    margin: 0 0 {paragraph_gap}px 0;
    text-align: justify;
">
    {html.escape(paragraph)}
</p>
"""
            for paragraph in content.paragraphs
        )

        return f"""
<html>
<head>
<meta charset="utf-8">

<style>
    @page {{
        size: A4;
        margin-top: 1.4cm;
        margin-right: 1.8cm;
        margin-bottom: 1.3cm;
        margin-left: 1.8cm;
    }}

    body {{
        font-family: "Times New Roman", Times, serif;
        font-size: {font_size}pt;
        line-height: {line_height};
        color: #111111;
    }}

    .sender {{
        margin-bottom: 16px;
    }}

    .recipient {{
        text-align: right;
        margin-bottom: 15px;
    }}

    .date {{
        margin-bottom: 12px;
    }}

    .attention {{
        margin-bottom: 12px;
    }}

    .subject {{
        font-weight: bold;
        margin-bottom: 18px;
    }}

    .greeting {{
        margin-bottom: 14px;
    }}

    .closing {{
        margin-top: 14px;
        margin-bottom: 20px;
        text-align: justify;
    }}

    .signature {{
        margin-top: 14px;
    }}
</style>
</head>

<body>
    <div class="sender">
        {sender_lines}
    </div>

    <div class="recipient">
        {recipient_lines}
    </div>

    <div class="date">
        {html.escape(self.profile.city)}, le {html.escape(context.date_label)}
    </div>

    <div class="attention">
        {html.escape(context.recipient.attention_line)}
    </div>

    <div class="subject">
        Objet : {html.escape(content.subject)}
    </div>

    <div class="greeting">
        {html.escape(content.greeting)}
    </div>

    {paragraphs_html}

    <div class="closing">
        {html.escape(content.closing)}
    </div>

    <div class="signature">
        {html.escape(content.signature)}
    </div>
</body>
</html>
"""