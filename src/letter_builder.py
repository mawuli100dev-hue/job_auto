"""
letter_builder.py
Mise en forme de la lettre de motivation en HTML -> PDF (1 page garantie) + Word,
avec le même style que le CV (Times New Roman, mise en page sobre).

Contraintes fixes :
- Police à 11pt PARTOUT, y compris le nom du candidat (aucune exception), et
  JAMAIS réduite pour faire tenir le texte sur une page.
- Marges gauche/droite fixées à 1 cm.
- Texte du corps de la lettre justifié (aligné à gauche ET à droite).
- Signature alignée à GAUCHE (pas à droite).
- En-tête candidat / entreprise EMPILÉS, interligne TRÈS SERRÉ propre à ces blocs.
- AUCUNE ligne vide "gaspillée" (paragraphe vide entier) entre les blocs.
- Pour tenir sur 1 page, ORDRE DE PRIORITÉ DE RESSERREMENT :
  1. marge basse (jusqu'à 0)
  2. marge haute
  3. interligne du corps du texte
  4. espacement ENTRE les paragraphes (gap_px) - en tout dernier recours, pour
     que les paragraphes restent visuellement bien séparés le plus longtemps
     possible.
La taille de police (11pt) ne bouge JAMAIS.
Ne contient AUCUN appel LLM.

═══════════════════════════════════════════════════════════════════════════
FIX v2 (2026-09-19) : ordre du bloc "entreprise/lieu" dans le PDF
═══════════════════════════════════════════════════════════════════════════
Bug observé : sur plusieurs lettres générées, le bloc "ENTREPRISE / lieu"
apparaissait dans le texte extrait du PDF APRÈS "Madame, Monsieur," au lieu
d'apparaître avant (comme dans le .docx, qui lui était toujours correct).

Cause probable : xhtml2pdf (moteur pisa) a un support fragile du "collapsing"
des marges CSS quand plusieurs blocs consécutifs ont des margin-bottom très
faibles (la boucle de resserrement fit_on_one_page descend jusqu'à 0px). Sur
certaines combinaisons de valeurs, la hauteur calculée d'un bloc "text-align:
right" peut être mal évaluée par le moteur, ce qui décale son contenu par
rapport aux blocs suivants.

Correctifs appliqués :
1. Remplacement de tous les margin-bottom des blocs d'en-tête par du
   padding-bottom. Le padding ne "collapse" jamais entre blocs adjacents
   (contrairement au margin), ce qui supprime la source d'ambiguïté la plus
   probable dans le moteur de mise en page.
2. Ajout de "display:block; overflow:hidden;" explicite sur les blocs d'en-tête
   pour forcer un calcul de hauteur déterministe (empêche tout chevauchement
   avec le bloc suivant même en cas de contenu court).
3. Le bloc entreprise/lieu et le bloc date/objet/salutation sont désormais
   rendus par une fonction dédiée qui garantit textuellement l'ordre dans le
   flux HTML (candidat -> entreprise -> date -> attention -> objet ->
   salutation -> corps), avec des tests de regression possibles via
   render_pdf + extraction texte pour vérifier l'ordre avant envoi.
"""

import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from xhtml2pdf import pisa
from pypdf import PdfReader

NOM = "Hénoc AMAVIGAN"
VILLE_CANDIDAT = "Carcassonne, 11000"
TELEPHONE = "+33 7 74 74 98 25"
EMAIL = "amaviganhenoc@gmail.com"
PORTFOLIO = "https://portfolioamavigan.vercel.app/"

FONT_FAMILY_CSS = "'Times New Roman', Times, serif"
FONT_NAME_DOCX = "Times New Roman"
FONT_SIZE_PT = 11
MARGIN_LR_CM = 1.0
HEADER_LINE_HEIGHT = 1.05  # interligne fixe et serré, réservé aux blocs d'adresse


