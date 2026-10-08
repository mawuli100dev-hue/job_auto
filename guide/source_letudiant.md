# L'Étudiant Jobs & Stages (alternance et stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres de [jobs-stages.letudiant.fr](https://jobs-stages.letudiant.fr) (Eau de Paris,
Safran, Colas, mc2i, start-ups...). Aucune clé nécessaire.

## Alternance

```powershell
# 1. Collecter
python src\collect_offers_letudiant.py --type-candidature alternance --keywords-list "data,$MOTS" --max-anciennete-jours 14

# 2. Filtrer
$brut = Dernier data\letudiant\1_brutes\alternance "offres_*.csv"
python src\filter_offers.py --type-candidature alternance --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\letudiant\2_filtrees\alternance "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature alternance -MaxOffers 2
```

## Stage

```powershell
# 1. Collecter
python src\collect_offers_letudiant.py --type-candidature stage --keywords-list "data,$MOTS" --max-anciennete-jours 14

# 2. Filtrer
$brut = Dernier data\letudiant\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater
$filtre = Dernier data\letudiant\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

## Options utiles

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 14` | Seulement les offres mises à jour depuis 14 jours (défaut : 14) |
| `--delai 2` | Pause de 2 secondes entre deux pages d'offre (défaut : 1) |

## À savoir

- Le site interdit aux robots ses recherches filtrées. Le script passe donc par ses
  **sitemaps** (la liste de toutes ses offres publiée pour les moteurs de recherche,
  environ 85 000 adresses) et garde celles dont **l'intitulé** contient un mot-clé.
  Un mot présent seulement dans la description n'est pas vu.
- Les sitemaps pèsent environ 20 Mo : compte 1 à 2 minutes de téléchargement avant
  la lecture des offres.
- Les sitemaps contiennent aussi des offres expirées : elles sont ignorées.
- Le type de contrat vient de l'offre (stage) et de son intitulé (« alternance »,
  « apprenti »...). Les CDI et CDD sont écartés.
- Lors d'un test sur 14 jours : 49 offres candidates, 13 stages gardés, 10 après
  filtrage.
