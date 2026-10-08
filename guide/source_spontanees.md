# Candidatures spontanées

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

Pour écrire à une entreprise qui n'a pas publié d'offre.

## Où ranger le CSV

```text
data\spontanees\1_brutes\<type>\mon_fichier.csv
```

Colonnes :

| Colonne | Contenu |
|---------|---------|
| **`id`** | Identifiant unique, par exemple `SPONT-nom-entreprise` |
| **`entreprise`** | Nom de l'entreprise |
| `lieu` | Ville |
| `description` | **Ce que fait l'entreprise** : 2 ou 3 phrases vraies tirées de son site |
| `activite`, `secteur` | Secteur d'activité |
| `poste_cible` | Poste visé, par exemple `Data Analyst` (défaut : Data Analyst) |
| `recipient_name`, `recipient_email` | Contact, s'il est connu |

> La lettre ne peut parler de l'entreprise qu'avec ce que contient `description`.
> Une description vague donne une lettre vague : c'est ce qui fera la différence.

## Commande

Pas de collecte ni de filtre : le pipeline part directement de ta liste.

```powershell
$liste = Dernier data\spontanees\1_brutes\alternance "*.csv"
.\run_pipeline.ps1 -CsvPath $liste.FullName -SourceType spontaneous -TypeCandidature alternance -MaxOffers 3
```

Pour des stages spontanés, remplace `alternance` par `stage` partout.

## Étape par étape

```powershell
python src\tailor_cv.py --csv $liste.FullName --offer-id "SPONT-nom-entreprise" --source-type spontaneous --type-candidature alternance
python src\generate_letter.py --csv $liste.FullName --offer-id "SPONT-nom-entreprise" --source-type spontaneous --type-candidature alternance
```

Les candidatures sont rangées dans `data\spontanees\3_candidatures\`.
