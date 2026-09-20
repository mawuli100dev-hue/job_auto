"""
generate_letter.py
Génère la lettre de motivation en se basant EXCLUSIVEMENT sur ce qui a été
réellement mis sur le CV (cv_data.json, produit par tailor_cv.py) + la
description de l'offre. Garantit une cohérence parfaite CV <-> lettre.

═══════════════════════════════════════════════════════════════════════════
ARCHITECTURE v11 (refonte + patches A-E, 2026-09-11)
═══════════════════════════════════════════════════════════════════════════
[historique v3-v11 inchangé, voir versions précédentes]

CORRECTIF v12 (2026-09-14) : support des candidatures spontanées (paramètre
`spontanee` traversant generate_plan/write_letter/critique_letter).

═══════════════════════════════════════════════════════════════════════════
CORRECTIF v14 (2026-09-14 - CHANGEMENT D'APPROCHE POUR L'OBJET, cause racine)
═══════════════════════════════════════════════════════════════════════════
Les v12/v13 demandaient au LLM d'écrire l'OBJET COMPLET ("Candidature
spontanée pour une alternance - X"), puis essayaient de RETIRER ce préfixe
avec des regex après coup, pour le réinjecter proprement. Problème de fond :
un LLM ne respecte jamais un format à 100%, donc il produisait des variantes
imprévisibles du préfixe ("Candidature spontanée -", "Offre spontanée pour...",
etc.) que la regex ne pouvait pas toutes anticiper -> doublons récurrents,
peu importe le nombre de patchs regex ajoutés.

CORRECTIF DE FOND : on ne demande plus JAMAIS au LLM d'écrire le préfixe.
Le JSON retourné par write_letter() contient maintenant un champ "theme"
(3-6 mots, ex: "Science des données", "Intelligence artificielle") au lieu
d'un "objet" complet. Le préfixe fixe ("Candidature spontanée pour une
alternance en ..." / "Candidature pour l'alternance - ...") est construit
PAR LE CODE PYTHON, dans build_objet(), avec un simple f-string. Aucune
regex de nettoyage de préfixe n'est plus nécessaire : le préfixe n'existe
que dans le code, jamais dans la sortie du LLM.
Le nettoyage résiduel (retrait de "Ingénieur/Expert/Senior/Lead", troncature
de longueur) est conservé, mais ne s'applique plus qu'au THÈME, pas à une
phrase entière à parser.
═══════════════════════════════════════════════════════════════════════════
"""

import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from letter_builder import fit_on_one_page, build_docx

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".." / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEFAULT_MODEL = "openai/gpt-4o-mini"

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

MOTS_CIBLE_MIN = 590
MOTS_CIBLE_MAX = 650
SEUIL_QUALITE = 8.5

THEME_DEFAUT = "science des données / informatique"


# ═══════════════════════════════════════════════════════════════════════════
# EXEMPLE DE STYLE POSITIF
# ═══════════════════════════════════════════════════════════════════════════

STYLE_EXEMPLE = """L'analyse de données hétérogènes pour en extraire des tendances fiables
suppose une méthode rigoureuse et reproductible. Dans mon projet d'étude des flux de dépôt
de poussières sahariennes, j'ai construit un pipeline Python croisant trois sources de
données sur 66 ans, avec calcul de tendances et quantification des biais relatifs entre
sources. Cette démarche m'a appris à documenter chaque étape d'un traitement, un réflexe
que je souhaite mettre au service de travaux portant sur des données plus complexes encore.

La structuration de bases de données relationnelles est au cœur de ma formation : en
deuxième année, j'ai conçu une base PostgreSQL de 15 tables normalisées, avec modèle
conceptuel, pipeline ETL et tests d'intégrité documentés. Je dispose également de
compétences en Python, R et Power BI, que j'ai pratiquées dans plusieurs projets
universitaires et que je souhaite mobiliser dans un contexte comme le vôtre.

Je suis disponible à partir d'octobre 2026 et mobile pour rejoindre votre équipe. Je
serais heureux de vous présenter ma démarche et d'échanger sur la manière dont je pourrais
contribuer à vos projets."""


# ═══════════════════════════════════════════════════════════════════════════
# RÈGLES DE FOND (injectées dans le prompt de rédaction)
# ═══════════════════════════════════════════════════════════════════════════

REGLE_POSTURE = """
POSTURE (règle la plus importante, à appliquer à chaque phrase) :

Hénoc est un étudiant en BUT Science des Données qui CHERCHE une alternance. Il est en
position de demandeur, pas d'expert qui a déjà fait ses preuves dans le métier de
l'entreprise. La lettre doit refléter cette position à chaque phrase, naturellement.

Concrètement :
- On ne dit jamais "je maîtrise X" (trop affirmatif). On dit "je dispose de compétences
  en X" ou "j'ai pratiqué X dans mes projets universitaires".
- On ne dit jamais "mes compétences me permettront de contribuer efficacement". On dit
  "je souhaite mobiliser ces compétences dans un contexte comme le vôtre".
- On ne dit jamais "je suis convaincu que" ou "je suis persuadé que" (arrogant).
  On dit "j'espère" ou "je souhaite", ou mieux : on donne un fait et on s'arrête.
- On ne dit jamais "cette expérience me positionne favorablement" ou "je suis reconnu
  pour". On expose le fait, le lecteur en tire ses conclusions.
- On ne dit jamais "je suis enthousiaste à l'idée de" (creux). On dit "je serais heureux
  de vous présenter ma démarche" (concret).
- Un lien entre une expérience et l'offre se formule comme une PISTE MESURÉE :
  "cette démarche me semble transposable à..." plutôt que "cette démarche est
  directement applicable à...".
- La lettre est intégralement à la 1ère personne. Le nom "Hénoc AMAVIGAN (masculin)" n'apparaît
  JAMAIS dans le corps (il est déjà dans l'en-tête, on n'a pas à le répéter).
- On ne dit jamais "je suis motivé par" ou "je suis passionné par" (creux). On décrit
  ce qui a été fait et les résultats obtenus.
- On ne dit jamais "Actuellement étudiant en" (creux). On utilise une formulation non générique.
"""

