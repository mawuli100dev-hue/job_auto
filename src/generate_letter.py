"""
generate_letter.py
Génère la lettre de motivation en se basant EXCLUSIVEMENT sur ce qui a été
réellement mis sur le CV (cv_data.json, produit par tailor_cv.py) + la
description de l'offre. Garantit une cohérence parfaite CV <-> lettre.

═══════════════════════════════════════════════════════════════════════════
ARCHITECTURE v14 (v13 + Passe 4 lissage narratif, 2026-09-19)
═══════════════════════════════════════════════════════════════════════════
v11 : patches A-E (plan de qualité, interdiction 3e personne, raccourcissement
d'objet, contrainte de longueur, complément liste noire).
v12 : Fix 1 (hedge conditionnel non détecté au pluriel), Fix 2 (paragraphe 1
non couvert par les règles d'ancrage/posture), Fix 3 (voix de l'entreprise
dans le paragraphe 1).
v13 : Fix 4 (amorces répétitives des paragraphes 2/3/4), Fix 5 (backslash
invalide dans une expression de f-string, incompatible Python < 3.12).

v14 ajoute une PASSE 4 : LISSAGE NARRATIF, en post-traitement de la lettre
déjà complète, plutôt que d'ajouter encore une règle dans le prompt de
rédaction (risque de confusion documenté depuis les versions v3-v9). Le
contenu produit par la passe 2 est déjà bon ; le problème constaté est
l'enchaînement entre paragraphes 2, 3 et 4, qui repartent chacun de zéro sur
un nouveau besoin de l'offre sans jamais rebondir sur ce qui vient d'être
dit. La passe 4 voit la lettre complète et retravaille UNIQUEMENT les
transitions (débuts de P3, P4, P5), sans toucher aux faits ni à la longueur.

Coût d'une lettre : environ 5-7 appels LLM à gpt-4o-mini (~0.006-0.010$).
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

TYPES_AMORCE = ("nom_entreprise", "reformulation_besoin", "connecteur_logique")

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
- La lettre est intégralement à la 1ère personne. Le nom "Hénoc AMAVIGAN" (masculin)
  n'apparaît JAMAIS dans le corps (il est déjà dans l'en-tête, on n'a pas à le répéter).
- On ne dit jamais "je suis motivé par" ou "je suis passionné par" (creux). On décrit
  ce qui a été fait et les résultats obtenus.
- On ne dit jamais "Actuellement étudiant en" (creux). On utilise une formulation non générique.
- La lettre s'écrit du point de vue du candidat qui s'adresse à l'entreprise, JAMAIS du
  point de vue de l'entreprise qui s'adresserait au candidat. On ne dit jamais
  "[Entreprise] vous propose..." ou "vous offre...", ni "nos politiques/projets/équipes"
  en parlant à la place de l'entreprise : c'est le candidat qui écrit "je", pas
  l'entreprise qui écrit "nous"/"vous".
"""

REGLE_SUR_INTERPRETATION = """
SUR-INTERPRÉTATION (règle non négociable) :

Ne jamais dire que le candidat A FAIT X simplement parce qu'il possède une compétence Y
qui POURRAIT servir à faire X. Une compétence reste une compétence, elle ne devient pas
une expérience vécue dans le domaine métier précis de l'offre.

Exemples :
- CV: pipeline Python d'analyse climatique | Offre: optimisation d'algorithmes IA
  BON : "La rigueur méthodologique développée dans ce projet est une démarche que je
  souhaite transposer à un contexte différent."
  MAUVAIS : "Cette démarche est directement applicable à l'optimisation de vos
  algorithmes."

- CV: dashboard Streamlit | Offre: digitalisation des processus
  BON : "Cette expérience m'a permis de développer des compétences en conception
  d'outils de restitution."
  MAUVAIS : "Cette expérience m'a préparé à digitaliser vos processus."

- CV: SQL + base de données relationnelle | Offre: base de données fournisseurs
  BON : "Ces compétences constituent une base que je souhaite mettre à profit pour
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

RÈGLE DE VARIÉTÉ DES AMORCES (Fix 4 - la plus souvent violée) :
Un SEUL paragraphe parmi 2, 3 et 4 a le droit de commencer littéralement par le nom de
l'entreprise. Les deux autres DOIVENT utiliser une autre stratégie d'amorce :

- Type "nom_entreprise" (max 1 fois sur toute la lettre) :
  "[Entreprise] a besoin de concevoir des outils de pilotage ; dans mon projet de..."

- Type "reformulation_besoin" (reformule le besoin SANS répéter le nom) :
  "Le pilotage de la performance et le suivi d'indicateurs supposent une donnée fiable
  et à jour ; mon expérience de..."

- Type "connecteur_logique" (relie au paragraphe précédent ou à un enjeu, sans répéter
  le nom ni "je/j'ai" en tout début) :
  "Cette exigence de fiabilité rejoint la démarche que j'ai suivie dans..."
  "Ce même besoin de suivi rigoureux se retrouve dans mon expérience de..."

PREMIÈRES PHRASES INTERDITES (quel que soit le type choisi) :
- "Dans le cadre de ma recherche..." (part du candidat)
- "Je dispose de compétences en..." (part du candidat)
- "J'ai eu l'opportunité de..." (part du candidat)
- "Mon expérience m'a permis de..." (part du candidat)

Le paragraphe 1 doit lui aussi citer l'entreprise, le poste ou un besoin précis de
l'offre dès sa première phrase, mais TOUJOURS depuis le point de vue du candidat qui
s'adresse à l'entreprise (jamais l'inverse). Sa DERNIÈRE phrase ne doit JAMAIS être une
formule générique du type "J'espère que cette expérience/démarche sera enrichissante"
ou "J'espère que cela me permettra de..." : conclure plutôt par un fait ou une intention
précise et non interchangeable d'une offre à l'autre.

Sur l'ensemble de la lettre : au maximum 2 phrases peuvent commencer par
"Je suis" / "Je serais" / "Je serai".
"""

