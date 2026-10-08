# Engagement Jeunes (alternance et stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres de grandes entreprises (Stellantis, Airbus, Safran, Thales, Wavestone...), sur
[engagement-jeunes.com](https://www.engagement-jeunes.com). Aucune clé nécessaire.

## Alternance

```powershell
# 1. Collecter
python src\collect_offers_engagement_jeunes.py --type-candidature alternance --keywords-list "data,$MOTS" --max-anciennete-jours 7

# 2. Filtrer
$brut = Dernier data\engagement_jeunes\1_brutes\alternance "offres_*.csv"
python src\filter_offers.py --type-candidature alternance --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\engagement_jeunes\2_filtrees\alternance "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature alternance -MaxOffers 2
```

## Stage

```powershell
# 1. Collecter
python src\collect_offers_engagement_jeunes.py --type-candidature stage --keywords-list "data,$MOTS" --max-anciennete-jours 7

# 2. Filtrer
$brut = Dernier data\engagement_jeunes\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater
$filtre = Dernier data\engagement_jeunes\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

## Options utiles

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 7` | Seulement les offres des 7 derniers jours (défaut : 21) |
| `--sans-filtre-mots-cles` | Garde toutes les offres trouvées par le site |
| `--delai 2` | Pause de 2 secondes entre deux pages (défaut : 1) |

## À savoir

- Le site renvoie beaucoup d'offres : lors d'un test sur 7 jours avec seulement
  « data » et « statistique », 367 offres trouvées, 253 après collecte, **139 après
  filtrage**. Avec toute la liste `$MOTS`, la collecte prend nettement plus de temps.
- Les filtres d'ancienneté du site sont 1, 2, 7, 31 ou 92 jours ; le script vérifie
  ensuite la date exacte de chaque offre.
- Le site autorise les robots sur toutes ses pages. Le script fait une pause d'une
  seconde entre deux pages.
- Les offres n'indiquent pas de date de début : la disponibilité du CV est déduite
  de la description.