REGLE_SUR_INTERPRETATION = """
SUR-INTERPRÉTATION (règle non négociable) :

Ne jamais dire que le candidat A FAIT X simplement parce qu'il possède une compétence Y
qui POURRAIT servir à faire X. Une compétence reste une compétence, elle ne devient pas
une expérience vécue dans le domaine métier précis de l'offre.

Exemples :
- CV: pipeline Python d'analyse climatique | Offre: optimisation d'algorithmes IA
  BON  : "La rigueur méthodologique développée dans ce projet est une démarche que je
          souhaite transposer à un contexte différent."
  MAUVAIS : "Cette démarche est directement applicable à l'optimisation de vos
             algorithmes."

- CV: dashboard Streamlit | Offre: digitalisation des processus
  BON  : "Cette expérience m'a permis de développer des compétences en conception
          d'outils de restitution."
  MAUVAIS : "Cette expérience m'a préparé à digitaliser vos processus."

- CV: SQL + base de données relationnelle | Offre: base de données fournisseurs
  BON  : "Ces compétences constituent une base que je souhaite mettre à profit pour
          vos projets."
  MAUVAIS : "J'ai contribué à la fiabilisation des bases fournisseurs."

RAPPEL SPÉCIAL CANDIDATURE SPONTANÉE : quand l'offre ne décrit qu'une entreprise sans
exigence technique précise, ce risque est ENCORE PLUS GRAND, car il n'y a aucun "besoin"
réel à respecter : n'invente JAMAIS un besoin technique de l'entreprise qui n'est pas
explicitement mentionné dans sa description.

Règle pratique : quand tu présentes une expérience, dis ce qui a été FAIT (verbe au
passé composé, résultat concret), puis PASSE À LA SUITE. Ne conclus pas par une
projection vague sur son utilité future dans le métier de l'offre.
"""

REGLE_ANCRAGE = """
ANCRAGE ENTREPRISE (contrainte mesurable) :

La PREMIÈRE PHRASE de CHAQUE paragraphe 2, 3 et 4 doit citer explicitement l'entreprise,
le poste, ou un besoin/mot-clé précis tiré de l'offre. Il ne suffit pas que l'entreprise
soit mentionnée "quelque part" dans le paragraphe.

PREMIÈRES PHRASES ACCEPTABLES (offre détaillée) :
- "Le besoin de [reformulation d'un besoin de l'offre] rejoint la démarche que j'ai
   suivie dans..."
- "Chez [Entreprise], [reformulation d'un enjeu de l'offre] suppose de [action] ; mon
   expérience de [...] a consisté à..."
- "Votre offre mentionne [élément précis] ; dans mon projet de [...], j'ai..."

PREMIÈRES PHRASES ACCEPTABLES (candidature SPONTANÉE, pas de besoin précis connu) :
- "[Entreprise], [secteur/activité connue de l'entreprise si disponible, sinon rien
   d'inventé], est le type de structure où je souhaiterais mettre mes compétences au
   service de projets data concrets."
- "Basée à [ville], [Entreprise] représente le type d'environnement où je souhaite
   mobiliser ma formation en science des données."
- "Chez [Entreprise], une équipe technique pourrait un jour avoir besoin d'exploiter des
   données ; mon expérience de [...] a consisté à..."

PREMIÈRES PHRASES INTERDITES (dans tous les cas) :
- "Dans le cadre de ma recherche..."   (part du candidat)
- "Je dispose de compétences en..."     (part du candidat)
- "J'ai eu l'opportunité de..."         (part du candidat)
- "Mon expérience m'a permis de..."     (part du candidat)

Sur l'ensemble de la lettre : au maximum 2 phrases peuvent commencer par
"Je suis" / "Je serais" / "Je serai". Varie les débuts : nom de l'entreprise, connecteur
logique ("Cette exigence...", "Ce même besoin..."), sujet de l'action ("Mon expérience
de...", "Cette démarche...").
"""

REGLE_LANGUE_CREUSE = """
LANGUE CREUSE À BANNIR (familles entières, pas seulement les exemples) :

Famille "défi/enjeu vague" :
  à bannir : "un défi", "un défi passionnant", "un enjeu crucial/majeur/fondamental",
  "un enjeu central". À la place : décris le problème technique concret (quel type de
  données, quel type de traitement).

Famille "résonance abstraite" :
  à bannir : "résonne avec", "trouve un écho", "me parle", "correspond à mes aspirations".
  À la place : explique EN QUOI concrètement, avec un fait.

Famille "qualificatifs d'intensité vagues" :
  à bannir : "passionnant", "enthousiaste à l'idée de", "particulièrement intéressé",
  "particulièrement motivé", "approche innovante", "solution innovante", "m'intéresse
  particulièrement", "opportunité enrichissante". À la place : zéro qualificatif
  d'intensité, laisse le fait concret parler.

Famille "affirmations excessives" :
  à bannir : "crucial", "essentiel", "indispensable", "parfaitement", "solide
  compréhension", "solide formation", "je suis reconnu pour", "s'inscrit parfaitement",
  "me semble approprié", "me semblent appropriées", "que je possède".

Famille "hedges conditionnels" (le pire tic constaté) :
  à bannir : "pourrait être mis à profit", "pourrait apporter une valeur ajoutée",
  "pourrait faciliter", "pourrait s'avérer pertinent", "pourraient être transposées",
  "peut permettre de", "peut contribuer à", "mes compétences me permettront de
  contribuer efficacement", "J'espère que cette démarche me permettra de mobiliser".
  Maximum UNE seule phrase de ce type dans TOUTE la lettre.

Test mental avant de valider une phrase : "Si je remplace le nom de l'entreprise par un
autre nom du même secteur, cette phrase reste-t-elle vraie mot pour mot ?" Si oui, elle
est trop générique, réécris-la.
"""

