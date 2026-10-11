# job_automation/run_all_sources.ps1

<#
.SYNOPSIS
    Enchaîne collecte, filtre et génération des candidatures pour toutes les
    sources automatisées, une source après l'autre.

.DESCRIPTION
    Phase 1 (gratuite) : pour chaque source et chaque type de contrat,
        1. collecte des offres (collect_offers*.py) ;
        2. filtre (filter_offers.py).
    Un récapitulatif affiche alors le nombre d'offres prêtes et le coût
    estimé de la génération, et demande confirmation.

    Phase 2 (payante) : pour chaque CSV filtré, run_pipeline.ps1 génère le
    CV, la lettre, le dossier PDF compressé, et met à jour le registre.

    Sources : france_travail, la_bonne_alternance (alternance seulement),
    pass, engagement_jeunes, letudiant. LinkedIn n'est pas inclus : ses
    offres demandent l'étape manuelle de completer_offres.py.

    Le déroulé complet est enregistré dans data\logs\.

.PARAMETER Sources
    Sources à traiter. Défaut : toutes.

.PARAMETER Types
    Types de contrat : alternance, stage ou les deux. Défaut : les deux.

.PARAMETER MaxOffresParLot
    Nombre maximal de candidatures générées par source et par type.
    0 : toutes. Défaut : 0.

.PARAMETER SansGeneration
    S'arrête après la phase 1 (collecte et filtre) : aucun appel payant.

.PARAMETER SansConfirmation
    Lance la phase 2 sans demander confirmation (usage planifié).

.PARAMETER CoutParCandidatureUsd
    Coût estimé d'une candidature (CV + lettre), pour le récapitulatif.
    Défaut : 0.06.

.EXAMPLE
    .\run_all_sources.ps1

.EXAMPLE
    .\run_all_sources.ps1 -SansGeneration

.EXAMPLE
    .\run_all_sources.ps1 -Sources pass, engagement_jeunes -Types stage -MaxOffresParLot 3
#>

param(
    [ValidateSet(
        "france_travail",
        "la_bonne_alternance",
        "pass",
        "engagement_jeunes",
        "letudiant"
    )]
    [string[]]$Sources = @(
        "france_travail",
        "la_bonne_alternance",
        "pass",
        "engagement_jeunes",
        "letudiant"
    ),

    [ValidateSet("alternance", "stage")]
    [string[]]$Types = @("alternance", "stage"),

    [ValidateRange(0, 100000)]
    [int]$MaxOffresParLot = 0,

    [switch]$SansGeneration,

    [switch]$SansConfirmation,

    [double]$CoutParCandidatureUsd = 0.06,

    [string]$Mots = "data analyst,data scientist,data engineer,data science,analyste de données,analyste data,statistique,statistic,statisticien,BI,power bi,big data,machine learning,deep learning,computer vision,vision par ordinateur,intelligence artificielle,IA,AI,géomatique,SIG,télédétection",

    [string]$Exclues = "ISCOD,OPENCLASSROOMS,Tetranergy Business School Rodez",

    [string]$PythonExecutable = "python"
)


$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

# Accents : Python écrit en UTF-8 et la console doit lire et afficher en
# UTF-8 (sinon « é » devient « Ã© » avec la page de codes 850 de Windows).
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Debut = Get-Date


# ---------------------------------------------------------------------------
# Description des sources
# ---------------------------------------------------------------------------

