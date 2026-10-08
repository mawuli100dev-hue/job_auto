# Le pipeline (run_pipeline.ps1)

[← Retour au guide](README.md)

## Ce qu'il fait

Pour chaque ligne du CSV filtré :

1. vérification dans le registre (une offre déjà traitée est ignorée) ;
2. vérification des doublons d'une autre source (même entreprise, même intitulé, même
   ville, déjà préparée) ;
3. CV personnalisé (PDF + Word) ;
4. lettre de motivation (PDF + Word) ;
5. fusion du CV, de la lettre et des annexes de `data\extra` ;
6. ajout au registre `data\offres_traitees.csv` ; la candidature est aussi inscrite dans
   `data\candidatures_index.csv` dès que sa lettre est générée (voir « Libérer de la
   place » dans le [README](README.md)).

Le dossier est créé dans la source du CSV traité :
`data\<source>\3_candidatures\<date>\<entreprise>_<id>\`. Un résumé du lot est enregistré
à côté du CSV : `resume_pipeline_<source>_<type>_<date>.csv`.

Commence toujours avec `-MaxOffers 2`, relis les lettres, puis lance le lot complet.

## Une seule offre (ou quelques-unes)

```powershell
.\run_pipeline.ps1 -CsvPath $filtre.FullName -OfferIds "214CZVT", "214JLFK" -TypeCandidature alternance
```

Ajoute `-Force` pour **refaire** une candidature déjà présente dans le registre (le
contrôle des doublons est alors aussi ignoré).

## Options

| Option | Effet |
|--------|-------|
| `-SourceType spontaneous` | Candidatures spontanées (défaut : `published`, offres publiées) |
| `-TypeCandidature stage` | `alternance`, `stage` ou `auto` (lu dans le CSV, défaut) |
| `-MaxOffers 5` | Traite au plus 5 lignes |
| `-OfferIds "id1", "id2"` | Traite seulement ces offres |
| `-Force` | Retraite même si l'offre est déjà dans le registre |
| `-TraiterNonPrecisees` | Traite aussi les offres sans nom d'entreprise (ignorées par défaut) |
| `-SkipMerge` | Ne fusionne pas les PDF |
| `-SansAnnexes` | Fusionne sans les documents de `data\extra` |
| `-PauseTousLesXOffres 3 -DureePauseLongueSec 30` | Pause de 30 s toutes les 3 candidatures |
| `-PythonExecutable "C:\Users\amavi\anaconda3\envs\job_auto\python.exe"` | Si tu n'as pas fait `conda activate job_auto` |

---

## Refaire une seule pièce

Remplace le chemin du CSV et l'identifiant par les tiens. Le dossier de candidature est
choisi d'après l'emplacement du CSV : utilise le CSV de la bonne source.

```powershell
# CV seul
python src\tailor_cv.py --csv $filtre.FullName --offer-id "214CZVT" --type-candidature alternance

# Lettre seule (le CV doit exister)
python src\generate_letter.py --csv $filtre.FullName --offer-id "214CZVT" --source-type published --type-candidature alternance

# Fusion du dossier PDF
python src\merge_dossier.py --offer-id "214CZVT"
```

| Option de la lettre | Effet |
|---------------------|-------|
| `--review` | Ajoute une relecture par un second appel (meilleure qualité, coût doublé) |
| `--model openai/gpt-4o-mini` | Modèle moins cher (défaut : `anthropic/claude-sonnet-4.5`) |

---

## Le registre des candidatures

`data\offres_traitees.csv` est commun à toutes les sources.

```powershell
# Voir toutes les candidatures déjà traitées
python src\registre_offres.py --list --details

# Une offre est-elle déjà traitée ?
python src\registre_offres.py --check "214CZVT" --type-candidature alternance

# Supprimer les doublons et les lignes vides
python src\registre_offres.py --clean
```
