# PASS, fonction publique (alternance et stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Offres des ministères, collectivités, hôpitaux et établissements publics (Météo France,
Santé publique France...), sur [pass.fonction-publique.gouv.fr](https://www.pass.fonction-publique.gouv.fr).
Aucune clé nécessaire.

## Alternance

```powershell
# 1. Collecter
python src\collect_offers_pass.py --type-candidature alternance --keywords-list "data,$MOTS" --max-anciennete-jours 7

# 2. Filtrer
$brut = Dernier data\pass\1_brutes\alternance "offres_*.csv"
python src\filter_offers.py --type-candidature alternance --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\pass\2_filtrees\alternance "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature alternance -MaxOffers 2
```

## Stage

```powershell
# 1. Collecter
python src\collect_offers_pass.py --type-candidature stage --keywords-list "data,$MOTS" --max-anciennete-jours 7

# 2. Filtrer
$brut = Dernier data\pass\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater
$filtre = Dernier data\pass\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

## Options utiles

| Option | Effet |
|--------|-------|
| `--max-anciennete-jours 7` | Seulement les offres des 7 derniers jours (défaut : 21) |
| `--sans-filtre-mots-cles` | Garde toutes les offres trouvées par le site |
| `--delai 2` | Pause de 2 secondes entre deux pages (défaut : 1) |

## À savoir

- Une recherche à plusieurs mots ne trouve que l'**expression exacte** : « data
  scientist » trouve 5 stages, « data » seul plus de 100. D'où le `data,` ajouté
  devant `$MOTS`.
- La recherche du site est **très large** (« IA » trouve « social ») : le script lit
  chaque offre et ne la garde que si un mot-clé y apparaît comme mot entier.
- Les mots très courts (« BI », « IA », « AI ») ramènent des centaines d'offres hors
  sujet à ouvrir une à une : retire « BI » si la collecte est trop longue.
- Pas d'API : le script fait une pause d'une seconde entre deux pages. Compte
  quelques minutes par collecte.
- L'adresse e-mail du contact est récupérée : elle sert de destinataire dans la lettre.
- Le filtre écarte les offres de la défense (Ministère des Armées, DRSD, DRM...) et
  celles réservées à un autre public (« réservé aux élèves fonctionnaires des ENS »).