REGLE_LANGUE_CREUSE = """
LANGUE CREUSE À BANNIR (familles entières, pas seulement les exemples) :

Famille "défi/enjeu vague" :
à bannir : "un défi", "un défi passionnant", "un enjeu crucial/majeur/fondamental/clé",
"un enjeu central". À la place : décris le problème technique concret (quel type de
données, quel type de traitement).

Famille "résonance abstraite" :
à bannir : "résonne avec", "trouve un écho", "me parle", "correspond à mes aspirations".
À la place : explique EN QUOI concrètement, avec un fait.

Famille "qualificatifs d'intensité vagues" :
à bannir : "passionnant", "enthousiaste à l'idée de", "particulièrement intéressé",
"particulièrement motivé", "approche innovante", "solution innovante", "m'intéresse
particulièrement", "opportunité enrichissante", "représente une opportunité",
"constitue une chance/opportunité". À la place : zéro qualificatif d'intensité, laisse
le fait concret parler.

Famille "affirmations excessives" :
à bannir : "crucial", "essentiel", "indispensable", "parfaitement", "solide
compréhension", "solide formation", "connaissances solides", "compétences solides",
"je suis reconnu pour", "s'inscrit parfaitement", "me semble approprié", "me semblent
appropriées", "que je possède", "ce qui me semble important".

Famille "hedges conditionnels" (le pire tic constaté) :
à bannir : "pourrait/pourrait/pourra/pourront être mis(e)(s) à profit", "pourrait
apporter une valeur ajoutée", "pourrait faciliter", "pourrait s'avérer pertinent",
"pourraient être transposées", "peut permettre de", "peut contribuer à", "mes
compétences me permettront de contribuer efficacement", "J'espère que cette démarche
me permettra de mobiliser", "j'espère que cette expérience sera enrichissante".
Maximum UNE seule phrase de ce type dans TOUTE la lettre.

Famille "voix de l'entreprise" :
à bannir : toute phrase où l'entreprise semble s'adresser au lecteur ("[Entreprise]
vous propose...", "vous offre...", "nous vous proposons..."), ou toute reprise quasi
verbatim de l'accroche marketing de l'offre. La lettre est écrite PAR le candidat,
jamais à la place de l'entreprise.

Famille "amorces répétitives" (Fix 4) :
à bannir : répéter le nom complet de l'entreprise en tout début de plus d'UN
paragraphe parmi 2, 3, 4. Si tu as déjà ouvert un paragraphe par le nom de
l'entreprise, les autres doivent obligatoirement utiliser une reformulation du besoin
ou un connecteur logique (voir REGLE_ANCRAGE).

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

- N'écris JAMAIS du point de vue de l'entreprise ("vous propose", "vous offre",
  "nous vous proposons") : c'est toujours le candidat qui parle à l'entreprise.

- Ne répète JAMAIS le nom complet de l'entreprise en tout début de plus d'UN
  paragraphe parmi 2, 3, 4 (Fix 4) : varie explicitement le type d'amorce.
"""

FORMULATIONS_INTERDITES = [
    r"\b(défi|défis)\b",
    r"\benjeu(x)? (crucial|cruciale|cruciaux|cruciales|majeur|majeure|majeurs|majeures|"
    r"fondamental|fondamentale|fondamentaux|fondamentales|central|centrale|centraux|centrales|"
    r"clé|clés)\b",

    r"\brésonne\b",
    r"\btrouve(nt)? un écho\b",
    r"\bme parle\b",
    r"\bcorrespond(ent)? à mes aspirations\b",

    r"\b(passionnant|passionnante|passionnants|passionnantes)\b",
    r"\b(enthousiaste|enthousiasmé|enthousiasmée) à l'idée\b",
    r"\bparticulièrement (intéressé|intéressée|motivé|motivée|convaincu|convaincue)\b",
    r"\bm'intéresse particulièrement\b",
    r"\b(serait|serait une|est une|représente|constitue|constitue une) "
    r"(opportunité|chance|une opportunité|une chance) "
    r"(enrichissante?|intéressante?|unique|formidable|exceptionnelle?)?\b",
    r"\b(approche|solution|solutions|projet|projets|initiative|démarche) "
    r"(innovant|innovante|innovants|innovantes)\b",

    r"\b(crucial|cruciale|cruciaux|cruciales|essentiel|essentielle|essentiels|essentielles|"
    r"indispensable|indispensables)\b",
    r"\bparfaitement\b",
    r"\bsolide (compréhension|maîtrise|connaissance|connaissances|base|bases|"
    r"formation|expérience|parcours|bagage)\b",
    r"\bconnaissances solides\b",
    r"\bcompétences (solides|techniques solides)\b",
    r"\bje suis reconnu\b",
    r"\b(me|nous) positionne(nt)? favorablement\b",
    r"\bs'inscrit parfaitement\b",
    r"\bs'inscrirait parfaitement\b",
    r"\bme semble(nt)? (approprié|appropriée|appropriés|appropriées|adapté|adaptée|adaptés|adaptées)\b",
    r"\bque je possède\b",
    r"\bce qui me semble important\b",

    r"\b(peut|peuvent|pourrait|pourraient|pourra|pourront|sera|serait|seraient) "
    r"(être\s+mis(e|es)?\s+à\s+profit|apporter|faciliter|permettre|contribuer|aider|servir|"
    r"s'avérer|être\s+(utile|utiles|bénéfique|bénéfiques|pertinent|pertinente|pertinents|"
    r"pertinentes|précieux|précieuse|précieuses|transposé|transposée|transposés|transposées|"
    r"transposable|transposables))\b",
    r"\bme permet(tent|tra|tront)? de contribuer\b",
    r"\bnous permet(tent|tra|tront)? de contribuer\b",
    r"\bj'espère que (cette|cela|ce) (démarche|expérience|projet) me permettra\b",
    r"\bj'espère que (cette|cela|ce) (expérience|démarche|opportunité) "
    r"(sera|serait|soit) (enrichissant|enrichissante|bénéfique)\b",
    r"\bvaleur ajoutée\b",

    r"\brenforce ma capacité\b",
    r"\brenforce(nt)? (ma|notre) capacité\b",

    r"\bvous propose(z)?\b",
    r"\bnous vous proposons\b",
    r"\bvous offre(z)?\b",
    r"\bnos\s+(politiques publiques|projets|équipes|missions|activités)\b",
]

