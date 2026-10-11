# Le pipeline (run_pipeline.ps1)

[← Retour au guide](README.md)

## Ce qu'il fait

Pour chaque ligne du CSV filtré :

1. vérification dans le registre (une offre déjà traitée est ignorée) ;
2. vérification des doublons d'une autre source (même entreprise, même intitulé, même
   ville, déjà préparée) ;
3. CV personnalisé (PDF + Word) ;
4. lettre de motivation (PDF + Word) ;
5. fusion du CV, de la lettre et des annexes de `data\extra`, puis compression des deux
   PDF à envoyer (`CV_LM_AMAVIGAN.pdf`, `LM_x_AMAVIGAN.pdf`) à **500 Ko ou moins** ;
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
| `-SansCompression` | Ne compresse pas les PDF à envoyer après la fusion |
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

## Compresser des dossiers déjà faits

`compress_dossiers.py` cherche tous les `CV_LM_AMAVIGAN.pdf` et `LM_x_AMAVIGAN.pdf` d'un
dossier (sous-dossiers compris), réduit leur taille et les remet à leur place.

```powershell
# Toutes les candidatures d'un jour
python src\compress_dossiers.py "data\linkedin\3_candidatures\2026-10-08"

# Toutes les candidatures d'une source, ou de toutes les sources
python src\compress_dossiers.py "data\france_travail\3_candidatures"
python src\compress_dossiers.py data

# Une seule candidature
python src\compress_dossiers.py --offer-id "214CZVT"
```

| Option | Effet |
|--------|-------|
| `--cible-ko 400` | Taille visée par PDF, en Ko (défaut : 500 ; `0` = un seul passage) |
| `--qualite 60` | Qualité JPEG maximale des images (défaut : 70) |
| `--sans-perte` | Ne touche pas aux images (environ -18 %, souvent au-dessus de 500 Ko) |
| `--forcer` | Recompresse aussi les PDF déjà compressés |

- Le texte des pages n'est jamais modifié. Les images (bulletins scannés, logos...)
  sont réenregistrées en JPEG avec une qualité qui baisse par paliers (70, 55, 45,
  35, 25) jusqu'à passer sous la taille visée : le premier palier qui suffit est
  gardé. Même à 25, le tampon des bulletins et les logos restent nets.
- Le poids restant vient surtout des **polices intégrées aux annexes** (`data\extra`,
  environ 390 Ko). Si un PDF reste au-dessus de 500 Ko (« objectif non atteint »),
  allège les annexes.
- Un PDF n'est remplacé que si la version compressée est plus petite et se relit
  correctement. Un PDF déjà compressé et sous la taille visée est ignoré (sauf
  `--forcer`).
- Pour retrouver un PDF non compressé, refais la fusion : `python src\merge_dossier.py --offer-id "214CZVT"`.

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