REGLE_INTERDICTIONS_SPECIFIQUES = """
INTERDICTIONS SPÉCIFIQUES (issues de tests réels) :

- Ne jamais transformer une compétence générique (Python, R, SQL, dashboards) en
  solution au problème métier précis de l'offre. "Compétences en Python et R
  directement mobilisables pour le développement de solutions d'identification des
  polymères" est INTERDIT. Dire à la place : "je dispose de compétences en Python et
  R, que je souhaite mettre au service de vos projets".

- Pas de caractères "—" (cadratin) ou "–" (demi-cadratin). Uniquement virgules,
  points, ou tiret simple "-" entouré d'espaces.

- Pour décrire une expérience : verbe au passé composé, sujet "j'ai" ou "mon projet",
  résultat concret (chiffre, méthode, livrable). Pas de commentaire sur la valeur de
  l'expérience.

- N'écris JAMAIS à la 3e personne : pas de "Hénoc AMAVIGAN", pas de "le candidat",
  pas de "Hénoc, étudiant en...". Tout est à la 1ère personne : "je", "mon", "j'ai".
"""

REGLE_MODE_SPONTANEE = """
CONTEXTE SPÉCIAL : CANDIDATURE SPONTANÉE (pas de poste publié)

Cette lettre est une CANDIDATURE SPONTANÉE : l'entreprise n'a publié AUCUNE offre, la
"description" fournie n'est qu'un résumé générique de 3-4 phrases sur l'entreprise
elle-même (secteur, ville, activité connue), PAS un besoin technique précis.

Conséquences concrètes :
1. N'invente JAMAIS un "besoin" technique de l'entreprise qui n'est pas explicitement
   dans sa description.
2. Ancre chaque paragraphe sur l'ENTREPRISE elle-même (son nom, son secteur si connu,
   sa ville) plutôt que sur un besoin fictif.
3. Pour le choix des expériences : privilégie celles qui montrent le niveau technique
   le plus solide et la plus grande POLYVALENCE.
4. Sois explicite sur la démarche spontanée dans le premier paragraphe.
"""


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION AUTOMATIQUE (regex)
# ═══════════════════════════════════════════════════════════════════════════

FORMULATIONS_INTERDITES = [
    r"\b(défi|défis)\b",
    r"\benjeu(x)? (crucial|cruciale|cruciaux|cruciales|majeur|majeure|majeurs|majeures|"
    r"fondamental|fondamentale|fondamentaux|fondamentales|central|centrale|centraux|centrales)\b",
    r"\brésonne\b",
    r"\btrouve(nt)? un écho\b",
    r"\bme parle\b",
    r"\bcorrespond(ent)? à mes aspirations\b",
    r"\b(passionnant|passionnante|passionnants|passionnantes)\b",
    r"\b(enthousiaste|enthousiasmé|enthousiasmée) à l'idée\b",
    r"\bparticulièrement (intéressé|intéressée|motivé|motivée|convaincu|convaincue)\b",
    r"\bm'intéresse particulièrement\b",
    r"\b(serait|serait une|est une) (opportunité|chance) "
    r"(enrichissante?|intéressante?|unique|formidable|exceptionnelle?)\b",
    r"\b(approche|solution|solutions|projet|projets|initiative|démarche) "
    r"(innovant|innovante|innovants|innovantes)\b",
    r"\b(crucial|cruciale|cruciaux|cruciales|essentiel|essentielle|essentiels|essentielles|"
    r"indispensable|indispensables)\b",
    r"\bparfaitement\b",
    r"\bsolide (compréhension|maîtrise|connaissance|connaissances|base|bases|"
    r"formation|expérience|parcours|bagage)\b",
    r"\bje suis reconnu\b",
    r"\b(me|nous) positionne(nt)? favorablement\b",
    r"\bs'inscrit parfaitement\b",
    r"\bs'inscrirait parfaitement\b",
    r"\bme semble(nt)? (approprié|appropriée|appropriés|appropriées|adapté|adaptée|adaptés|adaptées)\b",
    r"\bque je possède\b",
    r"\b(peut|peuvent|pourrait|pourraient|pourra|pourront|sera|serait|seraient) "
    r"(être (mise?|mis) à profit|apporter|faciliter|permettre|contribuer|aider|servir|"
    r"s'avérer|être (utile|utiles|bénéfique|bénéfiques|pertinent|pertinente|pertinents|"
    r"pertinentes|précieux|précieuse|précieuses|transposé|transposée|transposés|transposées|"
    r"transposable|transposables))\b",
    r"\bme permet(tent|tra|tront)? de contribuer\b",
    r"\bnous permet(tent|tra|tront)? de contribuer\b",
    r"\bJ'espère que (cette|cela|ce) (démarche|expérience|projet) me permettra\b",
    r"\bvaleur ajoutée\b",
    r"\brenforce ma capacité\b",
    r"\brenforce(nt)? (ma|notre) capacité\b",
]

DEBUT_CANDIDAT = re.compile(
    r"^(Je\b|J'ai\b|Dans le cadre de ma\b|Dans le cadre de mon\b|Mon\b|Ma\b|Mes\b|"
    r"Au cours de mon\b|Lors de mon\b|Durant mon\b)",
    flags=re.IGNORECASE,
)