DEBUT_CANDIDAT = re.compile(
    r"^(Je\b|J'ai\b|Dans le cadre de ma\b|Dans le cadre de mon\b|Mon\b|Ma\b|Mes\b|"
    r"Au cours de mon\b|Lors de mon\b|Durant mon\b)",
    flags=re.IGNORECASE,
)

DEBUT_JE_SUIS = re.compile(
    r"(?:^|(?<=[.!?]\s))(Je suis|Je serais|Je serai)\b",
    flags=re.IGNORECASE,
)


def split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def first_sentence(paragraph):
    parts = split_sentences(paragraph)
    return parts[0] if parts else ""


def last_sentence(paragraph):
    parts = split_sentences(paragraph)
    return parts[-1] if parts else ""


def ngram_overlap_ratio(sentence, reference_text, n=5):
    def ngrams(text, n):
        words = re.findall(r"\w+", text.lower())
        if len(words) < n:
            return set()
        return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}

    s_grams = ngrams(sentence, n)
    if not s_grams:
        return 0.0
    r_grams = ngrams(reference_text, n)
    return len(s_grams & r_grams) / len(s_grams)


def count_literal_entreprise_openings(paragraphs, entreprise_nom):
    count = 0
    idxs = []
    if not entreprise_nom:
        return count, idxs
    for idx in (1, 2, 3):
        if idx >= len(paragraphs):
            continue
        fs = first_sentence(paragraphs[idx])
        if fs.lower().startswith(entreprise_nom.lower()):
            count += 1
            idxs.append(idx + 1)
    return count, idxs


def validate_letter(objet, paragraphs, entreprise_nom, offer_text=""):
    violations = []
    full_text = " ".join(paragraphs)
    full_with_objet = full_text + " " + objet

    if "—" in full_with_objet or "–" in full_with_objet:
        violations.append("Caractères interdits — ou – présents dans la lettre.")

    for pattern in FORMULATIONS_INTERDITES:
        m = re.search(pattern, full_text, flags=re.IGNORECASE)
        if m:
            violations.append("Formulation interdite détectée : « " + m.group(0) + " ».")

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
                "Paragraphe " + str(idx + 1) + " : 1ère phrase centrée candidat "
                "(« " + fs[:70] + "... »). Doit partir de l'entreprise/du besoin."
            )
            continue
        cite = False
        if entreprise_nom and entreprise_nom.lower() in fs.lower():
            cite = True
        elif re.search(
            r"\b(votre offre|votre poste|votre besoin|vos besoins|l'offre|le poste|"
            r"chez vous|votre entreprise|votre structure|votre équipe|ce poste|"
            r"cette alternance|votre projet|vos projets)\b",
            fs, re.IGNORECASE,
        ):
            cite = True
        if not cite:
            violations.append(
                "Paragraphe " + str(idx + 1) + " : 1ère phrase ne cite ni l'entreprise, ni le "
                "poste, ni un besoin de l'offre (« " + fs[:70] + "... »)."
            )

    nb_lit, idxs_lit = count_literal_entreprise_openings(paragraphs, entreprise_nom)
    if nb_lit > 1:
        violations.append(
            "Paragraphes " + str(idxs_lit) + " commencent tous littéralement par le nom de "
            "l'entreprise (« " + str(entreprise_nom) + " »). Un seul paragraphe doit utiliser "
            "cette amorce ; les autres doivent reformuler le besoin ou utiliser un "
            "connecteur logique (voir REGLE_ANCRAGE)."
        )

    if paragraphs:
        p1_last = last_sentence(paragraphs[0])
        if re.match(r"^\s*j'espère que", p1_last, flags=re.IGNORECASE):
            violations.append(
                "Paragraphe 1 : dernière phrase générique en « j'espère que... » "
                "(« " + p1_last[:70] + "... »). Remplacer par un fait concret ou une "
                "intention précise."
            )

    if paragraphs:
        p1_first = first_sentence(paragraphs[0])
        if re.search(
            r"\bvous propose(z)?\b|\bnous vous proposons\b|\bvous offre(z)?\b",
            p1_first, flags=re.IGNORECASE,
        ):
            violations.append(
                "Paragraphe 1 : 1ère phrase adopte la voix de l'entreprise au lieu "
                "du candidat (« " + p1_first[:70] + "... »)."
            )
        if offer_text:
            overlap = ngram_overlap_ratio(p1_first, offer_text, n=5)
            if overlap > 0.5:
                violations.append(
                    "Paragraphe 1 : 1ère phrase reprend l'offre de façon quasi "
                    "verbatim (recouvrement 5-grammes = " + format(overlap, ".0%") + "). "
                    "Reformuler du point de vue candidat."
                )

    nb_je_suis = len(DEBUT_JE_SUIS.findall(full_text))
    if nb_je_suis > 2:
        violations.append(
            "Trop de phrases commencent par 'Je suis/Je serais/Je serai' "
            "(" + str(nb_je_suis) + ", maximum 2)."
        )

    return list(dict.fromkeys(violations))


def find_cv_data_path(offer_id, base_dir):
    candidatures_dir = base_dir / "data" / "candidatures"
    matches = list(candidatures_dir.glob("*/*_" + offer_id + "/cv_data.json"))
    if not matches:
        raise FileNotFoundError(
            "Aucun cv_data.json trouvé pour l'offre " + offer_id + ". "
            "Lance d'abord tailor_cv.py sur cette offre."
        )
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def clean_lieu(lieu_brut):
    if not lieu_brut:
        return ""
    nettoye = re.sub(r"^\s*\d{1,3}\s*-\s*", "", lieu_brut).strip()
    return nettoye or lieu_brut.strip()


