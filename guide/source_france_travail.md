# France Travail (alternance et stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres de [francetravail.fr](https://candidat.francetravail.fr), via l'API officielle
(clés `FT_CLIENT_ID` et `FT_CLIENT_SECRET` dans `.env`).

## Alternance

```powershell
# 1. Collecter
python src\collect_offers.py --type-candidature alternance --keywords-list $MOTS --max-anciennete-jours 3

# 2. Filtrer
$brut = Dernier data\france_travail\1_brutes\alternance "offres_*.csv"
python src\filter_offers.py --type-candidature alternance --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\france_travail\2_filtrees\alternance "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature alternance -MaxOffers 2
```

## Stage

```powershell
# 1. Collecter
python src\collect_offers.py --type-candidature stage --keywords-list $MOTS --max-anciennete-jours 3

# 2. Filtrer
$brut = Dernier data\france_travail\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater
$filtre = Dernier data\france_travail\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

## Options utiles

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 3` | Seulement les offres des 3 derniers jours (défaut : 21) |
| `--commune 11069 --distance 50` | Autour d'une commune (code INSEE, ici Carcassonne), rayon en km |

## À savoir

- Beaucoup d'offres n'ont pas de nom d'entreprise (« Non precise ») : le pipeline les
  ignore, sauf avec `-TraiterNonPrecisees`.
- Les offres des sites partenaires (HelloWork, Indeed...) apparaissent souvent ici
  aussi : la déduplication évite de les traiter deux fois.
