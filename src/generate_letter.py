"""
generate_letter.py
Génère la lettre de motivation en se basant EXCLUSIVEMENT sur ce qui a été
réellement mis sur le CV (cv_data.json, produit par tailor_cv.py) + la
description de l'offre. Garantit une cohérence parfaite CV <-> lettre.

═══════════════════════════════════════════════════════════════════════════
ARCHITECTURE v11 (refonte + patches A-E, 2026-09-11)
═══════════════════════════════════════════════════════════════════════════
Les versions v3-v9 empilaient des règles et des listes noires. Rendement
décroissant : le LLM contournait chaque interdiction par un synonyme non listé.

v10 a introduit une architecture en 3 passes (plan / rédaction / critique).
v11 ajoute les correctifs issus du test réel sur Plas'Tri :

  - Patch A : plan de meilleure qualité, avec règle de PROXIMITÉ THÉMATIQUE
              (choisir l'expérience dont la NATURE TECHNIQUE correspond au
              besoin de l'offre) + validation automatique du plan AVANT
              rédaction.
  - Patch B : interdiction stricte de la 3e personne ("Hénoc AMAVIGAN,
              étudiant en 3e année..."). Le corps de la lettre doit être
              intégralement à la 1ère personne.
  - Patch C : raccourcir_objet retire les titres "Ingénieur/Expert/Senior/Lead"
              qui ne conviennent pas à un profil BUT/alternance, même quand
              l'intitulé officiel de l'offre les contient.
  - Patch D : contrainte de longueur injectée dans le prompt de rédaction
              (répartition par paragraphe) + boucle de régénération jusqu'à
              2 tentatives si la longueur cible n'est pas atteinte.
  - Patch E : complément de la liste noire (solide formation, m'intéresse
              particulièrement, serait une opportunité enrichissante, me
              semblent appropriées, que je possède, J'espère que... me permettra).

Coût d'une lettre : environ 4-6 appels LLM à gpt-4o-mini (~0.005-0.008$).
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
load_dotenv(BASE_DIR / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
DEFAULT_MODEL = "openai/gpt-4o-mini"

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

MOTS_CIBLE_MIN = 590
MOTS_CIBLE_MAX = 650
SEUIL_QUALITE = 8.5


# ═══════════════════════════════════════════════════════════════════════════
# EXEMPLE DE STYLE POSITIF
# ═══════════════════════════════════════════════════════════════════════════
# Un LLM imite mieux un bon exemple qu'il n'obéit à une liste d'interdits.
# Cet exemple respecte TOUTES nos règles : ancrage entreprise, humilité,
# faits concrets, zéro sur-interprétation métier, zéro langue creuse.

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

Règle pratique : quand tu présentes une expérience, dis ce qui a été FAIT (verbe au
passé composé, résultat concret), puis PASSE À LA SUITE. Ne conclus pas par une
projection vague sur son utilité future dans le métier de l'offre.
"""