def remove_forbidden_chars(text):
    if not text:
        return text
    text = text.replace("—", " - ").replace("–", " - ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+-\s+", " - ", text)
    return text


def extract_cv_content(cv_data):
    experiences_text = "\n\n".join(
        "- " + e["titre"] + " (" + e.get("structure", "") + ", " + e.get("periode", "") + ") :\n  "
        + " ".join(b.replace("**", "") for b in e["bullets"])
        for e in cv_data.get("experiences_sur_cv", [])
    )
    competences_text = "\n".join(
        "- " + cat + " : " + ", ".join(items)
        for cat, items in cv_data.get("competences_sur_cv", {}).items()
    )
    return experiences_text, competences_text


def build_offer_text_from_saved(offer_saved, description_complete):
    return (
        "Intitulé: " + offer_saved.get("intitule", "") + "\n"
        + "Entreprise: " + offer_saved.get("entreprise", "") + "\n"
        + "Lieu: " + offer_saved.get("lieu", "") + "\n"
        + "Description: " + description_complete[:2500]
    )


def word_count(paragraphs):
    return sum(len(p.split()) for p in paragraphs)


def raccourcir_objet(objet, intitule_offre):
    o = (objet or "").strip()
    o = re.sub(r"^Candidature pour l'alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"^Offre d'alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"^Alternance\s*[-:]\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"\s*\(H/F\)\s*$", "", o, flags=re.IGNORECASE)
    o = re.sub(r"\b(Ingénieur|Ingénieure|Expert|Experte|Senior|Lead)\b\s*", "", o, flags=re.IGNORECASE)
    o = re.sub(r"\b(IA|AI)\s*$", r"\1", o)
    o = re.split(r"\s*[,;]\s*|\s*\(", o)[0].strip()
    o = re.sub(r"\s{2,}", " ", o).strip(" -,:;")
    if len(o) > 80:
        o = o[:77].rstrip() + "..."
    if not o:
        fallback = re.sub(r"\s*\(H/F\)\s*$", "", intitule_offre, flags=re.IGNORECASE)
        fallback = re.sub(
            r"\b(Ingénieur|Ingénieure|Expert|Senior|Lead)\b\s*", "", fallback, flags=re.IGNORECASE
        )
        fallback = fallback.split(",")[0].strip()
        if len(fallback) > 80:
            fallback = fallback[:77].rstrip() + "..."
        o = fallback or "Alternance en science des données"
    return "Candidature pour l'alternance - " + o


def generate_plan(client, model, offer_text, experiences_text, competences_text):
    prompt = """Tu prépares un PLAN pour une lettre de motivation. Tu ne rédiges AUCUNE
phrase de la lettre pour l'instant : tu produis uniquement un plan JSON structuré.

PROFIL : Hénoc AMAVIGAN, étudiant en 3e année de BUT Science des Données.
OBJECTIF : lettre de candidature pour une ALTERNANCE.

EXPÉRIENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
""" + experiences_text + """

COMPÉTENCES PRÉSENTES SUR LE CV (utilise UNIQUEMENT celles-ci) :
""" + competences_text + """

OFFRE VISÉE :
""" + offer_text + """

RÈGLE DE PROXIMITÉ THÉMATIQUE (la plus importante pour le choix des expériences) :

Pour chaque paragraphe, tu dois choisir l'expérience du CV dont la NATURE TECHNIQUE
est la plus proche du besoin de l'offre. La nature technique veut dire : quel TYPE
de données, quel TYPE de traitement.

Si aucune expérience du CV n'a la bonne nature technique, choisis celle dont la
MÉTHODE (rigueur, documentation, structuration) est la plus proche, ET INDIQUE
explicitement dans le plan "methodologique" ou "aucune" pour proximite_thematique.

RÈGLE DE VARIÉTÉ DES AMORCES (Fix 4, contrainte mesurable) :
Pour chaque paragraphe 2, 3 et 4, choisis un "type_amorce" parmi :
- "nom_entreprise" : l'amorce cite le nom de l'entreprise en toutes lettres au début.
- "reformulation_besoin" : l'amorce reformule un besoin de l'offre SANS répéter le
  nom de l'entreprise.
- "connecteur_logique" : l'amorce utilise un connecteur ("Cette exigence...", "Ce
  même besoin...") sans répéter le nom ni commencer par "je/j'ai".
CONTRAINTE STRICTE : au maximum UN SEUL des paragraphes 2, 3, 4 peut avoir
"type_amorce": "nom_entreprise". Les deux autres doivent être "reformulation_besoin"
ou "connecteur_logique".

RÈGLES DU PLAN :
1. Chaque "besoin_offre" doit être une citation courte ou reformulation précise
   d'un élément textuel de l'offre.
2. Chaque "fait_concret_cv" doit être un fait vérifiable (chiffre, méthode, livrable).
3. Le champ "amorce" du paragraphe 2/3/4 DOIT être cohérent avec son "type_amorce" et
   ne JAMAIS commencer par "Je", "J'ai", "Mon", "Ma", "Hénoc".
4. Le paragraphe 4 liste des compétences génériques du CV et des qualités humaines,
   SANS les transformer en solutions au problème métier.
5. La lettre finale visera 550 à 650 mots au total. Indique pour chaque paragraphe
   le nombre de phrases prévues (5-6 pour P1, 6-8 pour P2/P3, 5-6 pour P4,
   3-4 pour P5).
6. Les paragraphes 2 et 3 doivent utiliser DEUX expériences DIFFÉRENTES du CV.

Réponds UNIQUEMENT en JSON, format strict :
{
  "paragraphe_1": {"element_offre_concret": "...", "lien_candidat": "...", "nb_phrases_prevues": 5},
  "paragraphe_2": {"besoin_offre": "...", "experience_cv": "...", "nature_technique_experience": "...",
                     "fait_concret_cv": "...", "proximite_thematique": "directe | methodologique | aucune",
                     "type_amorce": "nom_entreprise | reformulation_besoin | connecteur_logique",
                     "amorce": "Phrase complète respectant le type_amorce choisi.", "nb_phrases_prevues": 7},
  "paragraphe_3": {"besoin_offre": "...", "experience_cv": "...", "nature_technique_experience": "...",
                     "fait_concret_cv": "...", "proximite_thematique": "directe | methodologique | aucune",
                     "type_amorce": "nom_entreprise | reformulation_besoin | connecteur_logique",
                     "amorce": "Phrase complète respectant le type_amorce choisi.", "nb_phrases_prevues": 7},
  "paragraphe_4": {"besoin_offre": "...", "competences_cv": ["...", "..."], "qualites_cv": ["...", "..."],
                     "type_amorce": "nom_entreprise | reformulation_besoin | connecteur_logique",
                     "amorce": "Phrase complète respectant le type_amorce choisi.", "nb_phrases_prevues": 5},
  "paragraphe_5": {"disponibilite": "...", "mobilite": "...", "ouverture_entretien": "...", "nb_phrases_prevues": 3}
}"""
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1500,
    )
    return json.loads(resp.choices[0].message.content)