# Arguments de collecte de chaque source. {TYPE} est remplacé par le type.
$Collecteurs = @{
    "france_travail" = @{
        Script     = "src\collect_offers.py"
        Arguments  = @("--type-candidature", "{TYPE}", "--keywords-list", $Mots, "--max-anciennete-jours", "14")
        Types      = @("alternance", "stage")
    }
    "la_bonne_alternance" = @{
        Script     = "src\collect_offers_lba.py"
        Arguments  = @("--type-candidature", "alternance", "--romes", "M1419,M1403,M1805,M1802,M1810", "--max-anciennete-jours", "30")
        Types      = @("alternance")
    }
    "pass" = @{
        Script     = "src\collect_offers_pass.py"
        Arguments  = @("--type-candidature", "{TYPE}", "--keywords-list", "data,$Mots", "--max-anciennete-jours", "14")
        Types      = @("alternance", "stage")
    }
    "engagement_jeunes" = @{
        Script     = "src\collect_offers_engagement_jeunes.py"
        Arguments  = @("--type-candidature", "{TYPE}", "--keywords-list", "data,$Mots", "--max-anciennete-jours", "14")
        Types      = @("alternance", "stage")
    }
    "letudiant" = @{
        Script     = "src\collect_offers_letudiant.py"
        Arguments  = @("--type-candidature", "{TYPE}", "--keywords-list", "data,$Mots", "--max-anciennete-jours", "14")
        Types      = @("alternance", "stage")
    }
}


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

function Write-Titre {
    param([string]$Texte)

    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host $Texte -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}


function Invoke-Python {
    param(
        [string]$Script,
        [string[]]$Arguments
    )

    # Out-Host : l'affichage de Python va à l'écran, pas dans la valeur
    # renvoyée par la fonction (seul le code de sortie l'est).
    & $PythonExecutable $Script @Arguments | Out-Host

    return $LASTEXITCODE
}


# Fichier le plus récent d'un dossier, créé pendant cette exécution.
function Get-FichierRecent {
    param(
        [string]$Dossier,
        [string]$Motif
    )

    if (-not (Test-Path $Dossier)) {
        return $null
    }

    return Get-ChildItem $Dossier -Recurse -Filter $Motif |
        Where-Object { $_.LastWriteTime -ge $Debut } |
        Sort-Object LastWriteTime |
        Select-Object -Last 1
}


function Get-NombreLignes {
    param([string]$Chemin)

    return @(Import-Csv -LiteralPath $Chemin -Encoding UTF8).Count
}


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------

$DossierLogs = Join-Path $ProjectRoot "data\logs"
New-Item -ItemType Directory -Force $DossierLogs | Out-Null

$Journal = Join-Path $DossierLogs ("run_all_sources_" + $Debut.ToString("yyyy-MM-dd_HHmmss") + ".txt")
Start-Transcript -Path $Journal | Out-Null


