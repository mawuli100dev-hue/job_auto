# job_automation/src/config/known_tools.py

"""
Outils que le candidat connaît (fonctionnement, concepts) sans les avoir
encore utilisés dans un projet complet.

- CV : ils apparaissent en « Notions de ... » dans competences_pool.json,
  seulement quand l'offre les cite (voir les tags de ces lignes).
- Lettre : si l'offre en demande, la lettre le dit honnêtement en une
  phrase, sans inventer de projet (voir LetterPromptBuilder).

Pour ajouter un outil : une ligne (nom affiché, variantes reconnues dans
l'offre), puis l'ajouter à une ligne « Notions de ... » du fichier
competences_pool.json pour qu'il apparaisse aussi sur le CV.
"""

KNOWN_TOOLS_WITHOUT_PROJECT: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Data engineering / Big Data
    ("Spark / PySpark", ("spark", "pyspark", "apache spark")),
    ("Databricks", ("databricks",)),
    ("Airflow", ("airflow", "apache airflow")),
    ("Hadoop", ("hadoop", "hdfs", "mapreduce")),
    # Cloud et entrepôts de données
    ("AWS", ("aws", "amazon web services")),
    ("GCP / BigQuery", ("gcp", "google cloud", "bigquery")),
    ("Snowflake", ("snowflake",)),
    ("dbt", ("dbt",)),
    # IA et MLOps
    ("LLM / RAG / LangChain", ("llm", "llms", "rag", "langchain", "ia generative")),
    ("MLOps / MLflow", ("mlops", "mlflow")),
    ("Kubernetes", ("kubernetes", "k8s")),
    ("FastAPI", ("fastapi",)),
    # Automatisation de tests et CI/CD
    ("Selenium", ("selenium",)),
    ("Cypress", ("cypress",)),
    ("Jenkins", ("jenkins",)),
    ("GitHub Actions", ("github actions", "github actions ci/cd")),
    # Automatisation de tâches et RPA
    ("UiPath", ("uipath",)),
    ("Power Automate", ("power automate", "microsoft power automate")),
    ("Zapier", ("zapier",)),
    # « make » seul est un mot anglais courant (« make an impact ») :
    # seules les formes propres à l'outil sont reconnues.
    ("Make / Integromat", ("make com", "integromat")),
    ("n8n", ("n8n",)),
    # BI et logiciels statistiques
    ("Tableau", ("tableau software", "tableau desktop", "tableau server")),
    ("Qlik / Looker", ("qlik", "qlik sense", "qlikview", "looker")),
    # « SAS » seul est aussi une forme de société (« Dupont SAS ») :
    # on ne le reconnaît qu'à côté d'un autre outil statistique.
    (
        "SAS",
        (
            "sas base",
            "sas enterprise",
            "sas enterprise guide",
            "sas viya",
            "logiciel sas",
            "python sas",
            "sas python",
            "r sas",
            "sas r",
            "sql sas",
            "sas sql",
            "spss sas",
            "sas spss",
        ),
    ),
    ("Dataiku", ("dataiku",)),
)