def validate_plan(plan):
    violations = []
    nb_nom_entreprise = 0

    for key in ("paragraphe_2", "paragraphe_3", "paragraphe_4"):
        p = plan.get(key, {})
        amorce = (p.get("amorce") or "").strip()
        if not amorce:
            violations.append(key + ": amorce manquante.")
            continue
        if re.match(r"^(Je\b|J'ai\b|Mon\b|Ma\b|Mes\b|Hénoc\b)", amorce, re.IGNORECASE):
            violations.append(
                key + ": l'amorce commence par un sujet candidat : « " + amorce[:60] + "... »"
            )
        type_amorce = (p.get("type_amorce") or "").strip().lower()
        if type_amorce not in TYPES_AMORCE:
            violations.append(
                key + ": type_amorce doit valoir 'nom_entreprise', 'reformulation_besoin' "
                "ou 'connecteur_logique' (valeur actuelle : « " + type_amorce + " »)."
            )
        elif type_amorce == "nom_entreprise":
            nb_nom_entreprise += 1

    if nb_nom_entreprise > 1:
        violations.append(
            str(nb_nom_entreprise) + " paragraphes utilisent le type_amorce 'nom_entreprise' "
            "(maximum autorisé : 1). Varie avec 'reformulation_besoin' ou "
            "'connecteur_logique' pour les autres."
        )

    exp2 = (plan.get("paragraphe_2", {}).get("experience_cv") or "").strip().lower()
    exp3 = (plan.get("paragraphe_3", {}).get("experience_cv") or "").strip().lower()
    if exp2 and exp3 and exp2 == exp3:
        violations.append(
            "Paragraphes 2 et 3 : la même expérience est utilisée deux fois. "
            "Choisis deux expériences différentes du CV."
        )

    for key in ("paragraphe_2", "paragraphe_3"):
        p = plan.get(key, {})
        pt = (p.get("proximite_thematique") or "").strip().lower()
        if pt not in ("directe", "methodologique", "aucune"):
            violations.append(
                key + ": proximite_thematique doit valoir 'directe', 'methodologique' "
                "ou 'aucune' (valeur actuelle : « " + pt + " »)."
            )
    return violations


