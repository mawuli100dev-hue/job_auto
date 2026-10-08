# Le filtre (filter_offers.py)

[← Retour au guide](README.md)

Le filtre lit un CSV de `1_brutes` et enregistre le résultat dans le dossier
`2_filtrees` de la même source.

```powershell
python src\filter_offers.py --type-candidature stage --input <fichier brut> --exclude-entreprises $EXCLUES
```

## Ce qu'il écarte, dans l'ordre

1. les offres du mauvais type de contrat et des entreprises exclues ;
2. les **stages qui commencent en 2026** (avant ta période de stage) ;
3. les offres **réservées** à un autre public (« réservé aux élèves fonctionnaires des
   ENS », « réservé aux agents titulaires »...) ou exigeant la nationalité française
   ou européenne ;
4. les employeurs de la **défense**, soumis à habilitation (Ministère des Armées, DRSD,
   DRM, DGSE, offres « AAE- ») ;
5. les **métiers hors data** d'après l'intitulé ;
6. les offres qui **ne parlent pas de data** ;
7. les **doublons** : même offre deux fois dans le fichier, ou déjà préparée depuis une
   autre source (même entreprise, même intitulé, même ville).

## Les règles sur l'intitulé

| Intitulé | Résultat |
|----------|----------|
| Business developer, comptable, juridique, CDI, CDD, senior, confirmé... | Toujours écarté |
| Commercial, sales, web, full stack, backend, PHP, Java, logiciel, support, administrateur système... | Écarté, sauf si l'intitulé contient aussi un terme data (« Data Analyst – Commercial Data Performance » reste) |
| « Développeur » seul | Écarté, sauf avec un terme data ou IA (« Développeur IA », « Développeur Power BI » restent) |
| Tout autre intitulé | Gardé seulement s'il parle de data : un terme data, IA ou « analyste » dans l'intitulé, ou au moins 2 outils/méthodes data dans la description. Sur PASS, un poste d'un domaine non data (« Ressources humaines », « Droit »...) doit avoir un terme data dans son intitulé |

## Après le filtrage

Toutes les offres écartées sont listées à la fin, avec la raison : vérifie d'un coup
d'œil qu'aucune bonne offre n'est partie. Ouvre ensuite le CSV filtré et supprime les
lignes qui ne t'intéressent pas : chaque ligne restante coûte un CV et une lettre.

## Options

| Option | Effet |
|--------|-------|
| `--garder-doublons` | Garde les doublons |
| `--sans-filtre-data` | Garde aussi les offres qui ne parlent pas de data |
| `--garder-stages-precoces` | Garde les stages qui commencent en 2026. Un stage sans date est toujours gardé |
| `--garder-reservees` | Garde les offres réservées à un autre public ou exigeant une nationalité |
| `--garder-defense` | Garde les employeurs de la défense |
| `--exclude-intitules "cybersecurite,reseaux"` | Écarte aussi ces mots (sauf avec un terme data) |
| `--garder-tous-intitules` | Désactive l'exclusion par intitulé |