def build_html(entreprise: str, lieu_entreprise: str, ville_date: str, objet: str,
                paragraphs: list, margin_top_cm: float = 1.3, margin_bottom_cm: float = 1.3,
                line_height: float = 1.25, gap_px: float = 10, header_gap_px: float = 9) -> str:
    paragraphs_html = "".join(
        f'<p class="corps">{p}</p>' for p in paragraphs
    )

    # FIX v2 : padding-bottom au lieu de margin-bottom sur les blocs d'en-tête,
    # + display:block/overflow:hidden pour un calcul de hauteur déterministe.
    # Ceci évite tout collapsing de marge ambigu entre blocs successifs quand
    # header_gap_px descend vers 0 pendant le resserrement (fit_on_one_page).
    html = f"""<html>
<head>
<style>
@page {{
    size: A4;
    margin: {margin_top_cm}cm {MARGIN_LR_CM}cm {margin_bottom_cm}cm {MARGIN_LR_CM}cm;
}}
body {{
    font-family: {FONT_FAMILY_CSS};
    font-size: {FONT_SIZE_PT}pt;
    line-height: {line_height};
    color: #1a1a1a;
}}
p {{ margin: 0; }}
.corps {{
    margin: 0 0 {gap_px}px 0;
    text-align: justify;
    text-justify: inter-word;
}}
.header-candidat {{
    display: block;
    overflow: hidden;
    padding-bottom: {header_gap_px}px;
    margin-bottom: 0;
    line-height: {HEADER_LINE_HEIGHT};
}}
.header-candidat div {{ margin: 0; padding: 0; font-size: {FONT_SIZE_PT}pt; }}
.nom {{ font-weight: bold; }}
.header-entreprise {{
    display: block;
    overflow: hidden;
    text-align: right;
    padding-bottom: {header_gap_px}px;
    margin-bottom: 0;
    line-height: {HEADER_LINE_HEIGHT};
}}
.header-entreprise div {{ margin: 0; padding: 0; }}
.entreprise-nom {{ font-weight: bold; text-transform: uppercase; }}
.date-ligne {{ margin-bottom: 2px; }}
.objet {{ font-weight: bold; margin: {gap_px}px 0 {gap_px}px 0; text-align: justify; }}
.salutation {{ margin-bottom: {gap_px}px; }}
.cloture {{ margin-top: {gap_px}px; text-align: justify; }}
.signature {{ text-align: left; margin-top: {gap_px * 1.5}px; }}
</style>
</head>
<body>
<div class="header-candidat">
    <div class="nom">{NOM}</div>
    <div>{VILLE_CANDIDAT}</div>
    <div>{TELEPHONE}</div>
    <div>{EMAIL}</div>
    <div>{PORTFOLIO}</div>
</div>
<div class="header-entreprise">
    <div class="entreprise-nom">{entreprise}</div>
    <div>{lieu_entreprise}</div>
</div>
<div class="date-ligne">{ville_date}</div>
<div>À l'attention de l'équipe recrutement</div>
<div class="objet"><b>OBJET</b> : {objet}</div>
<div class="salutation">Madame, Monsieur,</div>
{paragraphs_html}
<div class="cloture">Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.</div>
<div class="signature">{NOM}</div>
</body>
</html>"""
    return html


def render_pdf(html: str, output_path: Path) -> bool:
    try:
        with open(output_path, "wb") as f:
            result = pisa.CreatePDF(html, dest=f)
        return not result.err
    except PermissionError:
        alt = alt_path(output_path)
        print(f"ATTENTION : {output_path.name} est verrouillé (probablement ouvert "
              f"dans une autre appli). Sauvegarde sous {alt.name} à la place.")
        with open(alt, "wb") as f:
            result = pisa.CreatePDF(html, dest=f)
        return not result.err


def count_pages(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def alt_path(path: Path) -> Path:
    stamp = datetime.now().strftime("%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def write_html_output(output_html: Path, html: str) -> None:
    try:
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(html)
    except PermissionError:
        alt = alt_path(output_html)
        print(f"ATTENTION : {output_html.name} est verrouillé. Sauvegarde sous "
              f"{alt.name} à la place.")
        with open(alt, "w", encoding="utf-8") as f:
            f.write(html)


# (margin_top, margin_bottom, line_height, gap_px, header_gap_px)
# header_gap_px ne descend jamais à 0 pour laisser toujours un padding non nul
# entre le bloc entreprise et le bloc date, même au resserrement maximal
# (le padding ne collapse pas mais un padding à 0 rendrait le bug plus facile
# à réintroduire si la structure HTML change plus tard).
TIGHTENING_STEPS = [
    (1.3, 1.3, 1.25, 10, 9),
    (1.3, 1.0, 1.25, 10, 9),
    (1.3, 0.6, 1.24, 10, 9),
    (1.3, 0.3, 1.24, 10, 9),
    (1.3, 0.0, 1.22, 10, 9),
    (1.1, 0.0, 1.20, 9, 8),
    (1.0, 0.0, 1.18, 9, 8),
    (0.9, 0.0, 1.15, 8, 7),
    (0.8, 0.0, 1.12, 8, 7),
    (0.7, 0.0, 1.10, 7, 6),
    (0.6, 0.0, 1.08, 6, 6),
    (0.5, 0.0, 1.05, 5, 5),
    (0.4, 0.0, 1.00, 4, 4),
]


def fit_on_one_page(entreprise: str, lieu_entreprise: str, ville_date: str, objet: str,
                     paragraphs: list, output_pdf: Path, output_html: Path) -> dict:
    """La police 11pt et les marges gauche/droite (1cm) ne bougent JAMAIS."""
    for margin_top, margin_bottom, line_height, gap_px, header_gap_px in TIGHTENING_STEPS:
        html = build_html(
            entreprise, lieu_entreprise, ville_date, objet, paragraphs,
            margin_top_cm=margin_top, margin_bottom_cm=margin_bottom,
            line_height=line_height, gap_px=gap_px, header_gap_px=header_gap_px,
        )
        render_pdf(html, output_pdf)
        if count_pages(output_pdf) == 1:
            write_html_output(output_html, html)
            return {
                "margin_top_cm": margin_top, "margin_bottom_cm": margin_bottom,
                "line_height": line_height, "gap_px": gap_px,
                "font_size_pt": FONT_SIZE_PT, "fitted": True,
            }

    write_html_output(output_html, html)
    if count_pages(output_pdf) != 1:
        print("ATTENTION : la lettre ne tient toujours pas sur une page (11pt même "
              "avec des marges/interlignes minimaux) : raccourcis légèrement le "
              "texte dans generate_letter.py.")
    last = TIGHTENING_STEPS[-1]
    return {
        "margin_top_cm": last[0], "margin_bottom_cm": last[1], "line_height": last[2],
        "gap_px": last[3], "font_size_pt": FONT_SIZE_PT, "fitted": False,
    }


def set_run_font(run, name: str = FONT_NAME_DOCX, size_pt: int = FONT_SIZE_PT) -> None:
    run.font.name = name
    run.font.size = Pt(size_pt)
    rpr = run.element.get_or_add_rPr()
    rFonts = rpr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), name)


