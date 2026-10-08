# job_automation/src/job_automation/letter/letter_prompt_builder.py

import json
import re

from config.letter_examples import (
    LETTER_EXAMPLES,
    LETTER_LOGIC,
)
from common.text_normalizer import (
    contains_whole_expression,
    normalize_text,
)
from config.known_tools import (
    KNOWN_TOOLS_WITHOUT_PROJECT,
)
from config.letter_profile import (
    LETTER_PROFILE,
)
from domain.models import (
    LetterContent,
    LetterContext,
)


SYSTEM_PROMPT = """
Tu écris les lettres de motivation d'un étudiant en science des données, à sa place et dans SON style. Il t'a donné des lettres qu'il a écrites lui-même : ta lettre doit avoir la même logique, le même ton simple et sincère, la même longueur, au point qu'on ne puisse pas la distinguer des siennes. Tu sais aussi, comme un recruteur, qu'on ne retient d'une lettre que les faits concrets reliés à son besoin. Tu n'inventes jamais rien : chaque fait sur le candidat figure dans les données fournies.
""".strip()


# Formules creuses typiques des lettres générées par IA.
# Elles sont aussi vérifiées par LetterValidator.
BANNED_EXPRESSIONS = (
    "c'est avec un grand intérêt",
    "c'est avec enthousiasme",
    "vivement intéressé",
    "passionné",
    "leader",
    "renommée",
    "en constante évolution",
    "en perpétuelle évolution",
    "valeurs qui me correspondent",
    "je suis convaincu que mon profil",
    "atout majeur",
    "véritable atout",
    "n'hésitez pas",
    "dynamique et motivé",
    "relever de nouveaux défis",
    "cela démontre ma capacité",
    "apporter de la valeur",
    "je suis désireux",
    "votre engagement",
    "m'a permis",
    "grâce à cette expérience",
    "serais ravi",
    "des données similaires",
)


def build_style_examples() -> str:
    blocks = []

    for index, example in enumerate(LETTER_EXAMPLES, start=1):
        body = "\n\n".join(example.paragraphs)

        blocks.append(
            f"<lettre_du_candidat_{index}>\n"
            f"Contexte : {example.label}\n"
            f"Objet : {example.subject}\n\n"
            f"{body}\n"
            f"</lettre_du_candidat_{index}>"
        )

    return "\n\n".join(blocks)


STYLE_EXAMPLES = build_style_examples()


# Partie fixe du prompt, identique pour toutes les candidatures :
# placée dans le message système pour être mise en cache par
# le fournisseur (voir JsonLlmClient).
STYLE_SECTION = f"""
LETTRES ÉCRITES PAR LE CANDIDAT LUI-MÊME (modèles de style)
Imite leur logique, leur ton, leur simplicité et leur longueur. Ne recopie aucune de leurs phrases et ne reprends aucun fait propre à ces entreprises (navire, AIS, panache, Mayotte, Transitions Pro, Underscore_...). Les faits sur le candidat viennent UNIQUEMENT des blocs <candidat>, <experiences_du_cv> et <competences_du_cv> du message : si un projet cité dans ces modèles n'y figure pas, n'en parle pas.

{STYLE_EXAMPLES}

LOGIQUE COMMUNE DE CES LETTRES
{LETTER_LOGIC}
""".strip()


def known_tools_requested_by_offer(
    target,
) -> list[str]:
    """
    Outils de KNOWN_TOOLS_WITHOUT_PROJECT cités par l'offre : seuls
    ceux-là sont donnés au LLM, pour qu'il n'en parle que s'ils
    comptent pour cette candidature.
    """

    # La ponctuation est retirée pour que « Python, SAS »
    # corresponde à la variante « python sas ».
    offer_text = re.sub(
        r"[^\w\s]",
        " ",
        normalize_text(target.searchable_text()),
    )

    return [
        name
        for name, variants in KNOWN_TOOLS_WITHOUT_PROJECT
        if any(
            contains_whole_expression(
                expression=variant,
                normalized_text=offer_text,
            )
            for variant in variants
        )
    ]


