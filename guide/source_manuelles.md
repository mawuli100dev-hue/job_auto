# Offres ajoutées à la main (LinkedIn, Apify, sites d'entreprises...)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Pour les offres des sites non collectés automatiquement (LinkedIn, Indeed, Welcome to
the Jungle, sites carrière des entreprises...) : tu prépares toi-même un CSV, et le
logiciel s'occupe du reste (filtre, déduplication, CV, lettre).

## Où ranger le CSV

```text
data\manuelles\1_brutes\<type>\<date>\offres_manuelle_<type>_<date>.csv
```

- `<type>` : `alternance` ou `stage` ;
- le nom du fichier doit commencer par `offres_` ;
- encodage **UTF-8**, séparateur virgule.

## Les colonnes

Mêmes colonnes que les offres PASS. Les colonnes en gras sont indispensables ; les
autres améliorent le CV et la lettre quand elles sont remplies.

| Colonne | Contenu | Exemple |
|---------|---------|---------|
| **`id`** | Identifiant unique de l'offre (jamais deux fois le même) | `LI-4475844418` |
| **`source`** | Site d'origine | `linkedin` |
| **`type_candidature`** | `alternance` ou `stage` | `stage` |
| **`intitule`** | Intitulé du poste | `Stage Data Scientist (H/F)` |
| **`entreprise`** | Nom de l'entreprise | `Thales` |
| **`description`** | **Description complète de l'offre** : missions, profil, entreprise. C'est elle qui fait la qualité de la lettre | ... |
| `lieu` | Ville (et département) | `Toulouse (31)` |
| `type_contrat` | Libellé du contrat | `Stage` |
| `nature_contrat` | Précision sur le contrat | `Contrat d'apprentissage` |
| `duree_contrat` | Durée | `6 mois` |
| `date_debut` | Date de début, au format `Février 2027` ou `2027-02-01` | `Mars 2027` |
| `date_creation` | Date de publication, au format `2026-10-08` | `2026-10-08` |
| `niveau_diplome` | Niveau visé | `Bac+5` |
| `domaine` | Domaine du poste | `Data, IA` |
| `competences` | Outils et compétences demandés | `Python, SQL, PyTorch` |
| `recipient_email` | E-mail du recruteur, s'il est connu | `rh@entreprise.fr` |
| `url` | Lien de l'offre | `https://www.linkedin.com/jobs/view/...` |

Ligne d'en-tête à copier :

```text
id,source,type_candidature,intitule,entreprise,lieu,type_contrat,nature_contrat,duree_contrat,date_debut,date_creation,niveau_diplome,domaine,competences,description,recipient_email,url
```

## Offres exportées depuis Apify (LinkedIn...)

La remise en forme se fait **en dehors du logiciel** : donne l'export d'Apify à une IA
externe (Gemini...) avec un exemple de CSV PASS (`data\pass\1_brutes\...`), pour qu'elle
le réorganise dans ce format de colonnes, avec `source` = `linkedin` et un `id` unique par
offre (l'identifiant LinkedIn de l'offre, précédé de `LI-`). Range ensuite le fichier
comme ci-dessus : le logiciel prend le relais à partir du filtre.

Vérifie surtout que la colonne `description` contient bien **toute** la description :
sans elle, la lettre reste générique.

## Commandes

```powershell
# 2. Filtrer
$brut = Dernier data\manuelles\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 3. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\manuelles\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

Pour l'alternance, remplace `stage` par `alternance` partout.

## À savoir

- La déduplication compare tes offres manuelles aux candidatures déjà préparées depuis
  les autres sources : une offre LinkedIn déjà vue sur France Travail ou Engagement
  Jeunes est écartée (même entreprise, même intitulé, même ville).
- Les candidatures sont rangées dans `data\manuelles\3_candidatures\`.
