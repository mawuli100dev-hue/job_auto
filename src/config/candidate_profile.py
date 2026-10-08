# job_automation/src/config/candidate_profile.py

from dataclasses import dataclass


@dataclass(frozen=True)
class Formation:
    """
    Formation affichée dans le CV :
    une ligne en gras (title) et une ligne en italique (detail).
    """

    title: str
    detail: str


@dataclass(frozen=True)
class Reference:
    name: str
    email: str


@dataclass(frozen=True)
class CandidateProfile:
    """
    Informations stables du candidat, identiques sur tous les CV.
    """

    name: str
    location: str
    phone: str
    email: str
    portfolio: str
    linkedin: str
    github: str

    formations: tuple[Formation, ...]
    references: tuple[Reference, ...] = ()

    @property
    def contact_parts(self) -> list[str]:
        return [
            part
            for part in (
                self.location,
                self.phone,
                self.email,
                self.portfolio,
                self.linkedin,
                self.github,
            )
            if part
        ]

    @property
    def contact(self) -> str:
        return " | ".join(self.contact_parts)

    @property
    def references_line(self) -> str:
        return "; ".join(
            f"{reference.name} : {reference.email}"
            for reference in self.references
        )


CANDIDATE_PROFILE = CandidateProfile(
    name="Hénoc AMAVIGAN",
    location="Carcassonne, France",
    phone="+33 7 74 74 98 25",
    email="amaviganhenoc@gmail.com",
    portfolio="https://portfolioamavigan.vercel.app",
    # Forme encodée (%C3%A9 = é) : elle fonctionne partout, alors
    # qu'un « é » peut casser la détection de lien de certains
    # lecteurs PDF. Pour une URL lisible, personnaliser l'URL du
    # profil dans LinkedIn (ex. /in/henoc-amavigan) puis la reporter ici.
    linkedin=(
        "https://www.linkedin.com/in/"
        "h%C3%A9noc-amavigan-335646394/"
    ),
    github="https://github.com/mawuli100dev-hue",

    formations=(
        Formation(
            title="2026 : 3e année de BUT Science des Données",
            detail=(
                "Spécialité Exploration et Modélisation Statistique "
                "- IUT de Perpignan, Antenne de Carcassonne"
            ),
        ),
        Formation(
            title=(
                "2025 : Licence Professionnelle en Ingénierie "
                "Logicielle - niveau 3e année"
            ),
            detail="École Polytechnique, Lomé, Togo",
        ),
        Formation(
            title="2022 : Baccalauréat C",
            detail=(
                "Lycée d'enseignement général, Lomé, Togo "
                "- Mathématiques et Physique"
            ),
        ),
    ),

    references=(
        Reference(
            name="M. Sébastien Pinel",
            email="sebastien.pinel@univ-perp.fr",
        ),
        Reference(
            name="Mme Noémie Collette",
            email="noemie.collette@univ-perp.fr",
        ),
    ),
)


# ---------------------------------------------------------------------------
# Compétences de secours (preview_cv.py, ou si aucune sélection n'est faite).
# Même format que la sortie de SkillSelector : titre -> liste de puces.
# ---------------------------------------------------------------------------

DEFAULT_SKILLS = {
    "Télédétection & SIG": [
        "QGIS | GeoPandas, Shapely, Cartopy, Folium | xarray | FME",
        (
            "Traitement et croisement de données satellitaires "
            "multisources (modèles/réanalyses, observations terrain)"
        ),
        (
            "Cartographie spatiale géoréférencée, projections, "
            "analyse de tendances spatio-temporelles"
        ),
    ],
    "Traitement de données": [
        "Python, R, SQL | Power BI, Excel",
    ],
    "Développement": [
        "Streamlit, Flask, Nest.js, Next.js | Git, GitHub Actions, Docker",
        "Java, PHP, JavaScript, TypeScript, C, C++",
    ],
    "Atouts": [
        "Permis de conduire B",
        (
            "Rigueur et autonomie technique | Esprit de synthèse, "
            "d'analyse et de gestion de projet"
        ),
    ],
    "Bases de données": [
        "PostgreSQL, MySQL, MongoDB, Neo4j",
    ],
    "Langues": [
        "Anglais : niveau B2 | Allemand : Goethe Zertifikat B2",
    ],
    "Loisirs": [
        "Guitare basse et tuba | Cuisine : pâtisserie",
    ],
}