def clean_experience_for_prompt(
    experience: dict,
) -> dict:
    """
    Ne garde que ce qui est utile à la rédaction : les tags,
    identifiants et URL n'apportent rien et poussent le modèle
    à recopier des mots-clés.
    """

    bullets = []

    for bullet in experience.get("bullets", []):
        text = str(bullet).replace("**", "")
        text = re.sub(r"\s*:?\s*https?://\S+", "", text)
        bullets.append(text.strip())

    return {
        "titre": experience.get("titre", ""),
        "contexte": experience.get("sous_titre", ""),
        "structure": experience.get("structure", ""),
        "periode": experience.get("periode", ""),
        "realisations": bullets,
    }


class LetterPromptBuilder:
    @property
    def system_prompt(self) -> str:
        return f"{SYSTEM_PROMPT}\n\n{STYLE_SECTION}"

    def _build_data_blocks(
        self,
        context: LetterContext,
    ) -> str:
        target = context.target

        experiences_json = json.dumps(
            [
                clean_experience_for_prompt(experience)
                for experience in context.selected_experiences
            ],
            ensure_ascii=False,
            indent=2,
        )

        skills_json = json.dumps(
            context.selected_skills,
            ensure_ascii=False,
            indent=2,
        )

        candidate_lines = [
            f"Nom : {LETTER_PROFILE.full_name}",
            f"Formation : {LETTER_PROFILE.formation}",
            f"Parcours antérieur : {LETTER_PROFILE.previous_background}",
            f"Poste visé (sous-titre du CV) : {context.cv_subtitle}",
        ]

        if LETTER_PROFILE.referee:
            candidate_lines.append(
                "Personne pouvant témoigner de son travail "
                "(à citer seulement si cela renforce la lettre, "
                "sans jamais prétendre qu'elle a recommandé cette "
                f"entreprise) : {LETTER_PROFILE.referee}"
            )

        if context.availability:
            candidate_lines.append(
                "Disponibilité (à reprendre telle quelle, une seule "
                "fois, sans expliquer le calendrier de l'école ni "
                "aucune contrainte de dates, et sans ajouter de mois "
                f"ou de durée) : {context.availability}"
            )

        if (
            target.contract_type == "alternance"
            and context.availability_frame
        ):
            candidate_lines.append(
                "Cadre de l'alternance (à mentionner en une phrase "
                "simple, sans détailler le calendrier) : "
                f"{context.availability_frame}"
            )

        if (
            target.contract_type == "alternance"
            and LETTER_PROFILE.alternance_rhythm
        ):
            candidate_lines.append(
                "Rythme d'alternance : "
                f"{LETTER_PROFILE.alternance_rhythm}"
            )

        candidate_block = "\n".join(candidate_lines)

        known_tools = known_tools_requested_by_offer(target)

        known_tools_block = ""

        if known_tools:
            known_tools_block = (
                "\n\n<outils_connus_sans_projet>\n"
                + ", ".join(known_tools)
                + "\n</outils_connus_sans_projet>"
            )

        return f"""
<candidat>
{candidate_block}
</candidat>

<cible>
{context.company_context}
</cible>

<experiences_du_cv>
{experiences_json}
</experiences_du_cv>

<competences_du_cv>
{skills_json}
</competences_du_cv>{known_tools_block}
""".strip()

    def _build_rules(
        self,
        context: LetterContext,
    ) -> str:
        contract_label = {
            "alternance": "une alternance",
            "stage": "un stage",
        }[context.target.contract_type]

        if context.target.source_type == "spontaneous":
            subject_rule = (
                f"« Candidature spontanée pour {contract_label} "
                "en <domaine précis lié à l'entreprise> »."
            )
        else:
            subject_rule = (
                f"« Candidature pour {contract_label}, "
                "<intitulé reformulé et court>, <ville> »."
            )

        banned_list = ", ".join(
            f"« {expression} »"
            for expression in BANNED_EXPRESSIONS
        )

        return f"""
RÈGLES DE FOND (impératives)
- N'invente aucun fait : expérience, outil, chiffre, durée, diplôme, valeur ou actualité de l'entreprise, nom de produit. Tout doit venir des blocs ci-dessus.
- Durée et dates du contrat : n'en indique aucune (« d'un an », « de 12 mois », date de fin) si elle ne figure pas mot pour mot dans l'offre ou dans le bloc <candidat>. Dis simplement « cette alternance » ou « ce stage ».
- N'utilise que des outils présents dans <experiences_du_cv> ou <competences_du_cv>. Si l'offre demande un outil absent du CV, n'affirme pas le maîtriser.
- Exception : les outils du bloc <outils_connus_sans_projet>, s'il existe. Le candidat en connaît le fonctionnement et les concepts, sans les avoir encore utilisés dans un projet complet. Cite-les tous ensemble, en une seule phrase honnête et positive, de préférence dans le paragraphe sur l'écart, par exemple : « Je connais le fonctionnement de PySpark et de Databricks et les concepts qui les sous-tendent, sans les avoir encore utilisés dans un projet complet. » N'écris jamais qu'il ne les connaît pas, et n'invente aucun projet, résultat ou durée d'utilisation avec ces outils.
- Reste à la hauteur d'un étudiant : pas de « expert », « maîtrise parfaite », « solide expérience professionnelle ». Les projets académiques ou personnels sont présentés comme tels, pas comme des emplois.
- Ne recopie pas des phrases entières de l'offre ; reformule.
- Ne mentionne ni lien, ni URL, ni identifiant technique.
- Les ponts entre un projet et l'offre portent sur une COMPÉTENCE transférable (croiser des sources, nettoyer, construire un tableau de bord, suivre des indicateurs), jamais sur une ressemblance des données ou du secteur qui n'existe pas. Interdit : « j'ai travaillé sur des données similaires » quand le domaine est différent. Si le lien est indirect, dis-le simplement (« la méthode est la même », « je pourrais appliquer cette démarche à... »).
- Choisis en priorité les preuves qui utilisent les outils exigés par l'offre : chaque outil exigé que le CV contient doit apparaître au moins une fois dans la lettre, de préférence dans le récit d'un projet plutôt que dans une liste.
- Langues : n'en parle que si la cible demande explicitement une langue, et seulement de cette langue. Reprends alors exactement le niveau indiqué sur le CV pour cette langue (par exemple « anglais de niveau B2 »), jamais « je maîtrise l'anglais », et n'attribue jamais à une langue la certification d'une autre (le Goethe Zertifikat concerne l'allemand).
- Ne fais pas de paragraphe qui liste les outils : ceux exigés par l'offre doivent apparaître dans le récit des projets.

STYLE : CELUI DU CANDIDAT
- Écris comme dans les lettres du candidat : « j'ai construit », « j'ai conçu », « je sais qu'il me reste à apprendre », pas « j'ai eu l'opportunité de » ni « cette expérience m'a permis de développer ».
- Des phrases simples, 35 mots au maximum, avec des verbes d'action. Pas de grands mots, pas de superlatifs.
- Chaque affirmation sur une compétence s'appuie sur un fait (outil, volume, chiffre, résultat) tiré du CV. Un adjectif sur soi-même (« rigoureux », « autonome ») n'est permis que s'il est suivi du fait qui le montre.
- Au plus deux phrases consécutives commençant par « Je ».
- Pas de phrase qui commente le candidat (« cela démontre ma capacité à... ») : les faits suffisent.
- Nom de l'entreprise : écris-le comme un humain, pas en majuscules. Si la description utilise un nom court ou un sigle (exemple : « ACC »), utilise-le.
- Noms de marques, produits ou clients : écris-les normalement, même si l'offre les met en majuscules (« Peugeot », pas « PEUGEOT »). Garde les sigles tels quels (DS, MES).
- Pas de noms techniques internes qu'un recruteur extérieur ne connaît pas (noms de modèles, de jeux de données, de stations de mesure, de bases, comme ALADIN, CAMS, MOOSE, Cap Béar) : décris plutôt ce qu'ils sont (« un modèle régional, une réanalyse atmosphérique et des observations de terrain »). Garde les noms connus du recruteur : outils (Python, Power BI, YOLOv8), laboratoires (CEFREM) et noms de projets.
- Aucune de ces formules : {banned_list}.

FORME
- Entre 360 et 450 mots pour l'ensemble des paragraphes, en 5 à 7 paragraphes, comme les modèles. Ne dépasse pas 450 mots : la lettre doit tenir sur une page.
- Pas de Markdown, pas de liste à puces, pas de tiret cadratin (—) ni demi-cadratin (–).
- Objet : {subject_rule} Sans H/F.
- Formule d'appel : exactement « {context.recipient.greeting} ».
- Formule de politesse : « Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées. »
- Signature : exactement « {LETTER_PROFILE.full_name} ».
""".strip()

    def _build_json_format(
        self,
        context: LetterContext,
    ) -> str:
        return f"""
Réponds uniquement avec ce JSON :

{{
  "analyse": {{
    "besoins_cles": ["besoin 1", "besoin 2"],
    "preuves": ["besoin 1 : fait précis du CV, point commun", "besoin 2 : fait précis du CV, point commun"],
    "exigences_couvertes": ["exigence 1", "exigence 2"],
    "accroche": "le fait concret de l'entreprise ou de l'offre utilisé pour la première phrase",
    "ecart": "ce que la cible demande et que le CV ne montre pas, ou aucun"
  }},
  "subject": "...",
  "greeting": "{context.recipient.greeting}",
  "paragraphs": ["paragraphe 1", "paragraphe 2", "paragraphe 3", "paragraphe 4", "paragraphe 5", "paragraphe 6"],
  "closing": "...",
  "signature": "{LETTER_PROFILE.full_name}"
}}
""".strip()

    def build_generation_prompt(
        self,
        context: LetterContext,
    ) -> str:
        contract_label = {
            "alternance": "une alternance",
            "stage": "un stage",
        }[context.target.contract_type]

        return f"""
Rédige la lettre de motivation de ce candidat, qui postule à {contract_label}.

{self._build_data_blocks(context)}

ÉTAPE 1 : ANALYSE (dans le champ "analyse" du JSON)
- besoins_cles : les 2 ou 3 besoins concrets et SPÉCIFIQUES à cette cible. Un besoin valable pour n'importe quelle offre data (« analyser des données », « développer des outils ») est trop vague : précise sur quelles données, pour qui et dans quel but, avec les termes de l'offre (exemple : « analyser les données des machines et du MES pour suivre les lots de production et les défaillances »).
- preuves : pour chaque besoin, l'expérience ou la compétence du CV qui y répond le mieux, le fait précis à citer (outil, méthode, chiffre) ET le point commun avec le besoin (exemple : « croiser 3 sources hétérogènes, comme machines + mesures + MES »). Si rien ne correspond, écris "aucune preuve" : la lettre n'en parlera pas.
- exigences_couvertes : les exigences explicites de l'offre (outils, langues, niveau d'études) que le CV possède.
- accroche : un fait concret et spécifique de la description (un produit, un projet, un chiffre, une mission) qui servira à ouvrir la lettre.
- ecart : ce que la cible demande et que le CV ne montre pas. Pense d'abord au DOMAINE MÉTIER : si aucun projet du CV ne porte sur le secteur de l'entreprise (industrie, production, finance, santé, radiofréquence, milieu marin...) ou sur ses systèmes propres (MES, ERP, capteurs...), c'est un écart, même si tous les outils sont couverts. Puis aux outils et au niveau d'études. Écris "aucun" seulement si le CV couvre vraiment le domaine et les outils. Ne déclare jamais comme manquant un outil présent dans le CV. Les outils de <outils_connus_sans_projet> ne sont pas un manque mais une connaissance sans projet complet : présente-les comme tels.

ÉTAPE 2 : RÉDACTION, en 5 à 7 paragraphes, avec la logique des lettres du candidat
1. Accroche : ouvre sur le fait choisi dans "accroche" (une image concrète du problème que traite l'entreprise, ou ce qui convainc dans l'offre), cité précisément. Relie-le au candidat, puis dis qui il est (formation) et ce qu'il demande (le contrat). Ne commence pas par « Je », ni par « Actuellement étudiant ».
2. et 3. Un projet par paragraphe, en commençant par celui qui utilise le plus d'outils exigés par l'offre. Ce que le candidat a fait, avec quels outils, avec les chiffres du CV. Termine par un pont explicite vers une mission nommée dans l'offre.
4. Si "ecart" n'est pas "aucun" : un paragraphe honnête qui nomme l'écart simplement et dit comment le candidat le comblera, en s'appuyant sur ce qu'il sait déjà faire. Sinon, une autre preuve ou les compétences exigées par l'offre que le CV possède (outils, langue avec son niveau exact).
5. Ce qui rend le candidat fiable au quotidien, appuyé sur un fait du CV ou du parcours antérieur, puis sa disponibilité et sa mobilité (prêt à s'installer dans la ville de l'offre si elle est connue).
6. Une phrase simple qui propose un échange, comme dans les modèles.

{self._build_rules(context)}

{self._build_json_format(context)}
""".strip()

    def build_review_prompt(
        self,
        context: LetterContext,
        content: LetterContent,
    ) -> str:
        """
        Relecture par un « recruteur » : améliore les phrases faibles
        d'un premier jet sans toucher aux faits.
        """

        return f"""
Voici le premier jet d'une lettre de motivation et les données dont elle est tirée. Relis-la comme le recruteur qui recevra cette candidature, puis améliore-la.

{self._build_data_blocks(context)}

<premier_jet>
{json.dumps(self._content_as_dict(content), ensure_ascii=False, indent=2)}
</premier_jet>

TA RELECTURE
1. La lettre ressemble-t-elle aux lettres du candidat (logique, ton, longueur) ? Sinon, rapproche-la de ces modèles.
2. La première phrase donne-t-elle envie de lire la suite, avec un fait propre à cette entreprise ? Sinon, réécris-la.
3. Repère les phrases vagues, génériques ou qu'on pourrait écrire pour n'importe quelle entreprise, et remplace-les par un fait du CV relié à une mission de l'offre, ou supprime-les.
4. Simplifie les phrases longues ou ampoulées : une idée par phrase, des verbes d'action simples.
5. Vérifie chaque fait contre les données : supprime tout ce qui n'y figure pas.
6. Garde ce qui est déjà bon : ne réécris pas pour réécrire.

{self._build_rules(context)}

{self._build_json_format(context)}
""".strip()

    def build_correction_prompt(
        self,
        context: LetterContext,
        content: LetterContent,
        errors: list[str],
    ) -> str:
        # Les données et les règles restent dans le prompt : sans
        # elles, le modèle invente. Les étapes d'analyse et de
        # rédaction, inutiles pour corriger, sont omises pour
        # réduire le coût.
        return f"""
Voici une lettre de motivation rédigée pour ce candidat, qui contient des erreurs à corriger.

{self._build_data_blocks(context)}

<version_actuelle>
{json.dumps(self._content_as_dict(content), ensure_ascii=False, indent=2)}
</version_actuelle>

<erreurs_a_corriger>
{json.dumps(errors, ensure_ascii=False, indent=2)}
</erreurs_a_corriger>

Corrige uniquement ces erreurs, en modifiant le moins possible le reste de la lettre, et en respectant les règles ci-dessous.

{self._build_rules(context)}

{self._build_json_format(context)}
""".strip()

    @staticmethod
    def _content_as_dict(
        content: LetterContent,
    ) -> dict:
        return {
            "analyse": content.analysis,
            "subject": content.subject,
            "greeting": content.greeting,
            "paragraphs": content.paragraphs,
            "closing": content.closing,
            "signature": content.signature,
        }
