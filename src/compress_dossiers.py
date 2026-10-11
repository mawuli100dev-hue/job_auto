"""
compress_dossiers.py

Réduit la taille des dossiers PDF à envoyer (CV_LM_AMAVIGAN.pdf et
LM_x_AMAVIGAN.pdf) et les remet à leur place, dans leur dossier de
candidature.

Ce qui est compressé
--------------------
- le contenu des pages et les objets en double (sans perte) ;
- les images, réenregistrées en JPEG. La qualité baisse par paliers (70,
  55, 45, 35, 25) jusqu'à ce que le PDF pèse 500 Ko ou moins (--cible-ko) ;
  le premier palier qui suffit est gardé. Les images transparentes (logos)
  et les très petites images sont laissées telles quelles.

L'essentiel du poids restant vient des polices intégrées aux annexes
(data/extra) : si 500 Ko ne sont pas atteints, alléger les annexes.

Un PDF n'est remplacé que si la version compressée est plus petite et se
relit correctement, avec le même nombre de pages. Chaque PDF compressé est
marqué pour ne pas être recompressé une seconde fois (chaque passage JPEG
dégrade un peu les images) ; --forcer passe outre.

Si besoin, le PDF d'origine se régénère avec merge_dossier.py.

Exemples
--------

# Tous les dossiers d'un jour
python src\\compress_dossiers.py "data\\linkedin\\3_candidatures\\2026-10-08"

# Toutes les candidatures d'une source, ou de toutes les sources
python src\\compress_dossiers.py "data\\linkedin\\3_candidatures"
python src\\compress_dossiers.py data

# Une seule candidature (utilisé par run_pipeline.ps1)
python src\\compress_dossiers.py --offer-id 214CZVT
"""

import argparse
import io
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from merge_dossier import find_candidature_dir


PROJECT_ROOT = Path(__file__).resolve().parent.parent

TARGET_FILENAMES = (
    "CV_LM_AMAVIGAN.pdf",
    "LM_x_AMAVIGAN.pdf",
)

# Marqueur ajouté aux métadonnées d'un PDF déjà compressé.
COMPRESSED_MARKER = "/JobAutomationCompressed"

DEFAULT_JPEG_QUALITY = 70
DEFAULT_TARGET_KB = 500

# Niveaux essayés dans l'ordre jusqu'à passer sous la taille cible :
# (qualité JPEG, plus grand côté des images en pixels, taille minimale
# d'une image recompressée en octets). Le premier niveau qui suffit est
# gardé, pour des images aussi nettes que possible.
COMPRESSION_LEVELS = (
    (70, 1600, 30 * 1024),
    (55, 1400, 20 * 1024),
    (45, 1200, 10 * 1024),
    (35, 1000, 10 * 1024),
    (25, 900, 5 * 1024),
)


def is_already_compressed(reader: PdfReader) -> bool:
    metadata = reader.metadata or {}

    return metadata.get(COMPRESSED_MARKER) == "oui"


def recompress_images(
    writer: PdfWriter,
    quality: int,
    max_side: int,
    min_size: int,
) -> int:
    """
    Réenregistre en JPEG les grosses images opaques. Renvoie leur nombre.
    """

    count = 0

    for page in writer.pages:
        for image_file in page.images:
            if len(image_file.data) < min_size:
                continue

            image = image_file.image

            # Transparence : la conversion en JPEG donnerait un fond noir.
            if image.mode in ("RGBA", "LA", "P", "PA") or "transparency" in image.info:
                continue

            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side))

            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            try:
                image_file.replace(image, quality=quality)
                count += 1
            except Exception:
                # Image dans un format que pypdf ne sait pas remplacer :
                # elle reste telle quelle.
                continue

    return count


def build_compressed(
    reader: PdfReader,
    level: tuple[int, int, int] | None,
) -> bytes:
    """
    Version compressée du PDF en mémoire. level=None : sans perte.
    """

    writer = PdfWriter(clone_from=reader)

    for page in writer.pages:
        page.compress_content_streams(level=9)

    if level is not None:
        quality, max_side, min_size = level
        recompress_images(writer, quality, max_side, min_size)

    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)

    metadata = dict(reader.metadata or {})
    metadata[COMPRESSED_MARKER] = "oui"
    writer.add_metadata(metadata)

    buffer = io.BytesIO()
    writer.write(buffer)

    return buffer.getvalue()