DEBUT_JE_SUIS = re.compile(
    r"(?m)(?:^|(?<=[.!?]\s))(Je suis|Je serais|Je serai)\b",
)


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def first_sentence(paragraph: str) -> str:
    parts = split_sentences(paragraph)
    return parts[0] if parts else ""


def validate_letter(objet: str, paragraphs: list[str], entreprise_nom: str) -> list[str]:
    violations: list[str] = []
    full_text = " ".join(paragraphs)
    full_with_objet = full_text + " " + objet

    if "—" in full_with_objet or "–" in full_with_objet:
        violations.append("Caractères interdits — ou – présents dans la lettre.")

    for pattern in FORMULATIONS_INTERDITES:
        m = re.search(pattern, full_text, flags=re.IGNORECASE)
        if m:
            violations.append(f"Formulation interdite détectée : « {m.group(0)} ».")

    if re.search(r"\bHénoc\s+AMAVIGAN\b", full_text, re.IGNORECASE):
        violations.append(
            "Le nom complet du candidat apparaît dans le corps de la lettre "
            "(à la 3e personne). Tout doit être à la 1ère personne."
        )
    if re.search(r"\b(le candidat|la candidate)\b", full_text, re.IGNORECASE):
        violations.append(
            "Auto-référence à la 3e personne détectée (« le candidat » / « la candidate »)."
        )
    if re.search(r"\bAMAVIGAN,\s+étudiant\b", full_text, re.IGNORECASE):
        violations.append(
            "Auto-référence à la 3e personne détectée (« AMAVIGAN, étudiant... »)."
        )

    for idx in (1, 2, 3):
        if idx >= len(paragraphs):
            continue
        fs = first_sentence(paragraphs[idx])
        if not fs:
            continue
        if DEBUT_CANDIDAT.match(fs):
            violations.append(
                f"Paragraphe {idx + 1} : 1ère phrase centrée candidat "
                f"(« {fs[:70]}... »). Doit partir de l'entreprise/du besoin."
            )
            continue
        cité = False
        if entreprise_nom and entreprise_nom.lower() in fs.lower():
            cité = True
        elif re.search(
            r"\b(votre offre|votre poste|votre besoin|vos besoins|l'offre|le poste|"
            r"chez vous|votre entreprise|votre structure|votre équipe|ce poste|"
            r"cette alternance|votre projet|vos projets)\b",
            fs, re.IGNORECASE,
        ):
            cité = True
        if not cité:
            violations.append(
                f"Paragraphe {idx + 1} : 1ère phrase ne cite ni l'entreprise, ni le "
                f"poste, ni un besoin de l'offre (« {fs[:70]}... »)."
            )

    nb_je_suis = len(DEBUT_JE_SUIS.findall(full_text))
    if nb_je_suis > 2:
        violations.append(
            f"Trop de phrases commencent par 'Je suis/Je serais/Je serai' "
            f"({nb_je_suis}, maximum 2)."
        )

    return list(dict.fromkeys(violations))


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def find_cv_data_path(offer_id: str, base_dir: Path) -> Path:
    candidatures_dir = base_dir / "data" / "candidatures"
    matches = list(candidatures_dir.glob(f"*/*_{offer_id}/cv_data.json"))
    if not matches:
        raise FileNotFoundError(
            f"Aucun cv_data.json trouvé pour l'offre {offer_id}. "
            f"Lance d'abord tailor_cv.py sur cette offre."
        )
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def clean_lieu(lieu_brut: str) -> str:
    if not lieu_brut:
        return ""
    nettoye = re.sub(r"^\s*\d{1,3}\s*-\s*", "", lieu_brut).strip()
    return nettoye or lieu_brut.strip()


def remove_forbidden_chars(text: str) -> str:
    if not text:
        return text
    text = text.replace("—", " - ").replace("–", " - ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+-\s+", " - ", text)
    return text


def extract_cv_content(cv_data: dict) -> tuple[str, str]:
    experiences_text = "\n\n".join(
        f"- {e['titre']} ({e.get('structure', '')}, {e.get('periode', '')}) :\n  "
        + " ".join(b.replace('**', '') for b in e["bullets"])
        for e in cv_data.get("experiences_sur_cv", [])
    )
    competences_text = "\n".join(
        f"- {cat} : {', '.join(items)}"
        for cat, items in cv_data.get("competences_sur_cv", {}).items()
    )
    return experiences_text, competences_text


def build_offer_text_from_saved(offer_saved: dict, description_complete: str) -> str:
    return (
        f"Intitulé: {offer_saved.get('intitule', '')}\n"
        f"Entreprise: {offer_saved.get('entreprise', '')}\n"
        f"Lieu: {offer_saved.get('lieu', '')}\n"
        f"Description: {description_complete[:2500]}"
    )


def word_count(paragraphs: list[str]) -> int:
    return sum(len(p.split()) for p in paragraphs)