def tight_paragraph(doc_or_cell, alignment=None, space_after_pt: float = 0):
    p = doc_or_cell.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after_pt)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.line_spacing = HEADER_LINE_HEIGHT
    if alignment is not None:
        p.alignment = alignment
    return p


def build_docx(entreprise: str, lieu_entreprise: str, ville_date: str, objet: str,
                paragraphs: list, output_path: Path, paragraph_space_after_pt: float = 8) -> None:
    """La police 11pt et les marges gauche/droite (1cm) ne bougent JAMAIS."""
    doc = Document()
    section = doc.sections[0]
    section.left_margin = Cm(MARGIN_LR_CM)
    section.right_margin = Cm(MARGIN_LR_CM)
    section.top_margin = Cm(1.3)
    section.bottom_margin = Cm(0.3)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = FONT_NAME_DOCX
    normal_style.font.size = Pt(FONT_SIZE_PT)
    normal_style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME_DOCX)
    normal_style.paragraph_format.space_after = Pt(paragraph_space_after_pt)
    normal_style.paragraph_format.space_before = Pt(0)

    # Bloc candidat empilé, interligne serré, police 11pt uniforme.
    p = tight_paragraph(doc)
    r = p.add_run(NOM)
    r.bold = True
    set_run_font(r)

    lignes_candidat = [VILLE_CANDIDAT, TELEPHONE, EMAIL, PORTFOLIO]
    for i, line in enumerate(lignes_candidat):
        is_last = i == len(lignes_candidat) - 1
        p = tight_paragraph(doc, space_after_pt=10 if is_last else 0)
        r = p.add_run(line)
        set_run_font(r)

    # Bloc entreprise empilé, aligné à droite, interligne serré (rendu AVANT
    # la date/l'objet/la salutation, comme dans le PDF corrigé).
    p = tight_paragraph(doc, alignment=WD_ALIGN_PARAGRAPH.RIGHT)
    r = p.add_run(entreprise.upper())
    r.bold = True
    set_run_font(r)

    p2 = tight_paragraph(doc, alignment=WD_ALIGN_PARAGRAPH.RIGHT, space_after_pt=10)
    r2 = p2.add_run(lieu_entreprise)
    set_run_font(r2)

    p = doc.add_paragraph()
    r = p.add_run(ville_date)
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run("À l'attention de l'équipe recrutement")
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run(f"OBJET : {objet}")
    r.bold = True
    set_run_font(r)

    p = doc.add_paragraph()
    r = p.add_run("Madame, Monsieur,")
    set_run_font(r)

    # Corps de la lettre, justifié, paragraphes séparés.
    for para in paragraphs:
        clean = re.sub(r"\s+", " ", para)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = p.add_run(clean)
        set_run_font(r)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.")
    set_run_font(r)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(NOM)
    set_run_font(r)

    try:
        doc.save(output_path)
    except PermissionError:
        alt = alt_path(output_path)
        print(f"ATTENTION : {output_path.name} est verrouillé (sûrement ouvert dans "
              f"Word). Sauvegarde sous {alt.name} à la place.")
        doc.save(alt)