def write_letter(client, model, offer_text, experiences_text, competences_text,
                  plan, feedback_longueur=""):
    entreprise_nom = ""
    m = re.search(r"Entreprise:\s*(.+)", offer_text)
    if m:
        entreprise_nom = m.group(1).strip()

    feedback_block = (
        "\n\nCONSIGNE SUPPLÉMENTAIRE (retour de la génération précédente) :\n"
        + feedback_longueur + "\n"
        if feedback_longueur else ""
    )

    entreprise_label = entreprise_nom if entreprise_nom else "l'entreprise"

    exemples_amorce = ""
    if entreprise_nom:
        exemples_amorce = f"""
EXEMPLES CONCRETS DE VARIÉTÉ D'AMORCE POUR "{entreprise_label}" :
- type "nom_entreprise" (max 1 fois sur toute la lettre) :
  "{entreprise_label} a besoin de concevoir des outils de pilotage ;
  dans mon projet de..."
- type "reformulation_besoin" (ne répète PAS le nom) :
  "Le pilotage de la performance et le suivi d'indicateurs supposent une donnée fiable
  et à jour ; mon expérience de..."
- type "connecteur_logique" (ne répète PAS le nom, ne commence pas par "je/j'ai") :
  "Cette exigence de fiabilité rejoint la démarche que j'ai suivie dans..."
"""

    prompt = ("""Tu rédiges une lettre de motivation en français pour Hénoc AMAVIGAN,
étudiant en 3e année de BUT Science des Données, candidat à une ALTERNANCE.

Tu dois suivre STRICTEMENT le plan ci-dessous, y compris le "type_amorce" prévu pour
chaque paragraphe 2/3/4 : tu ne peux PAS t'en écarter.

═══ PLAN À SUIVRE ═══
""" + json.dumps(plan, ensure_ascii=False, indent=2) + """
═════════════════════
""" + exemples_amorce + """
EXPÉRIENCES SUR LE CV (n'invente rien d'autre) :
""" + experiences_text + """

COMPÉTENCES SUR LE CV (n'invente rien d'autre) :
""" + competences_text + """

OFFRE VISÉE :
""" + offer_text + """

═══ RÈGLE DE POSTURE (la plus importante) ═══
""" + REGLE_POSTURE + """

═══ RÈGLE DE SUR-INTERPRÉTATION ═══
""" + REGLE_SUR_INTERPRETATION + """

═══ RÈGLE D'ANCRAGE ENTREPRISE (variété des amorces incluse) ═══
""" + REGLE_ANCRAGE + """

═══ LANGUE CREUSE À BANNIR ═══
""" + REGLE_LANGUE_CREUSE + """

═══ INTERDICTIONS SPÉCIFIQUES ═══
""" + REGLE_INTERDICTIONS_SPECIFIQUES + """

═══ EXEMPLE DE STYLE À IMITER (registre, densité, sobriété) ═══
Ceci est un exemple POSITIF : chaque phrase respecte toutes les règles ci-dessus.
Imite ce registre, cette sobriété, cette façon de présenter les faits.
---
""" + STYLE_EXEMPLE + """
---

CONSIGNES DE RÉDACTION :

1. Rédige exactement 5 paragraphes. TOTAL IMPÉRATIF : """ + str(MOTS_CIBLE_MIN) + """ à """ + str(MOTS_CIBLE_MAX) + """
   mots. Répartition cible :
   - P1 : 90-110 mots (5-6 phrases)
   - P2 : 130-160 mots (6-8 phrases)
   - P3 : 130-160 mots (6-8 phrases)
   - P4 : 100-130 mots (5-6 phrases)
   - P5 : 50-70 mots (3-4 phrases)
   Compte mentalement. Si tu es en-dessous de """ + str(MOTS_CIBLE_MIN) + """ à la fin, développe
   chaque fait avec un détail supplémentaire (une précision technique, un résultat
   chiffré, une conséquence concrète) — SANS ajouter de commentaire sur la valeur
   de l'expérience ni de projection sur son utilité future.

2. Aucune formule d'appel ni de politesse finale (je les ajoute moi-même).

3. Pas de "—" ni "–". Uniquement virgules, points, tiret simple "-".

4. Au maximum 2 phrases commençant par "Je suis" / "Je serais" / "Je serai".

5. Tu écris UNIQUEMENT à la première personne ("je", "mon", "ma", "mes", "j'ai").
   Tu n'écris JAMAIS le nom "Hénoc AMAVIGAN" dans le corps de la lettre, ni
   "le candidat", ni toute autre formulation à la 3e personne. Tu n'écris JAMAIS
   du point de vue de l'entreprise ("vous propose", "vous offre").

6. Un SEUL paragraphe parmi 2, 3, 4 peut commencer littéralement par le nom de
   l'entreprise. Vérifie-le toi-même avant de répondre : relis les premiers mots de
   chaque paragraphe 2, 3 et 4 et assure-toi qu'ils ne répètent pas tous le même nom.

7. Pour l'objet : un titre court (max 10-12 mots), fidèle au THÈME de l'offre,
   sans recopier l'intitulé en entier, sans préfixe redondant. N'utilise JAMAIS
   les mots "Ingénieur", "Expert", "Senior" ou "Lead", MÊME si l'intitulé officiel
   les contient : ce sont des titres de poste, pas des titres pour un profil en
   alternance. Format conseillé : "Candidature pour l'alternance - [thème en 5-8 mots]".""" + feedback_block + """

Réponds UNIQUEMENT en JSON :
{"objet": "...", "paragraphes": ["...", "...", "...", "...", "..."]}""")

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


def critique_letter(client, model, offer_text, paragraphs):
    prompt = ("""Tu es un recruteur sévère et expérimenté. Tu évalues une lettre de
motivation écrite par un étudiant en BUT Science des Données pour une alternance.

Contexte de l'offre :
""" + offer_text[:1500] + """

Lettre à évaluer :
""" + json.dumps(paragraphs, ensure_ascii=False, indent=2) + """

Note la lettre sur 10 selon ces 6 critères, chacun noté sur 10 puis moyenné :
1. Ancrage entreprise (parle-t-elle de l'entreprise/du besoin, pas seulement du candidat ?)
2. Humilité (le candidat se positionne-t-il comme un junior qui demande une chance, ou
   comme un expert qui a déjà tout prouvé ?)
3. Absence de sur-interprétation (n'attribue-t-il pas au candidat des expériences
   métier qu'il n'a pas eues ?)
4. Densité factuelle (faits concrets : chiffres, méthodes, livrables, ou bien
   généralités creuses ?)
5. Absence de langue creuse (pas de "défi", "résonne", "pourrait être pertinent",
   "me permettra de contribuer", "enjeu crucial", "vous propose", etc. ?)
6. Fluidité et variété des amorces (les paragraphes 2, 3, 4 commencent-ils tous par
   la même formule mécanique "[Entreprise] + verbe", ou la lecture est-elle fluide et
   variée ?)

Critères de notation :
- 9-10 : lettre excellente, envoyable telle quelle sans retouche.
- 8-8.9 : très bonne, quelques retouches mineures.
- 7-7.9 : correcte mais un défaut net gêne la lecture.
- 6-6.9 : passable, plusieurs défauts.
- <6 : à réécrire.

Réponds UNIQUEMENT en JSON :
{"score": 8.5, "scores_detail": {"ancrage_entreprise": 9, "humilite": 8,
"pas_sur_interpretation": 9, "densite_factuelle": 8, "pas_langue_creuse": 8,
"fluidite_amorces": 8},
"phrases_problematiques": ["citation exacte d'une phrase ou bout de phrase qui pose problème", "..."],
"points_forts": ["...", "..."], "recommandations": ["...", "..."]}""")

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1000,
    )
    return json.loads(resp.choices[0].message.content)