def clean_theme(theme: str, intitule_offre: str = "") -> str:
    """v14 : nettoie UNIQUEMENT un thème court (pas une phrase avec préfixe).
    Retire les titres de poste inadaptés, tronque, et retombe sur un thème
    générique si le LLM n'a rien renvoyé d'exploitable."""
    t = (theme or "").strip()
    t = re.sub(r"\s*\(H/F\)\s*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(Ingénieur|Ingénieure|Expert|Experte|Senior|Lead)\b\s*", "", t, flags=re.IGNORECASE)
    # Retire un éventuel préfixe que le LLM aurait quand même ajouté par erreur.
    t = re.sub(r"^Candidature\s*(spontanée)?\s*(pour\s+(l'|une\s+)?alternance)?\s*(en|[-:])?\s*",
               "", t, flags=re.IGNORECASE)
    t = re.sub(r"^Alternance\s*(en|[-:])?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" -,:;")
    if len(t) > 60:
        t = t[:57].rstrip() + "..."
    if not t:
        fallback = re.sub(r"\s*\(H/F\)\s*$", "", intitule_offre or "", flags=re.IGNORECASE)
        fallback = re.sub(r"\b(Ingénieur|Ingénieure|Expert|Senior|Lead)\b\s*",
                          "", fallback, flags=re.IGNORECASE)
        fallback = fallback.split(",")[0].strip()
        t = fallback[:57] if fallback else THEME_DEFAUT
    return t


def build_objet(theme: str, intitule_offre: str, spontanee: bool) -> str:
    """v14 : construit l'objet ENTIÈREMENT en Python à partir d'un thème
    court. Le préfixe fixe n'est JAMAIS produit par le LLM, donc aucun risque
    de doublon quel que soit ce que le LLM a renvoyé dans "theme"."""
    theme_propre = clean_theme(theme, intitule_offre)
    if spontanee:
        return f"Candidature spontanée pour une alternance en {theme_propre}"
    return f"Candidature pour l'alternance - {theme_propre}"


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 1 : PLAN (Patch A - proximité thématique + validation)
# ═══════════════════════════════════════════════════════════════════════════

def generate_plan(client: OpenAI, model: str, offer_text: str,
                  experiences_text: str, competences_text: str,
                  spontanee: bool = False) -> dict:
    if spontanee:
        regle_selection = """RÈGLE DE SÉLECTION (candidature SPONTANÉE, pas de besoin technique connu) :

Il n'y a PAS de besoin technique précis à faire correspondre : l'offre ne décrit que
l'entreprise elle-même. Pour chaque paragraphe, choisis donc l'expérience du CV qui
démontre le NIVEAU TECHNIQUE LE PLUS SOLIDE et qui, mise bout à bout avec les autres
expériences choisies, montre la plus grande POLYVALENCE du candidat.

Pour le champ "besoin_offre" de chaque paragraphe : n'invente AUCUN besoin technique.
Utilise une reformulation honnête de ce qui est réellement connu de l'entreprise.

Pour le champ "proximite_thematique" : indique toujours "aucune", sauf si la
description de l'entreprise mentionne vraiment un domaine technique explicite (rare)."""
    else:
        regle_selection = """RÈGLE DE PROXIMITÉ THÉMATIQUE (la plus importante pour le choix des expériences) :

Pour chaque paragraphe, tu dois choisir l'expérience du CV dont la NATURE TECHNIQUE
est la plus proche du besoin de l'offre. La nature technique veut dire : quel TYPE
de données, quel TYPE de traitement.

Exemples de proximité correcte :
- Offre parle d'IMAGES (caméras, hyperspectral, vision) -> choisir une expérience
  sur des IMAGES (segmentation, traitement d'image).
- Offre parle de TEXTE (NLP, documents) -> choisir une expérience sur du TEXTE.
- Offre parle de DONNÉES TABULAIRES/statistiques -> choisir une expérience sur des
  données tabulaires.
- Offre parle de BASES DE DONNÉES relationnelles -> choisir l'expérience de
  modélisation BDD.

Si aucune expérience du CV n'a la bonne nature technique, choisis celle dont la
MÉTHODE est la plus proche, ET INDIQUE "methodologique" ou "aucune" pour
proximite_thematique."""

    note_spontanee = "\n\nRAPPEL : cette candidature est SPONTANÉE, aucune offre n'a été publiée.\n" if spontanee else ""

    prompt = f"""Tu prépares un PLAN pour une lettre de motivation. Tu ne rédiges AUCUNE
phrase de la lettre pour l'instant : tu produis uniquement un plan JSON structuré.

PROFIL : Hénoc AMAVIGAN, étudiant en 3e année de BUT Science des Données.
OBJECTIF : lettre de candidature pour une ALTERNANCE.{note_spontanee}

EXPÉRIENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
{experiences_text}

COMPÉTENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
{competences_text}

OFFRE VISÉE :
{offer_text}

{regle_selection}

RÈGLES DU PLAN :
1. Chaque "besoin_offre" doit être une citation courte ou reformulation précise
   d'un élément textuel de l'offre (ou, en mode spontané, une reformulation honnête
   de ce qui est réellement connu de l'entreprise, sans invention).
2. Chaque "fait_concret_cv" doit être un fait vérifiable (chiffre, méthode, livrable).
3. Le champ "amorce" du paragraphe 2/3/4 DOIT commencer par l'entreprise, le poste
   ou un besoin de l'offre. JAMAIS par "Je", "J'ai", "Mon", "Ma", "Hénoc".
4. Le paragraphe 4 liste des compétences génériques du CV et des qualités humaines.
5. La lettre finale visera 550 à 650 mots au total.
6. Les paragraphes 2 et 3 doivent utiliser DEUX expériences DIFFÉRENTES du CV.

Réponds UNIQUEMENT en JSON, format strict :
{{
  "paragraphe_1": {{"element_offre_concret": "...", "lien_candidat": "...", "nb_phrases_prevues": 5}},
  "paragraphe_2": {{"besoin_offre": "...", "experience_cv": "...", "nature_technique_experience": "...", "fait_concret_cv": "...", "proximite_thematique": "directe | methodologique | aucune", "amorce": "...", "nb_phrases_prevues": 7}},
  "paragraphe_3": {{"besoin_offre": "...", "experience_cv": "...", "nature_technique_experience": "...", "fait_concret_cv": "...", "proximite_thematique": "directe | methodologique | aucune", "amorce": "...", "nb_phrases_prevues": 7}},
  "paragraphe_4": {{"besoin_offre": "...", "competences_cv": ["...", "..."], "qualites_cv": ["...", "..."], "amorce": "...", "nb_phrases_prevues": 5}},
  "paragraphe_5": {{"disponibilite": "...", "mobilite": "...", "ouverture_entretien": "...", "nb_phrases_prevues": 3}}
}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1400,
    )
    return json.loads(resp.choices[0].message.content)


def validate_plan(plan: dict, spontanee: bool = False) -> list[str]:
    violations = []
    for key in ("paragraphe_2", "paragraphe_3", "paragraphe_4"):
        p = plan.get(key, {})
        amorce = (p.get("amorce") or "").strip()
        if not amorce:
            violations.append(f"{key}: amorce manquante.")
            continue
        if re.match(r"^(Je\b|J'ai\b|Mon\b|Ma\b|Mes\b|Hénoc\b)", amorce, re.IGNORECASE):
            violations.append(
                f"{key}: l'amorce commence par un sujet candidat : « {amorce[:60]}... »"
            )

    exp2 = (plan.get("paragraphe_2", {}).get("experience_cv") or "").strip().lower()
    exp3 = (plan.get("paragraphe_3", {}).get("experience_cv") or "").strip().lower()
    if exp2 and exp3 and exp2 == exp3:
        violations.append(
            "Paragraphes 2 et 3 : la même expérience est utilisée deux fois."
        )

    for key in ("paragraphe_2", "paragraphe_3"):
        p = plan.get(key, {})
        pt = (p.get("proximite_thematique") or "").strip().lower()
        if pt not in ("directe", "methodologique", "aucune"):
            violations.append(
                f"{key}: proximite_thematique invalide (« {pt} »)."
            )

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 2 : RÉDACTION (plan injecté comme contrainte forte)
# ═══════════════════════════════════════════════════════════════════════════

def write_letter(client: OpenAI, model: str, offer_text: str,
                 experiences_text: str, competences_text: str,
                 plan: dict, feedback_longueur: str = "",
                 spontanee: bool = False) -> tuple[list[str], str]:
    """v14 : demande un "theme" court au lieu d'un "objet" complet. Le
    préfixe fixe est construit séparément par build_objet()."""

    entreprise_nom = ""
    m = re.search(r"Entreprise:\s*(.+)", offer_text)
    if m:
        entreprise_nom = m.group(1).strip()

    feedback_block = (
        f"\n\nCONSIGNE SUPPLÉMENTAIRE (retour de la génération précédente) :\n"
        f"{feedback_longueur}\n"
        if feedback_longueur else ""
    )

    bloc_spontanee = f"\n═══ CONTEXTE CANDIDATURE SPONTANÉE ═══\n{REGLE_MODE_SPONTANEE}\n" if spontanee else ""

    consigne_p1 = (
        "P1 (5-6 phrases) : annonce clairement qu'il s'agit d'une candidature spontanée "
        "(aucune offre publiée), présente brièvement ce qui motive cette démarche vers "
        "cette entreprise précise, sans inventer de besoin technique."
        if spontanee else
        "P1 : accroche développée à partir d'un élément concret de l'offre."
    )

    prompt = f"""Tu rédiges une lettre de motivation en français pour Hénoc AMAVIGAN,
étudiant en 3e année de BUT Science des Données, candidat à une ALTERNANCE.

Tu dois suivre STRICTEMENT le plan ci-dessous.
{bloc_spontanee}
═══ PLAN À SUIVRE ═══
{json.dumps(plan, ensure_ascii=False, indent=2)}
═════════════════════

EXPÉRIENCES SUR LE CV (n'invente rien d'autre) :
{experiences_text}

COMPÉTENCES SUR LE CV (n'invente rien d'autre) :
{competences_text}

OFFRE VISÉE :
{offer_text}

═══ RÈGLE DE POSTURE (la plus importante) ═══
{REGLE_POSTURE}

═══ RÈGLE DE SUR-INTERPRÉTATION ═══
{REGLE_SUR_INTERPRETATION}

═══ RÈGLE D'ANCRAGE ENTREPRISE ═══
{REGLE_ANCRAGE}

═══ LANGUE CREUSE À BANNIR ═══
{REGLE_LANGUE_CREUSE}

═══ INTERDICTIONS SPÉCIFIQUES ═══
{REGLE_INTERDICTIONS_SPECIFIQUES}

═══ EXEMPLE DE STYLE À IMITER ═══
{STYLE_EXEMPLE}
---

CONSIGNES DE RÉDACTION :

1. Rédige exactement 5 paragraphes. TOTAL IMPÉRATIF : {MOTS_CIBLE_MIN} à {MOTS_CIBLE_MAX}
   mots. Répartition cible :
   - {consigne_p1}
   - P2 : 130-160 mots (6-8 phrases)
   - P3 : 130-160 mots (6-8 phrases)
   - P4 : 100-130 mots (5-6 phrases)
   - P5 : 50-70 mots (3-4 phrases)

2. Aucune formule d'appel ni de politesse finale (je les ajoute moi-même).

3. Pas de "—" ni "–". Uniquement virgules, points, tiret simple "-".

4. Au maximum 2 phrases commençant par "Je suis" / "Je serais" / "Je serai".

5. Tu écris UNIQUEMENT à la première personne. Tu n'écris JAMAIS le nom
   "Hénoc AMAVIGAN" dans le corps de la lettre, ni "le candidat".

6. IMPORTANT - CHAMP "theme" : donne UNIQUEMENT un thème court de 3 à 6 mots résumant
   le domaine visé (ex: "science des données", "intelligence artificielle appliquée
   au tri", "informatique décisionnelle"). N'écris JAMAIS les mots "Candidature",
   "spontanée", "alternance", "pour l'alternance" dans ce champ : ce sont des mots que
   le script ajoute lui-même automatiquement autour de ton thème. N'utilise jamais les
   mots "Ingénieur", "Expert", "Senior" ou "Lead" dans le thème.{feedback_block}

Réponds UNIQUEMENT en JSON :
{{"theme": "...", "paragraphes": ["...", "...", "...", "...", "..."]}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.35,
        max_tokens=2800,
    )
    result = json.loads(resp.choices[0].message.content)
    paragraphes = [remove_forbidden_chars(p) for p in result.get("paragraphes", [])]
    theme = remove_forbidden_chars(result.get("theme", ""))
    return paragraphes, theme


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 3 : CRITIQUE (score de qualité par un LLM-juge sévère)
# ═══════════════════════════════════════════════════════════════════════════

def critique_letter(client: OpenAI, model: str, offer_text: str,
                    paragraphs: list[str], spontanee: bool = False) -> dict:
    note_spontanee = (
        "\nIMPORTANT : c'est une CANDIDATURE SPONTANÉE, il n'y a pas de besoin technique "
        "précis à respecter. Ne pénalise PAS l'absence de correspondance technique précise.\n"
        if spontanee else ""
    )

    prompt = f"""Tu es un recruteur sévère et expérimenté. Tu évalues une lettre de
motivation écrite par un étudiant en BUT Science des Données pour une alternance.
{note_spontanee}
Contexte de l'offre :
{offer_text[:1500]}

Lettre à évaluer :
{json.dumps(paragraphs, ensure_ascii=False, indent=2)}

Note la lettre sur 10 selon ces 5 critères, chacun noté sur 10 puis moyenné :
1. Ancrage entreprise
2. Humilité
3. Absence de sur-interprétation
4. Densité factuelle
5. Absence de langue creuse

Réponds UNIQUEMENT en JSON :
{{
  "score": 8.5,
  "scores_detail": {{"ancrage_entreprise": 9, "humilite": 8, "pas_sur_interpretation": 9, "densite_factuelle": 8, "pas_langue_creuse": 8}},
  "phrases_problematiques": ["...", "..."],
  "points_forts": ["...", "..."],
  "recommandations": ["...", "..."]
}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1000,
    )
    return json.loads(resp.choices[0].message.content)


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 3bis : RÉÉCRITURE CIBLÉE
# ═══════════════════════════════════════════════════════════════════════════

def rewrite_targeted(client: OpenAI, model: str, paragraphs: list[str],
                     problemes: list[str]) -> list[str]:
    if not problemes:
        return paragraphs

    prompt = f"""Voici une lettre de motivation et une liste de phrases ou bouts de
phrases identifiés comme problématiques. Réécris UNIQUEMENT ces passages, dans leur
contexte, sans modifier le reste du texte ni sa longueur globale.

PASSAGES À RÉÉCRIRE :
{json.dumps(problemes, ensure_ascii=False, indent=2)}

PARAGRAPHES ACTUELS :
{json.dumps(paragraphs, ensure_ascii=False, indent=2)}

RAPPEL DE LA POSTURE À RESPECTER :
{REGLE_POSTURE}

Réponds UNIQUEMENT en JSON, avec les 5 paragraphes complets (même ceux non modifiés) :
{{"paragraphes": ["...", "...", "...", "...", "..."]}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.25,
        max_tokens=2800,
    )
    result = json.loads(resp.choices[0].message.content)
    new_paras = result.get("paragraphes", paragraphs)
    return [remove_forbidden_chars(p) for p in new_paras]


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offer-id", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY doit être défini dans .env")

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

    cv_data_path = find_cv_data_path(args.offer_id, BASE_DIR)
    dossier = cv_data_path.parent
    print(f"CV trouvé : {cv_data_path}")

    with open(cv_data_path, encoding="utf-8") as f:
        cv_data = json.load(f)

    offer_saved = cv_data.get("offer", {})
    spontanee = bool(cv_data.get("candidature_spontanee", False))

    offre_txt_path = dossier / "offre.txt"
    description_complete = ""
    if offre_txt_path.exists():
        with open(offre_txt_path, encoding="utf-8") as f:
            content = f.read()
            marker = "--- Description complète de l'offre ---"
            if marker in content:
                description_complete = content.split(marker, 1)[1].strip()

    experiences_text, competences_text = extract_cv_content(cv_data)
    offer_text = build_offer_text_from_saved(offer_saved, description_complete)

    intitule_offre = offer_saved.get("intitule", "").strip()
    entreprise = remove_forbidden_chars(offer_saved.get("entreprise", "").strip()) or "Entreprise"

    print(f"Mode : {'CANDIDATURE SPONTANÉE' if spontanee else 'réponse à une offre'}")

    print("\n[Passe 1/3] Génération du plan...")
    plan = generate_plan(client, args.model, offer_text,
                         experiences_text, competences_text, spontanee=spontanee)
    plan_violations = validate_plan(plan, spontanee=spontanee)
    tentatives_plan = 0
    while plan_violations and tentatives_plan < 2:
        tentatives_plan += 1
        print(f"Plan invalide ({len(plan_violations)} problèmes), régénération {tentatives_plan}/2...")
        for v in plan_violations:
            print(f"  - {v}")
        plan = generate_plan(client, args.model, offer_text,
                             experiences_text, competences_text, spontanee=spontanee)
        plan_violations = validate_plan(plan, spontanee=spontanee)
    if args.verbose:
        print("Plan retenu :")
        print(json.dumps(plan, ensure_ascii=False, indent=2)[:1800])

    print("\n[Passe 2/3] Rédaction de la lettre à partir du plan...")
    paragraphs, theme = write_letter(client, args.model, offer_text,
                                     experiences_text, competences_text, plan,
                                     spontanee=spontanee)

    if not paragraphs:
        raise RuntimeError("Le LLM n'a renvoyé aucun paragraphe.")

    objet = build_objet(theme, intitule_offre, spontanee)
    nb_mots = word_count(paragraphs)
    violations = validate_letter(objet, paragraphs, entreprise)
    print(f"Thème brut reçu : « {theme} » -> Objet construit : « {objet} »")
    print(f"Longueur : {nb_mots} mots. Violations regex : {len(violations)}")
    for v in violations:
        print(f"  - {v}")

    tentatives = 0
    while violations and tentatives < 2:
        tentatives += 1
        print(f"\nRégénération complète {tentatives}/2 (violations regex persistantes)...")
        paragraphs, theme = write_letter(client, args.model, offer_text,
                                         experiences_text, competences_text, plan,
                                         spontanee=spontanee)
        objet = build_objet(theme, intitule_offre, spontanee)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)
        print(f"Longueur : {nb_mots} mots. Violations regex : {len(violations)}")

    tentatives_longueur = 0
    while (nb_mots < MOTS_CIBLE_MIN - 30 or nb_mots > MOTS_CIBLE_MAX + 80) and tentatives_longueur < 2:
        tentatives_longueur += 1
        if nb_mots < MOTS_CIBLE_MIN - 30:
            feedback = (
                f"Ta réponse précédente ne faisait que {nb_mots} mots, alors que la cible "
                f"est {MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX}. Développe BEAUCOUP plus chaque "
                f"paragraphe avec des précisions techniques concrètes tirées du CV."
            )
        else:
            feedback = (
                f"Ta réponse faisait {nb_mots} mots, trop long. Condense en gardant "
                f"tous les faits concrets, cible {MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX} mots."
            )
        print(f"\nLongueur hors cible ({nb_mots} mots), régénération {tentatives_longueur}/2...")
        paragraphs, theme = write_letter(
            client, args.model, offer_text, experiences_text, competences_text,
            plan, feedback_longueur=feedback, spontanee=spontanee,
        )
        objet = build_objet(theme, intitule_offre, spontanee)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)
        print(f"Nouvelle longueur : {nb_mots} mots. Violations : {len(violations)}")

    print("\n[Passe 3/3] Évaluation par un LLM-juge sévère...")
    critique = critique_letter(client, args.model, offer_text, paragraphs, spontanee=spontanee)
    score = critique.get("score", 0)
    detail = critique.get("scores_detail", {})
    phrases_pb = critique.get("phrases_problematiques", [])

    print(f"\n  Score global : {score}/10 (seuil visé : {SEUIL_QUALITE})")
    for k, v in detail.items():
        print(f"    {k} : {v}/10")
    if critique.get("points_forts"):
        print("  Points forts :")
        for p in critique["points_forts"]:
            print(f"    + {p}")
    if phrases_pb:
        print("  Phrases problématiques :")
        for p in phrases_pb:
            print(f"    ! {p}")

    if (score < SEUIL_QUALITE or violations) and (phrases_pb or violations):
        print(f"\nRéécriture ciblée sur les phrases fautives...")
        problemes_a_corriger = list(phrases_pb) + violations
        paragraphs = rewrite_targeted(client, args.model, paragraphs, problemes_a_corriger)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)

        critique2 = critique_letter(client, args.model, offer_text, paragraphs, spontanee=spontanee)
        score2 = critique2.get("score", 0)
        print(f"Score après réécriture : {score2}/10")
        if score2 > score:
            score = score2
            critique = critique2

    today = datetime.now()
    ville_date = f"Carcassonne, le {today.day} {MOIS_FR[today.month - 1]} {today.year}"
    lieu_entreprise = remove_forbidden_chars(clean_lieu(offer_saved.get("lieu", "")))

    pdf_path = dossier / "LM_Henoc_AMAVIGAN.pdf"
    html_path = dossier / "LM_Henoc_AMAVIGAN.html"
    docx_path = dossier / "LM_Henoc_AMAVIGAN.docx"

    fit_info = fit_on_one_page(entreprise, lieu_entreprise, ville_date, objet,
                               paragraphs, pdf_path, html_path)
    build_docx(entreprise, lieu_entreprise, ville_date, objet, paragraphs, docx_path)

    statut = "OK, tient sur 1 page" if fit_info["fitted"] else "NE TIENT PAS sur 1 page"
    print(f"\n═══════ RÉSULTAT ═══════")
    print(f"Mode : {'CANDIDATURE SPONTANÉE' if spontanee else 'réponse à une offre'}")
    print(f"Objet final : {objet}")
    print(f"Score qualité : {score}/10 (seuil visé : {SEUIL_QUALITE})")
    print(f"Longueur : {nb_mots} mots (cible {MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX})")
    print(f"Violations regex résiduelles : {len(violations)}")
    print(f"PDF : {pdf_path}  ({statut})")
    print(f"Word (secours) : {docx_path}")

    if score < SEUIL_QUALITE:
        print(f"\n⚠ Score inférieur à {SEUIL_QUALITE}. Recommandations du critique :")
        for r in critique.get("recommandations", []):
            print(f"    - {r}")
    else:
        print(f"\n✓ Lettre au-dessus du seuil de qualité.")
    if violations:
        print(f"\n⚠ {len(violations)} violation(s) regex résiduelle(s) : relis la lettre.")


if __name__ == "__main__":
    main()