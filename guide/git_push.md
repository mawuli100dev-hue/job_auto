# Publier le code sur GitHub

[← Retour au guide](README.md)

Seul le **code** part sur GitHub. Le fichier `.gitignore` bloque tout le reste :

| Jamais publié | Pourquoi |
|---------------|----------|
| `data\` en entier | Offres, CSV filtrés, dossiers de candidature (CV, lettres), registre, index, annexes personnelles (bulletins, lettres de recommandation) |
| `spont\data\` | Anciennes candidatures spontanées |
| `*.csv`, `*.xlsx`, `*.pdf`, `*.docx`, `*.html` | Données et documents générés |
| `.env` | Clés d'API (OpenRouter, France Travail, La Bonne Alternance) |
| `__pycache__\`, `src\preview_output\`, `src\contenu_*.txt` | Fichiers générés ou copies du code |

## Avant chaque push : vérifier ce qui part

```powershell
cd "C:\Users\amavi\projects-studio\Nouveau dossier\job_automation"
git status
```

Seuls des fichiers de code (`.py`, `.ps1`), de configuration (`.json`) et du guide
(`.md`) doivent apparaître. Si un CSV, un PDF ou un dossier `data\` apparaît, **arrête**
et vérifie le `.gitignore`.

## Publier

```powershell
git add -A
git status
git commit -m "Décris ici ce qui a changé"
git push
```

`git add -A` respecte le `.gitignore` : les données restent sur ton ordinateur.

## À savoir

- Le dépôt `mawuli100dev-hue/job_auto` est **public**. Même sans les données, le code
  contient des informations personnelles : ton nom, ton téléphone, ton e-mail et les
  e-mails de tes références (`src\config\candidate_profile.py`), tes lettres
  (`src\config\letter_examples.py`), ton parcours (`experiences.json`,
  `competences_pool.json`). Pour les garder pour toi, passe le dépôt en **privé** :
  GitHub → le dépôt → Settings → General → Danger Zone → Change visibility.
- Retirer un fichier du suivi (`git rm --cached`) ne l'efface pas de l'**historique** :
  les anciennes versions restent visibles sur GitHub tant que l'historique n'est pas
  réécrit.