def rewrite_targeted(client, model, paragraphs, problemes):
    if not problemes:
        return paragraphs

    prompt = ("""Voici une lettre de motivation et une liste de phrases ou bouts de
phrases identifiés comme problématiques (langue creuse, sur-interprétation,
ton trop affirmatif, voix de l'entreprise au lieu du candidat, amorces répétitives).
Réécris UNIQUEMENT ces passages, dans leur contexte, sans modifier le reste du texte
ni sa longueur globale. Si le problème concerne une amorce répétée ("[Entreprise] +
verbe" dans plusieurs paragraphes), reformule TOUTES les amorces sauf UNE pour qu'elles
utilisent un connecteur logique ou une reformulation du besoin, sans répéter le nom de
l'entreprise.

PASSAGES À RÉÉCRIRE :
""" + json.dumps(problemes, ensure_ascii=False, indent=2) + """

PARAGRAPHES ACTUELS :
""" + json.dumps(paragraphs, ensure_ascii=False, indent=2) + """

RAPPEL DE LA POSTURE À RESPECTER :
""" + REGLE_POSTURE + """

RAPPEL DE LA RÈGLE D'ANCRAGE (variété des amorces) :
""" + REGLE_ANCRAGE + """

Réponds UNIQUEMENT en JSON, avec les 5 paragraphes complets (même ceux non modifiés) :
{"paragraphes": ["...", "...", "...", "...", "..."]}""")

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


