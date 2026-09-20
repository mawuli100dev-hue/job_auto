"""
merge_dossier.py
Fusionne, pour une offre donnée, deux PDF finaux dans le dossier de candidature :

  1. CV_LM_AMAVIGAN.pdf  = CV + Lettre de motivation + documents annexes
  2. LM_x_AMAVIGAN.pdf   = Lettre de motivation (SANS le CV) + documents annexes

Les documents annexes (data/extra/) sont triés par le PRÉFIXE NUMÉRIQUE de leur
nom de fichier (ex: "3_bulletin sem3.pdf" avant "4_bulletin sem4.pdf").

Ne contient AUCUN appel LLM.

Usage :
    python merge_dossier.py --offer-id 213QBYH
"""

import re
import argparse
from datetime import datetime
from pathlib import Path

from pypdf import PdfWriter

BASE_DIR = Path(__file__).resolve().parent.parent
EXTRA_DIR = BASE_DIR / "data" / "extra"


def find_candidature_dir(offer_id: str, base_dir: Path) -> Path:
    """Retrouve le dossier de candidature déjà créé par tailor_cv.py / generate_letter.py."""
    candidatures_dir = base_dir / "data" / "candidatures"
    matches = list(candidatures_dir.glob(f"*/*_{offer_id}"))
    if not matches:
        raise FileNotFoundError(
            f"Aucun dossier de candidature trouvé pour l'offre {offer_id}. "
            f"Lance d'abord tailor_cv.py puis generate_letter.py sur cette offre."
        )
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def _extraction_prefix(path: Path) -> tuple[int, str]:
    """Extrait le préfixe numérique du nom de fichier (ex: '3_bulletin...' -> 3).
    Les fichiers sans préfixe numérique sont placés à la fin, triés par nom."""
    match = re.match(r"^(\d+)_", path.stem)
    if match:
        return (int(match.group(1)), path.name)
    return (10**9, path.name)


def collect_extra_files(extra_dir: Path) -> list[Path]:
    if not extra_dir.exists():
        print(f"ATTENTION : le dossier {extra_dir} n'existe pas, aucun document annexe ajouté.")
        return []
    pdfs = [p for p in extra_dir.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()]
    pdfs.sort(key=_extraction_prefix)
    return pdfs


def merge_pdfs(ordered_files: list[Path], output_path: Path) -> Path:
    writer = PdfWriter()
    for pdf_path in ordered_files:
        writer.append(str(pdf_path))

    try:
        with open(output_path, "wb") as f:
            writer.write(f)
    except PermissionError:
        stamp = datetime.now().strftime("%H%M%S")
        alt_path = output_path.with_name(f"{output_path.stem}_{stamp}{output_path.suffix}")
        print(f"ATTENTION : '{output_path.name}' est verrouillé (probablement ouvert dans une autre appli). Sauvegarde sous '{alt_path.name}' à la place.")
        with open(alt_path, "wb") as f:
            writer.write(f)
        return alt_path

    return output_path


def print_ordre(titre: str, fichiers_nommes: list[tuple[str, str]]):
    print(f"\nOrdre de fusion retenu pour {titre} :")
    for i, (nom, label) in enumerate(fichiers_nommes, start=1):
        print(f"  {i}. {nom} ({label})" if label else f"  {i}. {nom}")


def main():
    parser = argparse.ArgumentParser(description="Fusionne CV + lettre de motivation + documents annexes en PDF(s)")
    parser.add_argument("--offer-id", required=True)
    parser.add_argument("--extra-dir", default=str(EXTRA_DIR))
    args = parser.parse_args()

    dossier = find_candidature_dir(args.offer_id, BASE_DIR)
    print(f"Dossier de candidature : {dossier}")

    cv_path = dossier / "CV_Henoc_AMAVIGAN.pdf"
    lm_path = dossier / "LM_Henoc_AMAVIGAN.pdf"

    if not cv_path.exists():
        raise FileNotFoundError(f"CV introuvable : {cv_path}. Lance d'abord tailor_cv.py sur cette offre.")
    if not lm_path.exists():
        raise FileNotFoundError(f"Lettre de motivation introuvable : {lm_path}. Lance d'abord generate_letter.py sur cette offre.")

    extra_files = collect_extra_files(Path(args.extra_dir))

    # --- Document 1 : CV + LM + annexes -> CV_LM_AMAVIGAN.pdf ---
    ordered_files_avec_cv = [cv_path, lm_path] + extra_files
    print_ordre(
        "CV_LM_AMAVIGAN.pdf",
        [(cv_path.name, "CV"), (lm_path.name, "Lettre de motivation")]
        + [(f.name, "") for f in extra_files],
    )
    output_avec_cv = dossier / "CV_LM_AMAVIGAN.pdf"
    final_avec_cv = merge_pdfs(ordered_files_avec_cv, output_avec_cv)
    print(f"-> PDF fusionné généré : {final_avec_cv}")

    # --- Document 2 : LM (sans CV) + annexes -> LM_x_AMAVIGAN.pdf ---
    ordered_files_sans_cv = [lm_path] + extra_files
    print_ordre(
        "LM_x_AMAVIGAN.pdf",
        [(lm_path.name, "Lettre de motivation")] + [(f.name, "") for f in extra_files],
    )
    output_sans_cv = dossier / "LM_x_AMAVIGAN.pdf"
    final_sans_cv = merge_pdfs(ordered_files_sans_cv, output_sans_cv)
    print(f"-> PDF fusionné généré : {final_sans_cv}")


if __name__ == "__main__":
    main()