# job_automation/src/config/letter_examples.py

"""
Lettres écrites à la main par le candidat. Elles servent de modèle
de style au LLM : logique, ton, longueur, simplicité.

Les faits propres à chaque entreprise (navire AIS, panaches turbides,
Transitions Pro...) ne doivent jamais être réutilisés : seule la
manière d'écrire compte. LetterValidator vérifie qu'aucune phrase
n'est recopiée.

Pour ajouter un modèle : ajouter un LetterExample avec le texte
des paragraphes, sans en-tête ni formule de politesse.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LetterExample:
    label: str
    subject: str
    paragraphs: tuple[str, ...]


LETTER_EXAMPLES = (
    LetterExample(
        label=(
            "Offre publiée, alternance Chargé d'études / Data Analyst "
            "dans un organisme d'accompagnement des reconversions"
        ),
        subject=(
            "Candidature pour une alternance, Chargé d'études / "
            "Data Analyst, Rennes"
        ),
        paragraphs=(
            "Ce qui m'a immédiatement convaincu dans votre offre, c'est la dimension double de ce poste : produire des analyses statistiques rigoureuses tout en les transformant en outils de pilotage concrets pour des acteurs de l'emploi et de la formation. Accompagner les transitions professionnelles à travers la donnée est une mission qui résonne particulièrement avec mon propre parcours, puisque je suis moi-même en reconversion de l'ingénierie logicielle vers la science des données.",
            "En 2e année de BUT Science des Données, j'ai développé une pratique concrète de la structuration, du traitement et de la restitution de données complexes. J'ai conçu une base de données PostgreSQL de 15 tables normalisées pour un projet universitaire, avec un modèle conceptuel de données, un pipeline ETL sous FME et Power BI, et des tests d'intégrité documentés. Cette exigence méthodologique correspond directement à votre besoin de concevoir des plans d'analyse statistique et de garantir l'intégrité des bases de données mobilisées dans vos études.",
            "L'analyse de données hétérogènes pour en extraire des tendances fiables est également au cœur de mon expérience. Dans le cadre d'un projet en climatologie au CEFREM, j'ai construit un pipeline Python croisant trois sources de données distinctes sur 66 ans, avec calcul de tendances et quantification de biais relatifs, une démarche proche de la production de prévisions et d'évaluations que requiert votre poste. J'ai par ailleurs conçu un dashboard Streamlit interactif pour le projet ANTICI'PYR, restituant des résultats complexes de manière lisible pour des utilisateurs non techniques, un objectif similaire au développement de tableaux de bord de suivi de KPIs que vous recherchez.",
            "Je maîtrise Python, R, Power BI ainsi que les bases de données relationnelles (PostgreSQL, MySQL, Oracle), des compétences directement mobilisables pour l'exploitation et la fiabilisation de vos données. Mon parcours antérieur en ingénierie logicielle m'a donné le réflexe de documenter systématiquement mes travaux et de collaborer avec des interlocuteurs variés, un atout pour dialoguer efficacement avec les équipes métiers et techniques de Transitions Pro Bretagne.",
            "Rigoureux, autonome et habitué à travailler en interaction avec des chercheurs de disciplines différentes au CEFREM, j'apprécie particulièrement les environnements où la donnée sert une mission d'intérêt général, ce qui est précisément le cas de l'accompagnement des parcours de reconversion professionnelle que porte votre organisme. Mobile et disponible immédiatement, je suis prêt à m'installer à Rennes pour m'investir pleinement dans cette alternance de 12 mois.",
            "Je serais heureux de vous rencontrer pour vous présenter ma démarche et discuter de la façon dont je pourrais contribuer à vos études et à vos projets de data science.",
        ),
    ),
    LetterExample(
        label=(
            "Offre publiée, stage en télédétection dans une université "
            "(offre visant plutôt des étudiants de master)"
        ),
        subject=(
            "Candidature pour un stage en télédétection, suivi des "
            "panaches turbides sédimentaires, lagon de Mayotte"
        ),
        paragraphs=(
            "Un panache turbide ne reste jamais identique d'une image à l'autre : il se déplace, se dilue, change de forme au gré des marées et des courants. Détecter et suivre ce type de dynamique par satellite est précisément ce que j'ai appris à faire dans mes derniers projets de télédétection, ce qui m'a donné envie de répondre à votre offre pour les projets LESELAM IV et TELCOAST. Je suis conscient que ce stage s'adresse prioritairement à des étudiants de master, alors que je termine actuellement ma 3e année de BUT Science des Données ; c'est sur les conseils d'un de mes professeurs, M. Sébastien Pinel, au vu de mes résultats scolaires et de mon expérience professionnelle déjà acquise, que je me permets de vous soumettre ma candidature.",
            "Le projet que j'ai mené au CEFREM portait déjà sur un environnement littoral : j'ai construit un pipeline Python complet croisant trois sources de données hétérogènes, un modèle régional, une réanalyse atmosphérique et des observations de terrain, sur 66 ans de données, avec calcul de tendances spatio-temporelles et quantification des biais entre modèle et terrain. Ce qui différencie votre projet, c'est qu'il ne s'agit plus de mesurer un flux stable mais de suivre un phénomène mobile et changeant dans le temps, une problématique que j'ai déjà abordée sur un projet de suivi spatio-temporel par imagerie satellite et que je souhaite maintenant appliquer à un enjeu littoral aussi précis que celui des panaches sédimentaires.",
            "J'ai en effet développé un pipeline de détection et de suivi spatio-temporel par imagerie satellitaire, basé sur un modèle YOLOv8 permettant de comparer des images à différents instants et de suivre le déplacement de cibles dans le temps, ainsi qu'un dashboard de cartographie géoréférencée conçu entièrement en Python avec GeoPandas et Cartopy. Je suis donc à l'aise avec le traitement de données satellitaires et les outils SIG nécessaires pour cartographier des dynamiques environnementales dans la durée.",
            "Je n'ai pas une connaissance aussi approfondie de la théorie des milieux marins et littoraux, mais le temps qui reste avant le stage sera pour moi l'occasion de l'approfondir, afin d'être pleinement opérationnel à la fois sur le plan théorique et pratique. La durée de 5 à 6 mois laisse par ailleurs largement le temps de monter en compétence sur ce point, et je suis dès à présent opérationnel sur le traitement de données multisources, la télédétection et la cartographie, qui constituent le cœur du travail demandé. M. Sébastien Pinel, qui a encadré mon stage au CEFREM, peut en témoigner directement si vous souhaitez le contacter.",
            "Disponible pour le premier semestre 2027 et mobile, je suis prêt à m'installer à Mayotte pour la durée du stage. Je serais heureux d'échanger avec vous pour vous présenter plus en détail ma démarche et la manière dont je peux contribuer aux projets LESELAM IV et TELCOAST.",
        ),
    ),
    LetterExample(
        label=(
            "Candidature spontanée, alternance ou stage dans une "
            "entreprise spatiale dont le cœur de métier diffère "
            "de l'expérience du candidat"
        ),
        subject=(
            "Candidature spontanée pour une alternance ou un stage en "
            "data science appliquée à la détection par satellite"
        ),
        paragraphs=(
            "Un navire qui coupe sa balise AIS n'a pas disparu : il a seulement cessé de se signaler. J'ai découvert la manière dont Unseenlabs parvient à le retrouver grâce à sa signature radiofréquence dans l'interview de M. Clément GALIC réalisée par Underscore_. Après avoir présenté l'un de mes projets de détection par imagerie satellitaire à un chercheur de mon école, M. Sébastien Pinel, il m'a vivement conseillé de vous contacter. Cette interview a beaucoup nourri ma curiosité, et je me permets de vous proposer ma candidature. Étudiant en 3e année de BUT Science des Données à l'IUT de Perpignan, antenne de Carcassonne, je suis disponible dès maintenant pour une alternance, ou à partir de 2027 pour un stage.",
            "Ce projet, un agent de reconnaissance spatiale, s'appuie sur un modèle YOLOv8 entraîné sur la fusion des bases DOTA et xView (22 classes, plus de 125 000 objets annotés). Il atteint un mAP50 global de 0,583, et jusqu'à 0,93 pour les navires. Il compare deux images prises à des instants différents pour repérer l'apparition ou la disparition de cibles. Une matrice de pondération lui permet ensuite de déclencher des alertes, par exemple en cas d'intrusion dans une zone interdite.",
            "Pour observer les effets du GSD (Ground Sample Distance), j'ai aussi soumis à mon modèle des captures Google Earth du port de Beyrouth, avant et après l'explosion de 2020. Il a détecté une partie des objets, mais pas les bâtiments de la zone touchée sur l'image d'avant. Faute de référence, il n'a pas pu mettre en évidence leur disparition sur l'image d'après. Cet essai m'a montré à quel point la source et la résolution des images conditionnent les résultats d'un modèle.",
            "Ce projet reste centré sur l'imagerie optique, alors que votre force est l'écoute radiofréquence. Je pense pourtant que nos objectifs sont proches : détecter, suivre et comprendre l'activité maritime à partir de données spatiales. C'est surtout la nature des données de départ qui change. Je suis convaincu que mon habitude de m'adapter à de nouveaux types de données me permettra de monter en compétence sur les vôtres.",
            "Mes projets au laboratoire CEFREM m'ont appris à travailler sur des sources hétérogènes. J'ai notamment croisé un modèle régional, une réanalyse atmosphérique et des observations de terrain sur 66 ans de données, en quantifiant les écarts entre modèle et mesures. J'ai aussi conçu un dashboard géospatial interactif avec Streamlit, Cartopy et GeoPandas.",
            "Je sais qu'il me reste beaucoup à apprendre, notamment sur le traitement du signal et la radiofréquence. Je suis sérieux et autonome, prêt à me former avec rigueur sur ces sujets et à apprendre au contact de vos équipes.",
            "Je serais très heureux de pouvoir échanger avec vous, même brièvement, pour vous présenter mon travail et écouter vos besoins. Vous trouverez mon CV en pièce jointe.",
        ),
    ),
)


# Formulations des modèles que la lettre peut reprendre telles
# quelles : ce sont des faits sur le candidat, pas du style.
FREE_PHRASES = (
    "Étudiant en 3e année de BUT Science des Données à l'IUT "
    "de Perpignan, antenne de Carcassonne",
    "Étudiant en troisième année de BUT Science des Données à "
    "l'IUT de Perpignan, antenne de Carcassonne",
)


# Ce qui fait la logique commune des trois lettres, formulé pour
# le LLM. À garder aligné sur LETTER_EXAMPLES.
LETTER_LOGIC = """
1. L'accroche part de l'entreprise, jamais du candidat : une image concrète du problème qu'elle traite (« Un navire qui coupe sa balise AIS n'a pas disparu... ») ou ce qui a convaincu le candidat dans l'offre (« Ce qui m'a immédiatement convaincu dans votre offre, c'est... »). Puis le lien personnel avec le candidat, puis qui il est et ce qu'il demande.
2. Un projet par paragraphe, raconté simplement : ce qu'il a fait, avec quels outils, avec les chiffres réels du CV (15 tables, 66 ans, mAP50 de 0,583). Le paragraphe se termine par un pont explicite et honnête vers une mission précise de l'offre : « une démarche proche de... », « ce qui correspond directement à votre besoin de... », « Ce qui différencie votre projet, c'est que... ».
3. L'honnêteté sur l'écart : si l'offre demande un domaine, un outil ou un niveau que le CV ne montre pas, le candidat le dit simplement (« Je sais qu'il me reste beaucoup à apprendre, notamment sur... », « Ce projet reste centré sur X, alors que votre force est Y ») et dit comment il comblera cet écart. Jamais d'excuse, jamais de fausse modestie, jamais de compétence inventée.
4. Un paragraphe court sur ce qui rend le candidat fiable au quotidien, appuyé sur un fait (son parcours en ingénierie logicielle, le travail avec des chercheurs au CEFREM, le tutorat), puis la disponibilité et la mobilité (« je suis prêt à m'installer à <ville> »).
5. Une dernière phrase simple qui propose un échange : « Je serais heureux d'échanger avec vous pour vous présenter... ».
""".strip()
