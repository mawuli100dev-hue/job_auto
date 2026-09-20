"""
cv_builder.py
Module de construction du CV en HTML -> PDF (1 page garantie) + Word.
Ne contient AUCUN appel LLM : uniquement la mise en forme visuelle.

CHOIX FINAL (SIMPLICITÉ AVANT TOUT) :
Une seule colonne pour les compétences, avec xhtml2pdf (pas de nouvelle
dépendance à installer). Garanti 100% fiable pour tous les ATS.

CORRECTIF (2026-09-14 - alignement avec competences_pool.json) :
DEFAULT_COMPETENCES (utilisé par preview_cv.py quand aucune offre n'est
ciblée) est mis à jour pour refléter les mêmes ajouts que competences_pool.json
(Pandas/NumPy/Matplotlib, notions Scikit-learn/TensorFlow/PyTorch/OpenCV,
Power Automate/Kafka, Agile/Scrum, React explicité, NoSQL), suite à l'analyse
des offres data/IA collectées qui citent très fréquemment ces technologies.
Aucun changement structurel : tailor_cv.py et build_html/build_docx lisent
dynamiquement les catégories, donc ces ajouts n'exigent aucune modification
de code, seulement des données.
"""

import re
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn
from xhtml2pdf import pisa
from pypdf import PdfReader

NOM = "Hénoc AMAVIGAN"
CONTACT = "Carcassonne, France | +33 7 74 74 98 25 | amaviganhenoc@gmail.com | https://portfolioamavigan.vercel.app"

SOUS_TITRE_DEFAUT = "Recherche d'alternance en science des données à partir de septembre 2026"

FONT_FAMILY_CSS = "'Times New Roman', Times, serif"
FONT_NAME_DOCX = "Times New Roman"

FORMATION = [
    ("2026 : 3e année de BUT Science de Données", "Spécialité Exploration et Modélisation Statistique", "IUT de Perpignan, Antenne de Carcassonne"),
    ("2025 : Licence Professionnelle en Ingénierie Logicielle - niveau 3e année", "", "École Polytechnique, Lomé, Togo"),
    ("2022 : Baccalauréat C", "", "Lycée d'enseignement général, Lomé, Togo - Mathématiques et physique"),
]

COLOR_BLUE = "#1f3a5f"

DEFAULT_COMPETENCES_COL1 = ["Langages", "Atouts", "Langues"]
DEFAULT_COMPETENCES_COL2 = ["Outils", "Bases de données", "Loisirs"]

# Mis à jour le 2026-09-14 pour refléter les technologies les plus demandées
# dans les offres data/IA collectées (Pandas/NumPy/Matplotlib, notions ML/DL,
# Power Automate/Kafka, Agile/Scrum), en cohérence avec competences_pool.json.
DEFAULT_COMPETENCES = {
    "Langages": ["Python, R", "Java, JavaScript, TypeScript", "C, C++", "VBA", "SQL"],
    "Outils": [
        "Pandas, NumPy, Matplotlib",
        "Notions de Scikit-learn, TensorFlow, PyTorch, OpenCV",
        "Nest.js, Next.js (React), Streamlit, Flask",
        "Power BI, Excel, FME",
        "GitHub, GitHub Actions, Docker, Linux",
        "QGIS, ArcGIS, N8N, Matlab",
        "Power Automate, notions de Kafka",
    ],
    "Atouts": [
        "Permis de conduire B",
        "Aisance à l'oral et en présentation",
        "Développement de solutions automatisées",
        "Cartographie et visualisation de données",
        "Rigueur et autonomie technique",
        "Méthodologie Agile / Scrum",
    ],
    "Bases de données": ["PostgreSQL", "MySQL", "Oracle", "Notions de NoSQL"],
    "Langues": ["Anglais: niveau B2", "Allemand: Goethe Zertifikat B2"],
    "Loisirs": ["Guitare basse et du tuba", "Cuisine : pâtisserie"],
}

MARGIN_TOP_CM = 1.0
MARGIN_SIDE_CM = 1.2
MARGIN_BOTTOM_CM = 0.2


def bold_markdown_to_html(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)


INLINE_CATEGORIES = {"Langages" ,"Langues", "Bases de données", "Loisirs"}

def _competences_column_html(categories: list[str], competences: dict, category_gap: float, item_gap: float) -> str:
    html = ""
    for cat in categories:
        items = competences.get(cat, [])
        if cat in INLINE_CATEGORIES:
            content = f'<div style="margin-top:1px">{" | ".join(items)}</div>'
        else:
            li = "".join(f'<li style="margin-bottom:{item_gap}px">{item}</li>' for item in items)
            content = f'<ul style="margin:1px 0 0 14px;padding:0">{li}</ul>'
        html += (
            f'<div style="margin-bottom:{category_gap}px">'
            f'<div style="font-weight:bold;color:{COLOR_BLUE};margin-bottom:2px">{cat}</div>'
            f'{content}'
            f'</div>'
        )
    return html