try {
    # -----------------------------------------------------------------------
    # Phase 1 : collecte et filtre (gratuit)
    # -----------------------------------------------------------------------

    Write-Titre "Phase 1 : collecte et filtre de toutes les sources"

    $Lots = New-Object "System.Collections.Generic.List[object]"

    foreach ($source in $Sources) {
        $collecteur = $Collecteurs[$source]

        foreach ($type in $Types) {
            if ($collecteur.Types -notcontains $type) {
                continue
            }

            Write-Titre "$source / $type"

            $lot = [PSCustomObject]@{
                Source  = $source
                Type    = $type
                Brutes  = 0
                Filtre  = $null
                Offres  = 0
                Statut  = ""
            }

            # 1. Collecte
            $arguments = $collecteur.Arguments | ForEach-Object { $_ -replace "\{TYPE\}", $type }

            Write-Host "`n>>> Collecte" -ForegroundColor Yellow
            $code = Invoke-Python -Script $collecteur.Script -Arguments $arguments

            $brut = Get-FichierRecent `
                -Dossier (Join-Path $ProjectRoot "data\$source\1_brutes\$type") `
                -Motif "offres_*.csv"

            if ($code -ne 0 -or $null -eq $brut) {
                $lot.Statut = "échec de la collecte (code $code)"
                $Lots.Add($lot)
                continue
            }

            $lot.Brutes = Get-NombreLignes $brut.FullName

            if ($lot.Brutes -eq 0) {
                $lot.Statut = "aucune offre collectée"
                $Lots.Add($lot)
                continue
            }

            # 2. Filtre
            Write-Host "`n>>> Filtre" -ForegroundColor Yellow
            $code = Invoke-Python -Script "src\filter_offers.py" -Arguments @(
                "--type-candidature", $type,
                "--input", $brut.FullName,
                "--exclude-entreprises", $Exclues
            )

            $filtre = Get-FichierRecent `
                -Dossier (Join-Path $ProjectRoot "data\$source\2_filtrees\$type") `
                -Motif "offres_filtrees_*.csv"

            if ($code -ne 0 -or $null -eq $filtre) {
                $lot.Statut = "échec du filtre (code $code)"
                $Lots.Add($lot)
                continue
            }

            $lot.Filtre = $filtre.FullName
            $lot.Offres = Get-NombreLignes $filtre.FullName

            if ($MaxOffresParLot -gt 0 -and $lot.Offres -gt $MaxOffresParLot) {
                $lot.Offres = $MaxOffresParLot
            }

            $lot.Statut = if ($lot.Offres -gt 0) { "prêt" } else { "aucune offre après filtre" }
            $Lots.Add($lot)
        }
    }


    # -----------------------------------------------------------------------
    # Récapitulatif et confirmation
    # -----------------------------------------------------------------------

    Write-Titre "Récapitulatif de la phase 1"

    $Lots | Format-Table Source, Type, Brutes, Offres, Statut -AutoSize | Out-Host

    $aGenerer = @($Lots | Where-Object { $_.Statut -eq "prêt" })
    $total = ($aGenerer | Measure-Object -Property Offres -Sum).Sum

    if (-not $total) {
        $total = 0
    }

    $cout = [math]::Round($total * $CoutParCandidatureUsd, 2)

    Write-Host ""
    Write-Host "Candidatures à générer : au plus $total (les offres déjà traitées ou en double seront ignorées)."
    Write-Host "Coût estimé : au plus $cout $ (environ $CoutParCandidatureUsd $ par candidature)."

    if ($SansGeneration -or $total -eq 0) {
        Write-Host "`nPhase 2 non lancée." -ForegroundColor DarkYellow
        return
    }

    if (-not $SansConfirmation) {
        $reponse = Read-Host "`nLancer la génération des CV et des lettres ? (o/n)"

        if ($reponse.Trim().ToLower() -notin @("o", "oui")) {
            Write-Host "Génération annulée. Les CSV filtrés restent prêts dans data\<source>\2_filtrees\." -ForegroundColor DarkYellow
            return
        }
    }


    # -----------------------------------------------------------------------
    # Phase 2 : génération (payant)
    # -----------------------------------------------------------------------

    Write-Titre "Phase 2 : génération des candidatures"

    foreach ($lot in $aGenerer) {
        Write-Titre "Génération : $($lot.Source) / $($lot.Type)"

        $argumentsPipeline = @{
            CsvPath          = $lot.Filtre
            TypeCandidature  = $lot.Type
            PythonExecutable = $PythonExecutable
        }

        if ($MaxOffresParLot -gt 0) {
            $argumentsPipeline.MaxOffers = $MaxOffresParLot
        }

        & (Join-Path $ProjectRoot "run_pipeline.ps1") @argumentsPipeline

        $lot.Statut = if ($LASTEXITCODE -eq 0) { "généré" } else { "généré avec des échecs (voir le résumé du pipeline)" }
    }

    Write-Titre "Terminé"

    $Lots | Format-Table Source, Type, Brutes, Offres, Statut -AutoSize | Out-Host

    Write-Host "Dossiers à envoyer : data\<source>\3_candidatures\$($Debut.ToString('yyyy-MM-dd'))\"
}
finally {
    $duree = (Get-Date) - $Debut
    Write-Host ("Durée : {0:hh\:mm\:ss}" -f $duree)
    Write-Host "Journal : $Journal"
    Stop-Transcript | Out-Null
}
