# Guide : de la collecte des offres aux dossiers de candidature

Toutes les commandes se lancent dans **PowerShell**, depuis le dossier du projet.

```text
1. Collecter      un collecteur par source
2. Filtrer        filter_offers.py
3. Candidater     run_pipeline.ps1  →  CV + lettre + dossier PDF fusionné + registre
```

## Les guides

| Guide | Contenu |
|-------|---------|
| [source_france_travail.md](source_france_travail.md) | France Travail : alternance et stage |
| [source_la_bonne_alternance.md](source_la_bonne_alternance.md) | La Bonne Alternance : alternance |
| [source_pass.md](source_pass.md) | PASS, fonction publique : alternance et stage |
| [source_engagement_jeunes.md](source_engagement_jeunes.md) | Engagement Jeunes : alternance et stage |
| [source_letudiant.md](source_letudiant.md) | L'Étudiant Jobs & Stages : alternance et stage |
| [source_manuelles.md](source_manuelles.md) | Offres ajoutées à la main (LinkedIn, Apify, sites d'entreprises...) |
| [source_spontanees.md](source_spontanees.md) | Candidatures spontanées |
| [etape_filtre.md](etape_filtre.md) | Ce que fait le filtre, et ses options |
| [etape_pipeline.md](etape_pipeline.md) | Ce que fait le pipeline, refaire une pièce, le registre |
| [sites_non_collectes.md](sites_non_collectes.md) | Sites étudiés mais non collectés, et pourquoi |
| [git_push.md](git_push.md) | Publier le code sur GitHub sans les données |

---

## Avant chaque session

Copie ce bloc dans PowerShell à l'ouverture de chaque nouvelle fenêtre :

```powershell
cd "C:\Users\amavi\projects-studio\Nouveau dossier\job_automation"
conda activate job_auto

# Les mots-clés de recherche
$MOTS = "data analyst,data scientist,data engineer,data science,analyste de données,analyste data,statistique,statistic,statisticien,BI,power bi,big data,machine learning,deep learning,computer vision,vision par ordinateur,intelligence artificielle,IA,AI,géomatique,SIG,télédétection"

# Entreprises à exclure au filtrage
$EXCLUES = "ISCOD,OPENCLASSROOMS,Tetranergy Business School Rodez"

# Le fichier le plus récent d'un dossier
function Dernier($dossier, $motif) {
    Get-ChildItem $dossier -Recurse -Filter $motif | Sort-Object LastWriteTime | Select-Object -Last 1
}
```

- Sans `conda activate job_auto`, la commande `python` ne trouve pas les bibliothèques
  du projet (pypdf, xhtml2pdf, openai...).
- Une recherche est lancée **pour chaque mot-clé** de `$MOTS`, puis les résultats sont
  fusionnés et dédoublonnés. Plus la liste contient d'intitulés différents, plus on
  récupère d'offres. Sépare-les par des virgules, sans espace autour.

Le fichier `.env` doit contenir :

```text
OPENROUTER_API_KEY=...   (CV et lettres)
FT_CLIENT_ID=...         (France Travail)
FT_CLIENT_SECRET=...     (France Travail)
LBA_API_TOKEN=...        (La Bonne Alternance)
```

PASS, Engagement Jeunes et L'Étudiant ne demandent aucune clé.

---

## Où sont mes fichiers ?

Chaque source a son propre dossier, avec les 3 étapes dans l'ordre :

```text
data\
├── france_travail\
│   ├── 1_brutes\<type>\<date>\            offres collectées
│   ├── 2_filtrees\<type>\<date>\          offres filtrées + résumés du pipeline
│   └── 3_candidatures\<date>\<entreprise>_<id>\
│                                          CV, lettre, CV_LM_AMAVIGAN.pdf à envoyer
├── la_bonne_alternance\                   (même organisation)
├── pass\
├── engagement_jeunes\
├── letudiant\
├── manuelles\                             offres ajoutées à la main
├── spontanees\                            candidatures spontanées
├── extra\                                 annexes ajoutées au dossier PDF
├── offres_traitees.csv                    registre : identifiants des offres déjà traitées
└── candidatures_index.csv                 index : entreprise, intitulé, lieu de chaque candidature
```

`<type>` vaut `alternance` ou `stage`. Le dossier à envoyer est toujours
`data\<source>\3_candidatures\<date>\<entreprise>_<id>\` :

| Fichier | Contenu |
|---------|---------|
| `CV_LM_AMAVIGAN.pdf` | CV + lettre + annexes : **le fichier à envoyer** |
| `LM_x_AMAVIGAN.pdf` | Lettre + annexes, sans le CV |
| `CV_Henoc_AMAVIGAN.pdf` / `.docx` | CV seul |
| `LM_Henoc_AMAVIGAN.pdf` / `.docx` | Lettre seule (le `.docx` pour la retoucher) |
| `offre.txt` | L'offre, avec son lien pour postuler |

---

## Libérer de la place

Tu peux supprimer les anciens dossiers de `data\<source>\3_candidatures\` sans risque de
repostuler à la même offre. Deux fichiers gardent la mémoire de tout ce qui a été fait :

| Fichier | Ce qu'il garde | Ce qu'il évite |
|---------|----------------|----------------|
| `data\offres_traitees.csv` | L'identifiant de chaque offre traitée | Retraiter la même offre de la même source |
| `data\candidatures_index.csv` | Date, source, identifiant, entreprise, intitulé, lieu et dossier de chaque candidature | Retraiter la même offre venue d'une **autre** source (identifiant différent) |

L'index se remplit tout seul : chaque lettre générée y ajoute sa candidature, et les
dossiers encore présents y sont recopiés au premier filtrage ou pipeline. Avant de
supprimer des dossiers, lance une fois le filtre ou le pipeline pour que l'index soit
à jour. **Ne supprime jamais ces deux fichiers.**

Tu peux aussi supprimer les anciens CSV de `1_brutes` et `2_filtrees` : ils ne servent
plus une fois les candidatures préparées.

---

## Coût

| Pièce | Modèle | Coût estimé |
|-------|--------|-------------|
| Lettre | Claude Sonnet 4.5, un seul appel | ~0,05 $ |
| CV | gpt-4o-mini | ~0,01 $ |

Environ **6 $ pour 100 candidatures**. Suis la dépense réelle sur le tableau de bord
OpenRouter. Une relecture (`--review`) ou une correction automatique ajoute un appel.
La collecte et le filtre sont gratuits.

---

## Problèmes fréquents

| Message | Solution |
|---------|----------|
| `No module named 'pypdf'` ou `Freetype library not found` | `conda activate job_auto` |
| `Dernier` n'est pas reconnu | Relance le bloc « Avant chaque session » (la fonction disparaît à chaque nouvelle fenêtre PowerShell) |
| `cv_data.json est introuvable` | Lance `tailor_cv.py` avant `generate_letter.py`, avec le même CSV et le même `--source-type` |
| `IGNOREE (deja traitee)` | Normal : l'offre est dans le registre. `-Force` pour la refaire |
| `IGNOREE (doublon autre source)` | Normal : la même offre a déjà été préparée depuis une autre source ; son dossier est indiqué |
| `IGNOREE (entreprise non precisee)` | Normal : ajoute `-TraiterNonPrecisees` pour la traiter quand même |
| `ATTENTION (style, à relire)` | La lettre est générée, mais relis le point signalé avant de l'envoyer |
| `OPENROUTER_API_KEY doit être défini` | Vérifie le fichier `.env` |

---

## Réorganisation de data\ (déjà faite le 8 octobre 2026)

Les anciens dossiers (`data\offres`, `data\offres_lba`, `data\offres_pass`,
`data\offres_manuelles`, `data\offres_filtrees`, `data\candidatures`) ont été rangés
par source avec `python src\migrate_data_layout.py --appliquer`. Le journal des
déplacements est dans `data\migration_2026-10-08_073839.csv`. Relancer le script
sans `--appliquer` montre ce qu'il resterait à ranger.