def section_title_html(text: str, font_size: float, gap: float) -> str:
    pad_v = round(font_size * 0.35, 1)
    return (
        f'<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;'
        f'margin-top:{gap}px;margin-bottom:{gap}px">'
        f'<tr><td style="background-color:#eef2f7;padding:{pad_v}px 8px {pad_v}px 8px;'
        f'color:{COLOR_BLUE};font-weight:bold;line-height:1;font-size:{font_size}pt;'
        f'text-transform:uppercase">{text}</td></tr></table>'
    )


def build_html(
    selected_experiences: list[dict],
    competences: dict | None = None,
    sous_titre: str | None = None,
    font_scale: float = 1.0,
    margin_top_cm: float = MARGIN_TOP_CM,
    margin_side_cm: float = MARGIN_SIDE_CM,
    margin_bottom_cm: float = MARGIN_BOTTOM_CM,
) -> str:
    competences = competences or DEFAULT_COMPETENCES
    sous_titre = sous_titre or SOUS_TITRE_DEFAUT

    base = 10 * font_scale
    h1 = 16 * font_scale
    h2 = 11 * font_scale
    section_title_size = 11 * font_scale
    gap = 5 * font_scale
    category_gap = 9 * font_scale
    item_gap = 2.5 * font_scale
    exp_gap = 12 * font_scale

    formation_html = ""
    for titre, sous_titre_formation, structure in FORMATION:
        detail = f"{sous_titre_formation} - {structure}" if sous_titre_formation else structure
        formation_html += (
            f'<div style="margin-bottom:{gap * 0.7}px">'
            f'<div style="font-weight:bold">{titre}</div>'
            f'<div style="font-style:italic;color:#333">{detail}</div>'
            f'</div>'
        )

    competences_categories = DEFAULT_COMPETENCES_COL1 + DEFAULT_COMPETENCES_COL2
    competences_html = _competences_column_html(competences_categories, competences, category_gap, item_gap)

    experience_blocks = []
    for exp in selected_experiences:
        sous_titre_exp = exp.get("sous_titre", "")
        structure = exp.get("structure", "")
        periode = exp.get("periode", "")
        prefixe = f"{sous_titre_exp} - {structure}" if sous_titre_exp else structure
        meta = ", ".join(filter(None, [prefixe, periode]))
        bullets_html = "".join(
            f'<li style="margin-bottom:{gap * 0.3}px">{bold_markdown_to_html(b)}</li>'
            for b in exp["bullets"]
        )
        block = (
            f'<div style="font-weight:bold;margin:0">{exp["titre"]}</div>'
            f'<div style="font-style:italic;color:#333;margin:0 0 3px 0">{meta}</div>'
            f'<ul style="margin:0 0 0 15px;padding:0">{bullets_html}</ul>'
        )
        experience_blocks.append(block)

    experiences_html = ""
    for i, block in enumerate(experience_blocks):
        pad_top = 0 if i == 0 else exp_gap
        experiences_html += f'<div style="padding-top:{pad_top}px">{block}</div>'

    html = f"""<html>
<head>
<style>
@page {{
    size: A4;
    margin-top: {margin_top_cm}cm;
    margin-right: {margin_side_cm}cm;
    margin-bottom: {margin_bottom_cm}cm;
    margin-left: {margin_side_cm}cm;
}}
body {{ font-family: {FONT_FAMILY_CSS}; font-size: {base}pt; line-height: 1.2; color: #1a1a1a; }}
.nom {{ text-align:center; font-size:{h1}pt; font-weight:bold; color:{COLOR_BLUE}; margin-bottom:2px; }}
.accroche {{ text-align:center; font-size:{h2}pt; font-weight:bold; margin-bottom:4px; }}
.contact {{ text-align:center; font-size:{base * 0.9}pt; color:#444; margin-bottom:{gap}px; }}
.competences {{ margin-top: 2px; }}
ul {{ list-style-type: disc; }}
li {{ margin-left: 0; }}
</style>
</head>
<body>
<div class="nom">{NOM}</div>
<div class="accroche">{sous_titre}</div>
<div class="contact">{CONTACT}</div>
{section_title_html("Formation", section_title_size, gap)}
{formation_html}
{section_title_html("Compétences", section_title_size, gap)}
<div class="competences">{competences_html}</div>
{section_title_html("Expériences", section_title_size, gap)}
{experiences_html}
</body>
</html>"""
    return html