REGLE_ANCRAGE = """
ANCRAGE ENTREPRISE (contrainte mesurable) :

La PREMIÈRE PHRASE de CHAQUE paragraphe 2, 3 et 4 doit citer explicitement l'entreprise,
le poste, ou un besoin/mot-clé précis tiré de l'offre. Il ne suffit pas que l'entreprise
soit mentionnée "quelque part" dans le paragraphe.

PREMIÈRES PHRASES ACCEPTABLES :
- "Le besoin de [reformulation d'un besoin de l'offre] rejoint la démarche que j'ai
   suivie dans..."
- "Chez [Entreprise], [reformulation d'un enjeu de l'offre] suppose de [action] ; mon
   expérience de [...] a consisté à..."
- "Votre offre mentionne [élément précis] ; dans mon projet de [...], j'ai..."

PREMIÈRES PHRASES INTERDITES :
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

- OBJET : fournis un objet court (max 10-12 mots). Il sera de toute façon nettoyé
  automatiquement. N'utilise JAMAIS les mots "Ingénieur", "Expert", "Senior" ou "Lead",
  MÊME si l'intitulé officiel de l'offre les contient : ce sont des titres de poste,
  pas des titres pour un profil en alternance. Préfère le THÈME du poste :
  "Candidature pour l'alternance - Optimisation d'algorithmes IA", ou
  "Candidature pour l'alternance - Intelligence artificielle appliquée au tri".

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


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION AUTOMATIQUE (regex)
# ═══════════════════════════════════════════════════════════════════════════

FORMULATIONS_INTERDITES = [
    # Famille défi/enjeu vague
    r"\b(défi|défis)\b",
    r"\benjeu(x)? (crucial|cruciale|cruciaux|cruciales|majeur|majeure|majeurs|majeures|"
    r"fondamental|fondamentale|fondamentaux|fondamentales|central|centrale|centraux|centrales)\b",

    # Famille résonance / écho
    r"\brésonne\b",
    r"\btrouve(nt)? un écho\b",
    r"\bme parle\b",
    r"\bcorrespond(ent)? à mes aspirations\b",

    # Famille qualificatifs d'intensité vagues
    r"\b(passionnant|passionnante|passionnants|passionnantes)\b",
    r"\b(enthousiaste|enthousiasmé|enthousiasmée) à l'idée\b",
    r"\bparticulièrement (intéressé|intéressée|motivé|motivée|convaincu|convaincue)\b",
    r"\bm'intéresse particulièrement\b",
    r"\b(serait|serait une|est une) (opportunité|chance) "
    r"(enrichissante?|intéressante?|unique|formidable|exceptionnelle?)\b",
    r"\b(approche|solution|solutions|projet|projets|initiative|démarche) "
    r"(innovant|innovante|innovants|innovantes)\b",

    # Famille affirmations excessives
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

    # Famille hedges conditionnels (formes verbales élargies)
    r"\b(peut|peuvent|pourrait|pourraient|pourra|pourront|sera|serait|seraient) "
    r"(être (mise?|mis) à profit|apporter|faciliter|permettre|contribuer|aider|servir|"
    r"s'avérer|être (utile|utiles|bénéfique|bénéfiques|pertinent|pertinente|pertinents|"
    r"pertinentes|précieux|précieuse|précieuses|transposé|transposée|transposés|transposées|"
    r"transposable|transposables))\b",
    r"\bme permet(tent|tra|tront)? de contribuer\b",
    r"\bnous permet(tent|tra|tront)? de contribuer\b",
    r"\bJ'espère que (cette|cela|ce) (démarche|expérience|projet) me permettra\b",
    r"\bvaleur ajoutée\b",

    # Famille renforcement de capacité
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


def validate_letter(
    objet: str,
    paragraphs: list[str],
    entreprise_nom: str,
) -> list[str]:
    violations: list[str] = []
    full_text = " ".join(paragraphs)
    full_with_objet = full_text + " " + objet

    # Caractères interdits
    if "—" in full_with_objet or "–" in full_with_objet:
        violations.append("Caractères interdits — ou – présents dans la lettre.")

    # Formulations interdites
    for pattern in FORMULATIONS_INTERDITES:
        m = re.search(pattern, full_text, flags=re.IGNORECASE)
        if m:
            violations.append(f"Formulation interdite détectée : « {m.group(0)} ».")

    # Patch B : interdiction de la 3e personne
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

    # Ancrage des paragraphes 2/3/4
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

    # Limite "Je suis / Je serais / Je serai"
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


def raccourcir_objet(objet: str, intitule_offre: str) -> str:
    """Garantit un objet court et propre, quoi qu'ait produit le LLM.
    Patch C : retire aussi les titres Ingénieur/Expert/Senior/Lead, inadaptés
    à un profil BUT/alternance, même quand l'intitulé officiel les contient."""
    o = (objet or "").strip()
    # Retire les préfixes redondants produits par le LLM
    o = re.sub(r"^Candidature pour l'alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"^Offre d'alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"^Alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    # Retire le suffixe (H/F)
    o = re.sub(r"\s*\(H/F\)\s*$", "", o, flags=re.IGNORECASE)
    o = re.sub(r"\s*\(h/f\)\s*$", "", o, flags=re.IGNORECASE)
    # Patch C : retire les mots-senior
    o = re.sub(r"\b(Ingénieur|Ingénieure|Expert|Experte|Senior|Lead)\b\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"\b(IA|AI)\s*$", r"\1", o)  # garde IA si présent
    # Coupe à la première virgule, point-virgule ou parenthèse
    o = re.split(r"\s*[,;]\s*|\s*\(", o)[0].strip()
    # Nettoie les espaces multiples et tirets résiduels
    o = re.sub(r"\s{2,}", " ", o).strip(" -,:;")
    # Tronque à 80 caractères max
    if len(o) > 80:
        o = o[:77].rstrip() + "..."
    # Si vide après nettoyage, on retombe sur l'intitulé tronqué
    if not o:
        fallback = re.sub(r"\s*\(H/F\)\s*$", "", intitule_offre, flags=re.IGNORECASE)
        fallback = re.sub(r"\b(Ingénieur|Ingénieure|Expert|Senior|Lead)\b\s*",
                          "", fallback, flags=re.IGNORECASE)
        fallback = fallback.split(",")[0].strip()
        if len(fallback) > 80:
            fallback = fallback[:77].rstrip() + "..."
        o = fallback or "Alternance en science des données"
    return f"Candidature pour l'alternance - {o}"


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 1 : PLAN (Patch A - proximité thématique + validation)
# ═══════════════════════════════════════════════════════════════════════════

def generate_plan(client: OpenAI, model: str, offer_text: str,
                  experiences_text: str, competences_text: str) -> dict:
    """Demande au LLM de produire un plan JSON structuré AVANT de rédiger.
    Le plan doit respecter une règle de proximité thématique stricte :
    choisir l'expérience du CV dont la NATURE TECHNIQUE (type de données, type
    de traitement) correspond au besoin de l'offre."""
    prompt = f"""Tu prépares un PLAN pour une lettre de motivation. Tu ne rédiges AUCUNE
phrase de la lettre pour l'instant : tu produis uniquement un plan JSON structuré.

PROFIL : Hénoc AMAVIGAN, étudiant en 3e année de BUT Science des Données.
OBJECTIF : lettre de candidature pour une ALTERNANCE.

EXPÉRIENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
{experiences_text}

COMPÉTENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
{competences_text}

OFFRE VISÉE :
{offer_text}

RÈGLE DE PROXIMITÉ THÉMATIQUE (la plus importante pour le choix des expériences) :

Pour chaque paragraphe, tu dois choisir l'expérience du CV dont la NATURE TECHNIQUE
est la plus proche du besoin de l'offre. La nature technique veut dire : quel TYPE
de données, quel TYPE de traitement.

Exemples de proximité correcte :
- Offre parle d'IMAGES (caméras, hyperspectral, vision) -> choisir une expérience
  sur des IMAGES (segmentation, traitement d'image).
- Offre parle de TEXTE (NLP, documents) -> choisir une expérience sur du TEXTE.
- Offre parle de DONNÉES TABULAIRES/statistiques (mesures, séries temporelles)
  -> choisir une expérience sur des données tabulaires.
- Offre parle de BASES DE DONNÉES relationnelles -> choisir l'expérience de
  modélisation BDD.

CONTRE-EXEMPLE À NE PAS FAIRE :
- Offre parle d'imagerie hyperspectrale (IMAGES) ; le plan a associé un projet de
  DÉTECTION DE SPAM (TEXTE). C'est faux. Il faut choisir un projet d'IMAGES.

Si aucune expérience du CV n'a la bonne nature technique, choisis celle dont la
MÉTHODE (rigueur, documentation, structuration) est la plus proche, ET INDIQUE
explicitement dans le plan "methodologique" ou "aucune" pour proximite_thematique.

RÈGLES DU PLAN :
1. Chaque "besoin_offre" doit être une citation courte ou reformulation précise
   d'un élément textuel de l'offre.
2. Chaque "fait_concret_cv" doit être un fait vérifiable (chiffre, méthode, livrable).
3. Le champ "amorce" du paragraphe 2/3/4 DOIT commencer par l'entreprise, le poste
   ou un besoin de l'offre. JAMAIS par "Je", "J'ai", "Mon", "Ma", "Hénoc".
4. Le paragraphe 4 liste des compétences génériques du CV et des qualités humaines,
   SANS les transformer en solutions au problème métier.
5. La lettre finale visera 550 à 650 mots au total. Indique pour chaque paragraphe
   le nombre de phrases prévues (5-6 pour P1, 6-8 pour P2/P3, 5-6 pour P4,
   3-4 pour P5).
6. Les paragraphes 2 et 3 doivent utiliser DEUX expériences DIFFÉRENTES du CV.

Réponds UNIQUEMENT en JSON, format strict :
{{
  "paragraphe_1": {{
    "element_offre_concret": "...",
    "lien_candidat": "...",
    "nb_phrases_prevues": 5
  }},
  "paragraphe_2": {{
    "besoin_offre": "...",
    "experience_cv": "...",
    "nature_technique_experience": "...",
    "fait_concret_cv": "...",
    "proximite_thematique": "directe | methodologique | aucune",
    "amorce": "Phrase complète commençant par l'entreprise/le besoin.",
    "nb_phrases_prevues": 7
  }},
  "paragraphe_3": {{
    "besoin_offre": "...",
    "experience_cv": "...",
    "nature_technique_experience": "...",
    "fait_concret_cv": "...",
    "proximite_thematique": "directe | methodologique | aucune",
    "amorce": "Phrase complète commençant par l'entreprise/le besoin.",
    "nb_phrases_prevues": 7
  }},
  "paragraphe_4": {{
    "besoin_offre": "...",
    "competences_cv": ["...", "..."],
    "qualites_cv": ["...", "..."],
    "amorce": "Phrase complète commençant par l'entreprise/le besoin.",
    "nb_phrases_prevues": 5
  }},
  "paragraphe_5": {{
    "disponibilite": "...",
    "mobilite": "...",
    "ouverture_entretien": "...",
    "nb_phrases_prevues": 3
  }}
}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1400,
    )
    return json.loads(resp.choices[0].message.content)


def validate_plan(plan: dict) -> list[str]:
    """Détecte les plans manifestement mauvais AVANT la rédaction (Patch A)."""
    violations = []

    # Amorce des paragraphes 2/3/4 ne doit pas commencer par un sujet candidat
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

    # Vérifier qu'au moins 2 expériences distinctes sont utilisées pour P2/P3
    exp2 = (plan.get("paragraphe_2", {}).get("experience_cv") or "").strip().lower()
    exp3 = (plan.get("paragraphe_3", {}).get("experience_cv") or "").strip().lower()
    if exp2 and exp3 and exp2 == exp3:
        violations.append(
            "Paragraphes 2 et 3 : la même expérience est utilisée deux fois. "
            "Choisis deux expériences différentes du CV."
        )

    # Vérifier que proximite_thematique est renseigné pour P2 et P3
    for key in ("paragraphe_2", "paragraphe_3"):
        p = plan.get(key, {})
        pt = (p.get("proximite_thematique") or "").strip().lower()
        if pt not in ("directe", "methodologique", "aucune"):
            violations.append(
                f"{key}: proximite_thematique doit valoir 'directe', 'methodologique' "
                f"ou 'aucune' (valeur actuelle : « {pt} »)."
            )

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 2 : RÉDACTION (plan injecté comme contrainte forte)
# ═══════════════════════════════════════════════════════════════════════════

def write_letter(client: OpenAI, model: str, offer_text: str,
                 experiences_text: str, competences_text: str,
                 plan: dict, feedback_longueur: str = "") -> tuple[list[str], str]:
    """Rédige la lettre à partir du plan. Patch D : accepte un feedback
    spécifique sur la longueur pour piloter la régénération."""

    entreprise_nom = ""
    m = re.search(r"Entreprise:\s*(.+)", offer_text)
    if m:
        entreprise_nom = m.group(1).strip()

    feedback_block = (
        f"\n\nCONSIGNE SUPPLÉMENTAIRE (retour de la génération précédente) :\n"
        f"{feedback_longueur}\n"
        if feedback_longueur else ""
    )

    prompt = f"""Tu rédiges une lettre de motivation en français pour Hénoc AMAVIGAN,
étudiant en 3e année de BUT Science des Données, candidat à une ALTERNANCE.

Tu dois suivre STRICTEMENT le plan ci-dessous. Tu ne peux PAS t'en écarter :
chaque paragraphe doit contenir le fait concret et le besoin d'offre indiqués dans
le plan, et commencer par l'amorce indiquée.

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

═══ EXEMPLE DE STYLE À IMITER (registre, densité, sobriété) ═══
Ceci est un exemple POSITIF : chaque phrase respecte toutes les règles ci-dessus.
Imite ce registre, cette sobriété, cette façon de présenter les faits.
---
{STYLE_EXEMPLE}
---

CONSIGNES DE RÉDACTION :

1. Rédige exactement 5 paragraphes. TOTAL IMPÉRATIF : {MOTS_CIBLE_MIN} à {MOTS_CIBLE_MAX}
   mots. Répartition cible :
   - P1 : 90-110 mots (5-6 phrases)
   - P2 : 130-160 mots (6-8 phrases)
   - P3 : 130-160 mots (6-8 phrases)
   - P4 : 100-130 mots (5-6 phrases)
   - P5 : 50-70 mots (3-4 phrases)
   Compte mentalement. Si tu es en-dessous de {MOTS_CIBLE_MIN} à la fin, développe
   chaque fait avec un détail supplémentaire (une précision technique, un résultat
   chiffré, une conséquence concrète) — SANS ajouter de commentaire sur la valeur
   de l'expérience ni de projection sur son utilité future.

2. Aucune formule d'appel ni de politesse finale (je les ajoute moi-même).

3. Pas de "—" ni "–". Uniquement virgules, points, tiret simple "-".

4. Au maximum 2 phrases commençant par "Je suis" / "Je serais" / "Je serai".

5. Tu écris UNIQUEMENT à la première personne ("je", "mon", "ma", "mes", "j'ai").
   Tu n'écris JAMAIS le nom "Hénoc AMAVIGAN" dans le corps de la lettre, ni
   "le candidat", ni toute autre formulation à la 3e personne.

6. Pour l'objet : un titre court (max 10-12 mots), fidèle au THÈME de l'offre,
   sans recopier l'intitulé en entier, sans préfixe redondant. N'utilise JAMAIS
   les mots "Ingénieur", "Expert", "Senior" ou "Lead", MÊME si l'intitulé officiel
   les contient : ce sont des titres de poste, pas des titres pour un profil en
   alternance. Format conseillé : "Candidature pour l'alternance - [thème en 5-8 mots]".{feedback_block}

Réponds UNIQUEMENT en JSON :
{{"objet": "...", "paragraphes": ["...", "...", "...", "...", "..."]}}"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.35,
        max_tokens=2800,
    )
    result = json.loads(resp.choices[0].message.content)
    paragraphes = [remove_forbidden_chars(p) for p in result.get("paragraphes", [])]
    objet = remove_forbidden_chars(result.get("objet", ""))
    return paragraphes, objet


# ═══════════════════════════════════════════════════════════════════════════
# PASSE 3 : CRITIQUE (score de qualité par un LLM-juge sévère)
# ═══════════════════════════════════════════════════════════════════════════

def critique_letter(client: OpenAI, model: str, offer_text: str,
                    paragraphs: list[str]) -> dict:
    prompt = f"""Tu es un recruteur sévère et expérimenté. Tu évalues une lettre de
motivation écrite par un étudiant en BUT Science des Données pour une alternance.

Contexte de l'offre :
{offer_text[:1500]}

Lettre à évaluer :
{json.dumps(paragraphs, ensure_ascii=False, indent=2)}

Note la lettre sur 10 selon ces 5 critères, chacun noté sur 10 puis moyenné :
1. Ancrage entreprise (parle-t-elle de l'entreprise/du besoin, pas seulement du candidat ?)
2. Humilité (le candidat se positionne-t-il comme un junior qui demande une chance, ou
   comme un expert qui a déjà tout prouvé ?)
3. Absence de sur-interprétation (n'attribue-t-il pas au candidat des expériences
   métier qu'il n'a pas eues ?)
4. Densité factuelle (faits concrets : chiffres, méthodes, livrables, ou bien
   généralités creuses ?)
5. Absence de langue creuse (pas de "défi", "résonne", "pourrait être pertinent",
   "me permettra de contribuer", "enjeu crucial", etc. ?)

Critères de notation :
- 9-10 : lettre excellente, envoyable telle quelle sans retouche.
- 8-8.9 : très bonne, quelques retouches mineures.
- 7-7.9 : correcte mais un défaut net gêne la lecture.
- 6-6.9 : passable, plusieurs défauts.
- <6 : à réécrire.

Réponds UNIQUEMENT en JSON :
{{
  "score": 8.5,
  "scores_detail": {{
    "ancrage_entreprise": 9,
    "humilite": 8,
    "pas_sur_interpretation": 9,
    "densite_factuelle": 8,
    "pas_langue_creuse": 8
  }},
  "phrases_problematiques": [
    "citation exacte d'une phrase ou bout de phrase qui pose problème",
    "..."
  ],
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
phrases identifiés comme problématiques (langue creuse, sur-interprétation,
ton trop affirmatif). Réécris UNIQUEMENT ces passages, dans leur contexte, sans
modifier le reste du texte ni sa longueur globale.

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
    parser.add_argument("--verbose", action="store_true",
                        help="Affiche le plan et le rapport du critique.")
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

    # ─── PASSE 1 : PLAN + validation (Patch A) ───────────────────────────
    print("\n[Passe 1/3] Génération du plan...")
    plan = generate_plan(client, args.model, offer_text,
                         experiences_text, competences_text)
    plan_violations = validate_plan(plan)
    tentatives_plan = 0
    while plan_violations and tentatives_plan < 2:
        tentatives_plan += 1
        print(f"Plan invalide ({len(plan_violations)} problèmes), régénération {tentatives_plan}/2...")
        for v in plan_violations:
            print(f"  - {v}")
        plan = generate_plan(client, args.model, offer_text,
                             experiences_text, competences_text)
        plan_violations = validate_plan(plan)
    if args.verbose:
        print("Plan retenu :")
        print(json.dumps(plan, ensure_ascii=False, indent=2)[:1800])

    # ─── PASSE 2 : RÉDACTION ─────────────────────────────────────────────
    print("\n[Passe 2/3] Rédaction de la lettre à partir du plan...")
    paragraphs, objet = write_letter(client, args.model, offer_text,
                                     experiences_text, competences_text, plan)

    if not paragraphs:
        raise RuntimeError("Le LLM n'a renvoyé aucun paragraphe.")

    nb_mots = word_count(paragraphs)
    violations = validate_letter(objet, paragraphs, entreprise)
    print(f"Longueur : {nb_mots} mots. Violations regex : {len(violations)}")
    for v in violations:
        print(f"  - {v}")

    # ─── BOUCLE DE RÉGÉNÉRATION si violations regex ──────────────────────
    tentatives = 0
    while violations and tentatives < 2:
        tentatives += 1
        print(f"\nRégénération complète {tentatives}/2 (violations regex persistantes)...")
        paragraphs, objet = write_letter(client, args.model, offer_text,
                                         experiences_text, competences_text, plan)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)
        print(f"Longueur : {nb_mots} mots. Violations regex : {len(violations)}")

    # ─── BOUCLE DE RÉGÉNÉRATION SI LONGUEUR HORS CIBLE (Patch D) ─────────
    tentatives_longueur = 0
    while (nb_mots < MOTS_CIBLE_MIN - 30 or nb_mots > MOTS_CIBLE_MAX + 80) and tentatives_longueur < 2:
        tentatives_longueur += 1
        if nb_mots < MOTS_CIBLE_MIN - 30:
            feedback = (
                f"Ta réponse précédente ne faisait que {nb_mots} mots, alors que la cible "
                f"est {MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX}. Développe BEAUCOUP plus chaque "
                f"paragraphe en ajoutant des précisions techniques concrètes (méthode, "
                f"outil, chiffre, livrable) tirées du CV. N'ajoute AUCUN commentaire sur "
                f"la valeur de l'expérience ni de projection sur son utilité future. "
                f"Répartition cible : P1 ~100 mots, P2 ~150, P3 ~150, P4 ~120, P5 ~60."
            )
        else:
            feedback = (
                f"Ta réponse faisait {nb_mots} mots, trop long par rapport à la cible "
                f"{MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX}. Condense en supprimant les tournures "
                f"et adjectifs, en gardant tous les faits concrets. Répartition cible : "
                f"P1 ~100 mots, P2 ~150, P3 ~150, P4 ~120, P5 ~60."
            )
        print(f"\nLongueur hors cible ({nb_mots} mots), régénération {tentatives_longueur}/2...")
        paragraphs, objet = write_letter(
            client, args.model, offer_text, experiences_text, competences_text,
            plan, feedback_longueur=feedback,
        )
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)
        print(f"Nouvelle longueur : {nb_mots} mots. Violations : {len(violations)}")

    # ─── PASSE 3 : CRITIQUE + SCORE ──────────────────────────────────────
    print("\n[Passe 3/3] Évaluation par un LLM-juge sévère...")
    critique = critique_letter(client, args.model, offer_text, paragraphs)
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

    # ─── PASSE 3bis : RÉÉCRITURE CIBLÉE si nécessaire ───────────────────
    if (score < SEUIL_QUALITE or violations) and (phrases_pb or violations):
        print(f"\nRéécriture ciblée sur les phrases fautives...")
        problemes_a_corriger = list(phrases_pb) + violations
        paragraphs = rewrite_targeted(client, args.model, paragraphs,
                                      problemes_a_corriger)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise)

        critique2 = critique_letter(client, args.model, offer_text, paragraphs)
        score2 = critique2.get("score", 0)
        print(f"Score après réécriture : {score2}/10")
        if score2 > score:
            score = score2
            critique = critique2

    # ─── Nettoyage final de l'objet (Patch C) ────────────────────────────
    objet_avant = objet
    objet = raccourcir_objet(objet, intitule_offre)
    if objet != objet_avant:
        print(f"\nObjet nettoyé automatiquement :")
        print(f"  Avant : {objet_avant}")
        print(f"  Après : {objet}")

    # ─── RENDU FINAL ─────────────────────────────────────────────────────
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
    print(f"Score qualité : {score}/10 (seuil visé : {SEUIL_QUALITE})")
    print(f"Longueur : {nb_mots} mots (cible {MOTS_CIBLE_MIN}-{MOTS_CIBLE_MAX})")
    print(f"Violations regex résiduelles : {len(violations)}")
    print(f"PDF : {pdf_path}  ({statut})")
    print(f"Word (secours) : {docx_path}")

    if score < SEUIL_QUALITE:
        print(f"\n⚠ Score inférieur à {SEUIL_QUALITE}. Recommandations du critique :")
        for r in critique.get("recommandations", []):
            print(f"    - {r}")
        print("Relis attentivement la lettre avant envoi.")
    else:
        print(f"\n✓ Lettre au-dessus du seuil de qualité.")
    if violations:
        print(f"\n⚠ {len(violations)} violation(s) regex résiduelle(s) : relis la lettre.")


if __name__ == "__main__":
    main()