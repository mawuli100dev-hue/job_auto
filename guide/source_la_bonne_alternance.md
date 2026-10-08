# La Bonne Alternance (alternance uniquement)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres de [labonnealternance.apprentissage.beta.gouv.fr](https://labonnealternance.apprentissage.beta.gouv.fr),
via l'API officielle (clé `LBA_API_TOKEN` dans `.env`). Le site ne propose pas de stages.

## Les codes ROME

L'API ne cherche pas par mots-clés mais par **codes ROME** (métiers) :

| Code  | Métiers |
|-------|---------|
| M1419 | Data Analyst |
| M1403 | Data Scientist, Data Analyst (études socio-économiques) |
| M1805 | Data Engineer, Machine Learning Engineer |
| M1802 | Business Intelligence |
| M1810 | Production et exploitation des systèmes d'information |

## Commandes

```powershell
# 1. Collecter
python src\collect_offers_lba.py --type-candidature alternance --romes M1419,M1403,M1805,M1802,M1810 --max-anciennete-jours 30

# 2. Filtrer
$brut = Dernier data\la_bonne_alternance\1_brutes\alternance "offres_*.csv"
python src\filter_offers.py --type-candidature alternance --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\la_bonne_alternance\2_filtrees\alternance "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature alternance -MaxOffers 2
```

## Options utiles

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 30` | Seulement les offres publiées depuis 30 jours (défaut : aucune limite) |
| `--ville Toulouse --distance 50` | Autour d'une ville, rayon en km |

## À savoir

- Les offres restent en ligne environ 2 mois et sont souvent plus anciennes que
  celles de France Travail : lors d'un test, aucune n'avait moins de 15 jours. Garde
  une valeur large (30 jours), ou retire l'option pour tout récupérer.
- Les codes ROME couvrent toute l'informatique (jusqu'au réparateur de PC) : c'est le
  filtre qui ne garde que les offres data.
