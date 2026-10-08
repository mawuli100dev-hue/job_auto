# LinkedIn, par les alertes e-mail (alternance et stage)

[← Retour au guide](README.md) · Lance d'abord le bloc « Avant chaque session ».

LinkedIn interdit la collecte automatique. Le logiciel passe donc par tes **alertes
emploi**, reçues dans Gmail : il en tire la liste des nouvelles offres (intitulé,
entreprise, lieu, lien), puis tu complètes la description de celles qui t'intéressent
en les ouvrant dans ton navigateur.

```text
Alertes LinkedIn → Gmail → 0_a_completer → (tu copies la description) → 1_brutes → filtre → pipeline
```

## Une seule fois : la configuration

1. Sur LinkedIn, crée des alertes emploi (recherche → « Créer une alerte »), par exemple
   Data, Data Science, Data Engineer, Télédétection. Elles arrivent sur
   **amaviganayi1@gmail.com**.
2. Le fichier `.env` contient l'accès Gmail :

   ```text
   GMAIL_ADDRESS=amaviganayi1@gmail.com
   GMAIL_APP_PASSWORD=mot de passe d'application Google (16 lettres)
   ```

   Le mot de passe d'application se gère sur
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) :
   tu peux le révoquer et en créer un nouveau à tout moment (mets alors à jour `.env`).

## Commandes

```powershell
# 1. Lire les alertes reçues depuis 7 jours (Gmail en lecture seule)
python src\collect_alerts_gmail.py

# 2. Compléter les descriptions, offre par offre
python src\completer_offres.py

# 3. Filtrer
$brut = Dernier data\linkedin\1_brutes\stage "offres_*.csv"
python src\filter_offers.py --type-candidature stage --input $brut.FullName --exclude-entreprises $EXCLUES

# 4. Candidater (test sur 2 offres, puis retire -MaxOffers pour le lot complet)
$filtre = Dernier data\linkedin\2_filtrees\stage "offres_filtrees_*.csv"
.\run_pipeline.ps1 -CsvPath $filtre.FullName -TypeCandidature stage -MaxOffers 2
```

Pour l'alternance, remplace `stage` par `alternance` aux étapes 3 et 4.

## L'étape 2 en détail

Pour chaque offre, le script l'affiche et l'ouvre dans ton navigateur. Sur la page :

1. sélectionne le texte de **« À propos de l'offre d'emploi »** (seulement la
   description : pas les menus ni les offres suggérées) ;
2. copie-le (**Ctrl+C**) ;
3. reviens dans PowerShell et appuie sur **Entrée**.

| Touche | Effet |
|--------|-------|
| Entrée | Lit la description copiée et range l'offre dans `1_brutes` |
| `p` | Passe l'offre : elle reste à compléter pour la prochaine fois |
| `x` | Offre sans intérêt : elle ne sera plus proposée |
| `q` | Quitte ; la progression est enregistrée, tu reprends où tu t'étais arrêté |

Si l'intitulé ne dit pas s'il s'agit d'un stage ou d'une alternance, le script te le
demande. Tu ne complètes que les offres qui t'intéressent : tu ne paies le CV et la
lettre que pour celles-là.

## Options

| Commande | Option | Effet |
|----------|--------|-------|
| `collect_alerts_gmail.py` | `--jours 3` | Lit les alertes des 3 derniers jours (défaut : 7) |
| `completer_offres.py` | `--fichier <liste>` | Complète une liste précise (défaut : la plus récente) |

## À savoir

- La lecture de Gmail se fait en **lecture seule** : aucun e-mail n'est modifié,
  supprimé ni marqué comme lu.
- Une offre n'est proposée qu'**une fois** : celles déjà listées, déjà traitées
  (registre) ou déjà préparées depuis une autre source (index) sont écartées.
- Les liens enregistrés sont nettoyés : les jetons de connexion contenus dans les
  e-mails ne sont pas conservés.
- Les e-mails de confirmation de création d'alerte contiennent déjà une dizaine
  d'offres : ils sont lus aussi.

## Où sont les fichiers

```text
data\linkedin\
├── 0_a_completer\<date>\     listes tirées des alertes (colonne « statut » : complétée, sans intérêt)
├── 1_brutes\<type>\<date>\   offres complétées, prêtes pour le filtre
├── 2_filtrees\<type>\<date>\
└── 3_candidatures\<date>\<entreprise>_<id>\
```
