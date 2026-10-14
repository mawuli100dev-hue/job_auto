# SFdS, Société Française de Statistique (stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres de stage en statistique et data science publiées par la SFdS
([sfds.asso.fr](https://www.sfds.asso.fr/fr/n/506-consulter_les_offres_demploi/?jcon=STAGE&jedu=MASTER)) :
laboratoires (INRAE, INSERM, CEA, universités), Santé publique France, ENGIE...
Aucune clé nécessaire. Le site ne publie pas d'alternances.

## Commandes

```powershell
# 1. Collecter (une quinzaine d'offres, environ 15 secondes)
python src\collect_offers_sfds.py

# 2. Filtrer
$brut = Dernier data\sfds\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\sfds\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

La source est aussi lancée par `run_all_sources.ps1`.

## Options

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 14` | Seulement les offres publiées depuis 14 jours (défaut : 30) |
| `--delai 2` | Pause de 2 secondes entre deux téléchargements (défaut : 1) |

## Ce que fait le collecteur

- Toutes les offres sont sur une seule page, détails compris (le bloc qui s'ouvre au
  clic est déjà dans la page) : organisme, niveau, sujet, date de début, durée,
  description, liens et contact.
- Les **PDF joints** hébergés par la SFdS (la description détaillée du sujet) sont
  téléchargés et leur texte est ajouté à la description : la lettre s'appuie dessus.
  Le lien du PDF devient l'`URL` de l'offre, et `offre.txt` se termine par
  « Fiche de l'offre (PDF) » et « Site de l'organisme ». Les autres sites ne sont pas
  visités.
- L'**e-mail du contact** devient le destinataire de la lettre (colonne `recipient_email`).

## À savoir

- **Source de confiance pour le filtre** : toutes les offres de la SFdS relèvent de la
  statistique, donc les règles « métier hors data » et « ne parle pas de data » ne s'y
  appliquent pas (le vocabulaire de la statistique académique, comme « analyse de
  survie » ou « biostatistique », les aurait écartées à tort). Les autres règles
  restent : défense, offres réservées, stages trop tôt, doublons.
- Les offres sont de niveau **master ou doctorat** : la lettre contient la phrase
  « Je suis conscient que ce stage s'adresse à des étudiants de M1/M2… ».
- Beaucoup de sujets sont des stages de recherche, parfois rédigés en anglais : la
  lettre reste en français.