def compress_pdf(
    path: Path,
    quality: int,
    lossless_only: bool,
    force: bool,
    target_kb: int,
) -> tuple[int, int, str]:
    """
    Compresse un PDF sur place, en visant target_kb Ko (0 : un seul
    passage à la qualité demandée). Renvoie (taille avant, taille après,
    statut).
    """

    before = path.stat().st_size
    target_bytes = target_kb * 1024
    reader = PdfReader(path)

    already_small = not target_kb or before <= target_bytes

    if is_already_compressed(reader) and already_small and not force:
        return before, before, "déjà compressé"

    page_count = len(reader.pages)

    if lossless_only:
        levels = [None]
    else:
        levels = [
            level
            for level in COMPRESSION_LEVELS
            if level[0] <= quality
        ] or [(quality, 1600, 30 * 1024)]

        if not target_kb:
            levels = levels[:1]

    best = None
    best_level = None

    for level in levels:
        data = build_compressed(reader, level)

        if best is None or len(data) < len(best):
            best, best_level = data, level

        if target_kb and len(data) <= target_bytes:
            break

    # Vérifie que la version compressée se relit, avec les mêmes pages.
    try:
        if len(PdfReader(io.BytesIO(best)).pages) != page_count:
            return before, before, "ignoré (pages différentes)"
    except Exception as error:
        return before, before, f"ignoré (relecture impossible : {error})"

    if len(best) >= before:
        return before, before, "déjà optimal"

    temporary = path.with_suffix(".tmp.pdf")
    temporary.write_bytes(best)
    temporary.replace(path)

    detail = "sans perte" if best_level is None else f"qualité images {best_level[0]}"

    if target_kb and len(best) > target_bytes:
        return before, len(best), f"compressé ({detail}), objectif de {target_kb} Ko non atteint"

    return before, len(best), f"compressé ({detail})"


def find_target_files(paths: list[Path]) -> list[Path]:
    files = []

    for path in paths:
        if path.is_file() and path.name in TARGET_FILENAMES:
            files.append(path)
        elif path.is_dir():
            for filename in TARGET_FILENAMES:
                files.extend(path.rglob(filename))

    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Réduit la taille de CV_LM_AMAVIGAN.pdf et LM_x_AMAVIGAN.pdf "
            "dans les dossiers de candidature."
        )
    )

    parser.add_argument(
        "chemins",
        nargs="*",
        help="Dossiers (ou fichiers) où chercher les PDF, recherche dans les sous-dossiers comprise.",
    )

    parser.add_argument(
        "--offer-id",
        "--application-id",
        dest="offer_id",
        default=None,
        help="Compresse le dossier d'une seule candidature (comme merge_dossier.py).",
    )

    parser.add_argument(
        "--qualite",
        type=int,
        default=DEFAULT_JPEG_QUALITY,
        help=f"Qualité JPEG des images (1-95). Défaut : {DEFAULT_JPEG_QUALITY}.",
    )

    parser.add_argument(
        "--cible-ko",
        type=int,
        default=DEFAULT_TARGET_KB,
        help=(
            "Taille visée par PDF, en Ko. La qualité des images baisse par "
            "paliers jusqu'à passer dessous. 0 : un seul passage. "
            f"Défaut : {DEFAULT_TARGET_KB}."
        ),
    )

    parser.add_argument(
        "--sans-perte",
        action="store_true",
        help="Compression sans perte uniquement (images inchangées).",
    )

    parser.add_argument(
        "--forcer",
        action="store_true",
        help="Recompresse aussi les PDF déjà compressés.",
    )

    args = parser.parse_args()

    if not 1 <= args.qualite <= 95:
        parser.error("--qualite doit être entre 1 et 95.")

    paths = [Path(value).resolve() for value in args.chemins]

    if args.offer_id:
        paths.append(find_candidature_dir(args.offer_id))

    if not paths:
        parser.error("Indique un dossier, un fichier ou --offer-id.")

    missing = [path for path in paths if not path.exists()]

    if missing:
        sys.exit("Introuvable : " + ", ".join(str(path) for path in missing))

    files = find_target_files(paths)

    if not files:
        print("Aucun fichier CV_LM_AMAVIGAN.pdf ou LM_x_AMAVIGAN.pdf trouvé.")
        return

    print(f"{len(files)} PDF à compresser.")

    total_before = 0
    total_after = 0

    for path in files:
        try:
            before, after, status = compress_pdf(
                path,
                quality=args.qualite,
                lossless_only=args.sans_perte,
                force=args.forcer,
                target_kb=args.cible_ko,
            )
        except Exception as error:
            print(f"  ERREUR {path.parent.name}/{path.name} : {error}")
            continue

        total_before += before
        total_after += after

        gain = f"-{100 * (before - after) // before} %" if after < before else ""

        print(
            f"  {path.parent.name}/{path.name} : {before // 1024} Ko -> "
            f"{after // 1024} Ko {gain} ({status})"
        )

    if total_before:
        print(
            f"\nTotal : {total_before / 1048576:.1f} Mo -> {total_after / 1048576:.1f} Mo "
            f"(-{100 * (total_before - total_after) // total_before} %)"
        )


if __name__ == "__main__":
    main()