def render_pdf(html: str, output_path: Path) -> bool:
    with open(output_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f)
    return not result.err


def count_pages(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def fit_on_one_page(
    selected_experiences: list[dict],
    output_pdf: Path,
    output_html: Path,
    competences: dict | None = None,
    sous_titre: str | None = None,
    start_scale: float = 1.15,
    min_scale: float = 0.83,
    step: float = 0.05,
    margin_top_cm: float = MARGIN_TOP_CM,
    margin_side_cm: float = MARGIN_SIDE_CM,
    margin_bottom_cm: float = MARGIN_BOTTOM_CM,
) -> float:
    scale = start_scale
    while scale >= min_scale:
        html = build_html(
            selected_experiences,
            competences=competences,
            sous_titre=sous_titre,
            font_scale=scale,
            margin_top_cm=margin_top_cm,
            margin_side_cm=margin_side_cm,
            margin_bottom_cm=margin_bottom_cm,
        )
        render_pdf(html, output_pdf)
        if count_pages(output_pdf) == 1:
            with open(output_html, "w", encoding="utf-8") as f:
                f.write(html)
            return scale
        scale -= step

    html = build_html(
        selected_experiences,
        competences=competences,
        sous_titre=sous_titre,
        font_scale=min_scale,
        margin_top_cm=margin_top_cm,
        margin_side_cm=margin_side_cm,
        margin_bottom_cm=margin_bottom_cm,
    )
    render_pdf(html, output_pdf)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    print("ATTENTION : le CV ne tient toujours pas sur une page à l'échelle minimale.")
    return min_scale


def set_run_font(run, name: str = FONT_NAME_DOCX):
    run.font.name = name
    rPr = run.element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = rPr.makeelement(qn('w:rFonts'), {})
        rPr.append(rFonts)
    rFonts.set(qn('w:eastAsia'), name)


def add_bullet_docx(doc: Document, text: str):
    p = doc.add_paragraph(style="List Bullet")
    parts = re.split(r"(\*\*.*?\*\*)", text)
    for part in parts:
        if not part:
            continue
        run = p.add_run(part[2:-2] if part.startswith("**") else part)
        run.bold = part.startswith("**")
        set_run_font(run)


def build_docx(
    selected_experiences: list[dict],
    output_path: Path,
    competences: dict | None = None,
    sous_titre: str | None = None,
):
    competences = competences or DEFAULT_COMPETENCES
    sous_titre = sous_titre or SOUS_TITRE_DEFAUT
    doc = Document()

    normal_style = doc.styles["Normal"]
    normal_style.font.name = FONT_NAME_DOCX
    normal_style.element.rPr.rFonts.set(qn('w:eastAsia'), FONT_NAME_DOCX)

    p = doc.add_paragraph()
    r = p.add_run(NOM)
    r.bold = True
    r.font.size = Pt(18)
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run(sous_titre)
    r.bold = True
    r.font.size = Pt(12)
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run(CONTACT.replace(" | ", "  |  "))
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run("FORMATION")
    r.bold = True
    r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    set_run_font(r)

    for titre, sous_titre_formation, structure in FORMATION:
        detail = f"{sous_titre_formation} - {structure}" if sous_titre_formation else structure
        p = doc.add_paragraph()
        r = p.add_run(titre)
        r.bold = True
        set_run_font(r)
        p2 = doc.add_paragraph()
        r2 = p2.add_run(detail)
        r2.italic = True
        set_run_font(r2)

    p = doc.add_paragraph()
    r = p.add_run("COMPÉTENCES")
    r.bold = True
    r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    set_run_font(r)

    for cat in DEFAULT_COMPETENCES_COL1 + DEFAULT_COMPETENCES_COL2:
        items = competences.get(cat, [])
        p = doc.add_paragraph()
        r = p.add_run(f"{cat}: ")
        r.bold = True
        set_run_font(r)
        r2 = p.add_run(", ".join(items))
        set_run_font(r2)

    p = doc.add_paragraph()
    r = p.add_run("EXPÉRIENCES")
    r.bold = True
    r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    set_run_font(r)

    for exp in selected_experiences:
        p = doc.add_paragraph()
        r = p.add_run(exp["titre"])
        r.bold = True
        set_run_font(r)

        sous_titre_exp = exp.get("sous_titre", "")
        structure = exp.get("structure", "")
        periode = exp.get("periode", "")
        prefixe = f"{sous_titre_exp} - {structure}" if sous_titre_exp else structure
        meta = ", ".join(filter(None, [prefixe, periode]))
        p2 = doc.add_paragraph()
        r2 = p2.add_run(meta)
        r2.italic = True
        set_run_font(r2)

        for b in exp["bullets"]:
            add_bullet_docx(doc, b)

    doc.save(output_path)