def smooth_narrative_flow(client, model, paragraphs):
    """Passe 4 (post-traitement) : retravaille UNIQUEMENT les transitions entre
    paragraphes pour rétablir une continuité narrative, sans toucher aux faits,
    aux chiffres, ni à la longueur. Le LLM voit la lettre complète déjà
    rédigée et peut donc relier chaque paragraphe à ce qui vient d'être dit,
    ce qu'aucune contrainte écrite à l'avance dans le prompt de rédaction ne
    peut garantir aussi bien. Idée proposée par l'utilisateur (2026-09-19) :
    isoler la fluidité dans une passe dédiée plutôt que d'ajouter encore une
    règle dans le prompt de la passe 2, déjà chargé de contraintes."""
    prompt = ("""Voici une lettre de motivation déjà complète, en 5 paragraphes. Le contenu
est bon mais la lecture est saccadée : chaque paragraphe 2, 3 et 4 repart de zéro sur un
nouveau besoin de l'offre, sans jamais rebondir sur ce qui vient d'être dit dans le
paragraphe précédent. On dirait 3 mini-lettres juxtaposées plutôt qu'un texte qui avance.

LETTRE ACTUELLE :
""" + json.dumps(paragraphs, ensure_ascii=False, indent=2) + """

TA TÂCHE : retravaille UNIQUEMENT les DÉBUTS des paragraphes 3, 4 et 5 (jamais le
paragraphe 1, jamais le contenu factuel des paragraphes) pour qu'ils rebondissent
explicitement sur ce qui vient d'être dit dans le paragraphe précédent, avant ou en
plus de citer l'entreprise ou un besoin de l'offre.

CONTRAINTES STRICTES :
1. Ne change AUCUN fait, chiffre, méthode, outil ou résultat mentionné. Tu ne fais que
   retravailler les phrases de transition et de liaison.
2. Ne change PAS la longueur totale de plus de 5%.
3. N'utilise jamais "vous propose", "vous offre", ni de langue creuse ("enjeu crucial",
   "opportunité enrichissante", "résonne avec", "pourrait être mis à profit").
4. Le lien vers le paragraphe précédent doit se faire par une formulation comme
   "Cette même rigueur...", "Au-delà de cette expérience...", "Ce même besoin de...",
   "Dans la continuité de...", PAS par une simple reformulation encore une fois du
   besoin de l'offre pris isolément.
5. Garde exactement 5 paragraphes, à la première personne, sans jamais nommer
   "Hénoc AMAVIGAN" dans le corps.

Réponds UNIQUEMENT en JSON avec les 5 paragraphes complets (même ceux non modifiés) :
{"paragraphes": ["...", "...", "...", "...", "..."]}""")

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=2800,
    )
    result = json.loads(resp.choices[0].message.content)
    new_paras = result.get("paragraphes", paragraphs)
    return [remove_forbidden_chars(p) for p in new_paras]


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
    print("CV trouvé : " + str(cv_data_path))

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

    print("\n[Passe 1/4] Génération du plan...")
    plan = generate_plan(client, args.model, offer_text, experiences_text, competences_text)
    plan_violations = validate_plan(plan)
    tentatives_plan = 0
    while plan_violations and tentatives_plan < 2:
        tentatives_plan += 1
        print("Plan invalide (" + str(len(plan_violations)) + " problèmes), régénération "
              + str(tentatives_plan) + "/2...")
        for v in plan_violations:
            print("  - " + v)
        plan = generate_plan(client, args.model, offer_text, experiences_text, competences_text)
        plan_violations = validate_plan(plan)
    if args.verbose:
        print("Plan retenu :")
        print(json.dumps(plan, ensure_ascii=False, indent=2)[:1800])

    print("\n[Passe 2/4] Rédaction de la lettre à partir du plan...")
    paragraphs, objet = write_letter(client, args.model, offer_text,
                                      experiences_text, competences_text, plan)
    if not paragraphs:
        raise RuntimeError("Le LLM n'a renvoyé aucun paragraphe.")

    nb_mots = word_count(paragraphs)
    violations = validate_letter(objet, paragraphs, entreprise, offer_text)
    print("Longueur : " + str(nb_mots) + " mots. Violations regex : " + str(len(violations)))
    for v in violations:
        print("  - " + v)

    tentatives = 0
    while violations and tentatives < 2:
        tentatives += 1
        print("\nRégénération complète " + str(tentatives) + "/2 (violations regex persistantes)...")
        paragraphs, objet = write_letter(client, args.model, offer_text,
                                          experiences_text, competences_text, plan)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise, offer_text)
        print("Longueur : " + str(nb_mots) + " mots. Violations regex : " + str(len(violations)))

    tentatives_longueur = 0
    while (nb_mots < MOTS_CIBLE_MIN - 30 or nb_mots > MOTS_CIBLE_MAX + 80) and tentatives_longueur < 2:
        tentatives_longueur += 1
        if nb_mots < MOTS_CIBLE_MIN - 30:
            feedback = (
                "Ta réponse précédente ne faisait que " + str(nb_mots) + " mots, alors que la cible "
                "est " + str(MOTS_CIBLE_MIN) + "-" + str(MOTS_CIBLE_MAX) + ". Développe BEAUCOUP plus chaque "
                "paragraphe en ajoutant des précisions techniques concrètes (méthode, "
                "outil, chiffre, livrable) tirées du CV. N'ajoute AUCUN commentaire sur "
                "la valeur de l'expérience ni de projection sur son utilité future. "
                "Répartition cible : P1 ~100 mots, P2 ~150, P3 ~150, P4 ~120, P5 ~60."
            )
        else:
            feedback = (
                "Ta réponse faisait " + str(nb_mots) + " mots, trop long par rapport à la cible "
                + str(MOTS_CIBLE_MIN) + "-" + str(MOTS_CIBLE_MAX) + ". Condense en supprimant les tournures "
                "et adjectifs, en gardant tous les faits concrets. Répartition cible : "
                "P1 ~100 mots, P2 ~150, P3 ~150, P4 ~120, P5 ~60."
            )
        print("\nLongueur hors cible (" + str(nb_mots) + " mots), régénération "
              + str(tentatives_longueur) + "/2...")
        paragraphs, objet = write_letter(
            client, args.model, offer_text, experiences_text, competences_text,
            plan, feedback_longueur=feedback,
        )
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise, offer_text)
        print("Nouvelle longueur : " + str(nb_mots) + " mots. Violations : " + str(len(violations)))

    print("\n[Passe 3/4] Évaluation par un LLM-juge sévère...")
    critique = critique_letter(client, args.model, offer_text, paragraphs)
    score = critique.get("score", 0)
    detail = critique.get("scores_detail", {})
    phrases_pb = critique.get("phrases_problematiques", [])

    print("\n  Score global : " + str(score) + "/10 (seuil visé : " + str(SEUIL_QUALITE) + ")")
    for k, v in detail.items():
        print("    " + k + " : " + str(v) + "/10")
    if critique.get("points_forts"):
        print("  Points forts :")
        for p in critique["points_forts"]:
            print("    + " + p)
    if phrases_pb:
        print("  Phrases problématiques :")
        for p in phrases_pb:
            print("    ! " + p)

    if (score < SEUIL_QUALITE or violations) and (phrases_pb or violations):
        print("\nRéécriture ciblée sur les phrases fautives...")
        problemes_a_corriger = list(phrases_pb) + violations
        paragraphs = rewrite_targeted(client, args.model, paragraphs, problemes_a_corriger)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise, offer_text)

        critique2 = critique_letter(client, args.model, offer_text, paragraphs)
        score2 = critique2.get("score", 0)
        print("Score après réécriture : " + str(score2) + "/10")
        if score2 > score:
            score = score2
            critique = critique2

    # ─── PASSE 4 : LISSAGE DE LA CONTINUITÉ NARRATIVE (v14) ──────────────
    # Retravaille uniquement les transitions entre paragraphes (jamais le
    # contenu factuel), pour éviter que chaque paragraphe 2/3/4 reparte de
    # zéro sur un nouveau besoin de l'offre sans jamais rebondir sur ce qui
    # vient d'être dit. Voir smooth_narrative_flow() pour le détail.
    print("\n[Passe 4/4] Lissage de la continuité narrative...")
    paragraphs = smooth_narrative_flow(client, args.model, paragraphs)
    nb_mots = word_count(paragraphs)
    violations = validate_letter(objet, paragraphs, entreprise, offer_text)
    print("Longueur après lissage : " + str(nb_mots) + " mots. Violations : " + str(len(violations)))
    if violations:
        print("Réécriture ciblée après lissage (violations réintroduites)...")
        paragraphs = rewrite_targeted(client, args.model, paragraphs, violations)
        nb_mots = word_count(paragraphs)
        violations = validate_letter(objet, paragraphs, entreprise, offer_text)
        print("Longueur : " + str(nb_mots) + " mots. Violations résiduelles : " + str(len(violations)))

    objet_avant = objet
    objet = raccourcir_objet(objet, intitule_offre)
    if objet != objet_avant:
        print("\nObjet nettoyé automatiquement :")
        print("  Avant : " + objet_avant)
        print("  Après : " + objet)

    today = datetime.now()
    ville_date = "Carcassonne, le " + str(today.day) + " " + MOIS_FR[today.month - 1] + " " + str(today.year)
    lieu_entreprise = remove_forbidden_chars(clean_lieu(offer_saved.get("lieu", "")))

    pdf_path = dossier / "LM_Henoc_AMAVIGAN.pdf"
    html_path = dossier / "LM_Henoc_AMAVIGAN.html"
    docx_path = dossier / "LM_Henoc_AMAVIGAN.docx"

    fit_info = fit_on_one_page(entreprise, lieu_entreprise, ville_date, objet,
                                paragraphs, pdf_path, html_path)
    build_docx(entreprise, lieu_entreprise, ville_date, objet, paragraphs, docx_path)

    statut = "OK, tient sur 1 page" if fit_info["fitted"] else "NE TIENT PAS sur 1 page"
    print("\n═══════ RÉSULTAT ═══════")
    print("Score qualité : " + str(score) + "/10 (seuil visé : " + str(SEUIL_QUALITE) + ")")
    print("Longueur : " + str(nb_mots) + " mots (cible " + str(MOTS_CIBLE_MIN) + "-" + str(MOTS_CIBLE_MAX) + ")")
    print("Violations regex résiduelles : " + str(len(violations)))
    print("PDF : " + str(pdf_path) + " (" + statut + ")")
    print("Word (secours) : " + str(docx_path))

    if score < SEUIL_QUALITE:
        print("\n⚠ Score inférieur à " + str(SEUIL_QUALITE) + ". Recommandations du critique :")
        for r in critique.get("recommandations", []):
            print("  - " + r)
        print("Relis attentivement la lettre avant envoi.")
    else:
        print("\n✓ Lettre au-dessus du seuil de qualité.")
    if violations:
        print("\n⚠ " + str(len(violations)) + " violation(s) regex résiduelle(s) : relis la lettre.")


if __name__ == "__main__":
    main()