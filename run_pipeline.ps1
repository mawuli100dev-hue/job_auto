# job_automation/run_pipeline.ps1

<#
.SYNOPSIS
    Prépare automatiquement les dossiers de candidature (CV, lettre,
    dossier fusionné) pour les offres publiées ou les candidatures
    spontanées contenues dans un CSV.

.DESCRIPTION
    Pour chaque offre, le pipeline exécute successivement :

    0. registre_offres.py --check
       Vérifie si la candidature a déjà été traitée.

    1. tailor_cv.py
       Génère le CV personnalisé au format PDF et Word.

    2. generate_letter.py
       Génère la lettre de motivation au format PDF et Word.

    3. merge_dossier.py
       Fusionne le CV, la lettre et les documents annexes.

    4. registre_offres.py --add
       Enregistre la candidature comme traitée seulement si les étapes
       demandées ont réussi.

    Il fonctionne pour :

        -SourceType published    (offres publiées, défaut)
        -SourceType spontaneous  (candidatures spontanées)

    et pour :

        type_candidature = alternance
        type_candidature = stage

.PARAMETER CsvPath
    Chemin du CSV des offres filtrées.

    Le CSV doit contenir au minimum une colonne "id".

.PARAMETER SourceType
    Source des candidatures du CSV :

        published    offres publiées (défaut)
        spontaneous  candidatures spontanées

    Pour spontaneous, le CSV doit contenir les colonnes "id" et
    "entreprise". Les colonnes "lieu", "description", "activite",
    "secteur" et "poste_cible" sont utilisées si elles existent.

.PARAMETER TypeCandidature
    Type de contrat recherché :

        auto
        alternance
        stage

    Avec "auto", le script utilise la colonne "type_candidature" du CSV.

    Si le CSV ne contient pas cette colonne, "alternance" est utilisée
    pour conserver la compatibilité avec les anciens fichiers.

.PARAMETER OfferIds
    Liste facultative d'identifiants à traiter.

    Exemple :

        -OfferIds "214CZVT", "214JLFK"

.PARAMETER MaxOffers
    Nombre maximal d'offres à examiner.

    0 signifie : toutes les offres.

.PARAMETER SkipMerge
    N'exécute pas merge_dossier.py.

    Le CV et la lettre sont tout de même générés. La candidature est
    enregistrée dans le registre si ces étapes réussissent.

.PARAMETER Force
    Retraite les candidatures même si elles sont déjà présentes
    dans le registre.

.PARAMETER TraiterNonPrecisees
    Traite également les offres dont l'entreprise est inconnue.

    Par défaut, ces offres sont ignorées pour éviter des appels LLM
    peu utiles.

.PARAMETER RegistrePath
    Chemin du registre.

    Défaut :

        data\offres_traitees.csv

.PARAMETER ExtraDir
    Dossier contenant les documents annexes à fusionner.

    Défaut :

        data\extra

.PARAMETER SansAnnexes
    Demande à merge_dossier.py de ne pas ajouter les annexes.

.PARAMETER DelaiEntreOffresSec
    Pause courte entre deux candidatures ayant réellement appelé le LLM.

    Défaut : 4 secondes.

.PARAMETER PauseTousLesXOffres
    Nombre de candidatures traitées avant une pause longue.

    Défaut : 3.

    Utiliser 0 pour désactiver les pauses longues.

.PARAMETER DureePauseLongueSec
    Durée de la pause longue.

    Défaut : 30 secondes.

.PARAMETER PythonExecutable
    Commande ou chemin vers l'exécutable Python.

    Défaut :

        python

.EXAMPLE
    .\run_pipeline.ps1 `
        -CsvPath "data\offres_filtrees\alternance\2026-10-01\offres_filtrees_alternance_2026-10-01_100000.csv"

.EXAMPLE
    .\run_pipeline.ps1 `
        -CsvPath "data\offres_filtrees\stage\2026-10-01\offres_filtrees_stage_2026-10-01_100000.csv" `
        -TypeCandidature stage

.EXAMPLE
    .\run_pipeline.ps1 `
        -CsvPath "data\offres_filtrees\alternance\2026-10-01\offres.csv" `
        -TypeCandidature alternance `
        -MaxOffers 5 `
        -PauseTousLesXOffres 3 `
        -DureePauseLongueSec 30

.EXAMPLE
    .\run_pipeline.ps1 `
        -CsvPath "data\offres_spontanees\offres_spontanees.csv" `
        -SourceType spontaneous `
        -TypeCandidature alternance `
        -MaxOffers 3

.EXAMPLE
    .\run_pipeline.ps1 `
        -CsvPath "data\offres_filtrees\stage\2026-10-01\offres.csv" `
        -OfferIds "1234567", "7654321" `
        -TypeCandidature stage `
        -Force
#>


param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [ValidateSet(
        "published",
        "spontaneous"
    )]
    [string]$SourceType = "published",

    [ValidateSet(
        "auto",
        "alternance",
        "stage"
    )]
    [string]$TypeCandidature = "auto",

    [string[]]$OfferIds,

    [ValidateRange(0, 100000)]
    [int]$MaxOffers = 0,

    [switch]$SkipMerge,

    [switch]$Force,

    [switch]$TraiterNonPrecisees,

    [string]$RegistrePath = "data\offres_traitees.csv",

    [string]$ExtraDir = "data\extra",

    [switch]$SansAnnexes,

    [ValidateRange(0, 86400)]
    [int]$DelaiEntreOffresSec = 4,

    [ValidateRange(0, 100000)]
    [int]$PauseTousLesXOffres = 3,

    [ValidateRange(0, 86400)]
    [int]$DureePauseLongueSec = 30,

    [string]$PythonExecutable = "python"
)


# ---------------------------------------------------------------------------
# Configuration générale
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot

$ValeurEntrepriseNonPrecisee = "Non precise"

$TailorCvScript = Join-Path `
    $ProjectRoot `
    "src\tailor_cv.py"

$GenerateLetterScript = Join-Path `
    $ProjectRoot `
    "src\generate_letter.py"

$MergeDossierScript = Join-Path `
    $ProjectRoot `
    "src\merge_dossier.py"

$RegistreScript = Join-Path `
    $ProjectRoot `
    "src\registre_offres.py"

$CheckDuplicateScript = Join-Path `
    $ProjectRoot `
    "src\check_duplicate.py"


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

function Resolve-ProjectPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $expandedPath = [Environment]::ExpandEnvironmentVariables(
        $PathValue
    )

    if ([System.IO.Path]::IsPathRooted($expandedPath)) {
        return [System.IO.Path]::GetFullPath(
            $expandedPath
        )
    }

    return [System.IO.Path]::GetFullPath(
        (Join-Path $ProjectRoot $expandedPath)
    )
}


function ConvertTo-NormalizedText {
    param(
        [AllowNull()]
        [string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $normalized = $Value.Trim().Normalize(
        [Text.NormalizationForm]::FormD
    )

    $withoutDiacritics = [regex]::Replace(
        $normalized,
        "\p{Mn}",
        ""
    )

    $withoutPunctuation = [regex]::Replace(
        $withoutDiacritics,
        "[^a-zA-Z0-9]+",
        " "
    )

    return $withoutPunctuation.Trim().ToLowerInvariant()
}


function Get-NomEntreprise {
    param(
        [AllowNull()]
        [string]$Valeur
    )

    if ([string]::IsNullOrWhiteSpace($Valeur)) {
        return $ValeurEntrepriseNonPrecisee
    }

    return $Valeur.Trim()
}


function Test-EntrepriseNonPrecisee {
    param(
        [AllowNull()]
        [string]$Entreprise
    )

    $normalized = ConvertTo-NormalizedText $Entreprise

    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return $true
    }

    $valeursInconnues = @(
        "non precise",
        "non precisee",
        "non renseigne",
        "non renseignee",
        "non communique",
        "non communiquee",
        "inconnu",
        "inconnue",
        "n a",
        "na"
    )

    return $valeursInconnues -contains $normalized
}


function Test-PythonExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable
    )

    $command = Get-Command `
        $Executable `
        -ErrorAction SilentlyContinue

    if (-not $command) {
        throw (
            "Exécutable Python introuvable : " +
            "'$Executable'. Vérifie ton environnement Python."
        )
    }
}


function Test-RequiredScript {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath
    )

    if (-not (Test-Path -LiteralPath $ScriptPath -PathType Leaf)) {
        throw "Script Python introuvable : $ScriptPath"
    }
}


function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StepName,

        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,

        [Parameter(Mandatory = $false)]
        [string[]]$Arguments = @()
    )

    Write-Host (
        "`n>>> Étape : $StepName"
    ) -ForegroundColor Cyan

    & $PythonExecutable `
        $ScriptPath `
        @Arguments

    $pythonExitCode = $LASTEXITCODE

    if ($pythonExitCode -ne 0) {
        throw (
            "$StepName a échoué " +
            "(code de sortie $pythonExitCode)."
        )
    }
}


function Test-CandidatureDejaTraitee {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ApplicationId,

        [Parameter(Mandatory = $true)]
        [string]$RegistryPath,

        [Parameter(Mandatory = $true)]
        [string]$ContractType
    )

    & $PythonExecutable `
        $RegistreScript `
        --check `
        $ApplicationId `
        --registre `
        $RegistryPath `
        --source-type `
        $SourceType `
        --type-candidature `
        $ContractType `
        *> $null

    $registryExitCode = $LASTEXITCODE

    switch ($registryExitCode) {
        0 {
            return $false
        }

        1 {
            return $true
        }

        default {
            throw (
                "La vérification du registre a échoué " +
                "pour '$ApplicationId' " +
                "(code $registryExitCode)."
            )
        }
    }
}


function Add-CandidatureAuRegistre {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ApplicationId,

        [Parameter(Mandatory = $true)]
        [string]$RegistryPath,

        [Parameter(Mandatory = $true)]
        [string]$ContractType
    )

    & $PythonExecutable `
        $RegistreScript `
        --add `
        $ApplicationId `
        --registre `
        $RegistryPath `
        --source-type `
        $SourceType `
        --type-candidature `
        $ContractType `
        *> $null

    $registryExitCode = $LASTEXITCODE

    if ($registryExitCode -ne 0) {
        throw (
            "L'ajout au registre a échoué " +
            "pour '$ApplicationId' " +
            "(code $registryExitCode)."
        )
    }
}


function Resolve-TypeCandidature {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Rows,

        [Parameter(Mandatory = $true)]
        [string]$RequestedType
    )

    $csvHasTypeColumn = (
        $Rows.Count -gt 0 -and
        $Rows[0].PSObject.Properties.Name -contains "type_candidature"
    )

    $declaredTypes = @()

    if ($csvHasTypeColumn) {
        $declaredTypes = @(
            $Rows |
                ForEach-Object {
                    $value = ConvertTo-NormalizedText `
                        $_.type_candidature

                    if (
                        $value -eq "alternance" -or
                        $value -eq "stage"
                    ) {
                        $value
                    }
                } |
                Sort-Object -Unique
        )
    }

    if ($RequestedType -eq "auto") {
        if ($declaredTypes.Count -eq 1) {
            return $declaredTypes[0]
        }

        if ($declaredTypes.Count -gt 1) {
            throw (
                "Le CSV contient plusieurs types de candidatures : " +
                "$($declaredTypes -join ', '). " +
                "Précise -TypeCandidature alternance ou stage."
            )
        }

        Write-Host (
            "La colonne type_candidature est absente ou vide. " +
            "Le type 'alternance' est utilisé pour compatibilité."
        ) -ForegroundColor DarkYellow

        return "alternance"
    }

    $mismatchedTypes = @(
        $declaredTypes |
            Where-Object {
                $_ -ne $RequestedType
            }
    )

    if ($mismatchedTypes.Count -gt 0) {
        throw (
            "Le paramètre -TypeCandidature vaut " +
            "'$RequestedType', mais le CSV déclare : " +
            "$($declaredTypes -join ', ')."
        )
    }

    return $RequestedType
}


function Add-PipelineResult {
    param(
        # La liste est vide au premier ajout : sans AllowEmptyCollection,
        # PowerShell refuse de la lier au paramètre obligatoire.
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$ResultList,

        [Parameter(Mandatory = $true)]
        [string]$Id,

        [AllowEmptyString()]
        [string]$Intitule,

        [AllowEmptyString()]
        [string]$Entreprise,

        [Parameter(Mandatory = $true)]
        [string]$Statut,

        [AllowEmptyString()]
        [string]$Erreur,

        [Parameter(Mandatory = $true)]
        [string]$ContractType
    )

    $result = [PSCustomObject]@{
        Id                  = $Id
        SourceType          = $SourceType
        TypeCandidature     = $ContractType
        Intitule            = $Intitule
        Entreprise          = $Entreprise
        Statut              = $Statut
        Erreur              = $Erreur
        DateTraitement      = (
            Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        )
    }

    [void]$ResultList.Add(
        $result
    )
}


# ---------------------------------------------------------------------------
# Validation initiale
# ---------------------------------------------------------------------------

try {
    Test-PythonExecutable `
        -Executable $PythonExecutable

    Test-RequiredScript `
        -ScriptPath $TailorCvScript

    Test-RequiredScript `
        -ScriptPath $GenerateLetterScript

    Test-RequiredScript `
        -ScriptPath $RegistreScript

    if (-not $SkipMerge) {
        Test-RequiredScript `
            -ScriptPath $MergeDossierScript
    }

    $ResolvedCsvPath = Resolve-ProjectPath `
        $CsvPath

    $ResolvedRegistrePath = Resolve-ProjectPath `
        $RegistrePath

    $ResolvedExtraDir = Resolve-ProjectPath `
        $ExtraDir

    if (
        -not (
            Test-Path `
                -LiteralPath $ResolvedCsvPath `
                -PathType Leaf
        )
    ) {
        throw "CSV introuvable : $ResolvedCsvPath"
    }

    $offres = @(
        Import-Csv `
            -LiteralPath $ResolvedCsvPath `
            -Encoding UTF8
    )

    if ($offres.Count -eq 0) {
        throw (
            "Le CSV ne contient aucune offre : " +
            "$ResolvedCsvPath"
        )
    }

    $colonnes = @(
        $offres[0].PSObject.Properties.Name
    )

    if ($colonnes -notcontains "id") {
        throw (
            "Le CSV ne contient pas de colonne 'id'. " +
            "Colonnes trouvées : " +
            "$($colonnes -join ', ')"
        )
    }

    if (
        $SourceType -eq "spontaneous" -and
        $colonnes -notcontains "entreprise"
    ) {
        throw (
            "Une candidature spontanée a besoin d'une colonne " +
            "'entreprise'. Colonnes trouvées : " +
            "$($colonnes -join ', ')"
        )
    }

    $ResolvedTypeCandidature = (
        Resolve-TypeCandidature `
            -Rows $offres `
            -RequestedType $TypeCandidature
    )
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}


# ---------------------------------------------------------------------------
# Filtrage par identifiants
# ---------------------------------------------------------------------------

if ($OfferIds -and $OfferIds.Count -gt 0) {
    $normalizedOfferIds = @(
        $OfferIds |
            ForEach-Object {
                if (-not [string]::IsNullOrWhiteSpace($_)) {
                    $_.Trim()
                }
            } |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_)
            }
    )

    $offres = @(
        $offres |
            Where-Object {
                $normalizedOfferIds -contains `
                    ([string]$_.id).Trim()
            }
    )

    if ($offres.Count -eq 0) {
        Write-Error (
            "Aucune offre du CSV ne correspond aux " +
            "identifiants demandés : " +
            "$($normalizedOfferIds -join ', ')"
        )

        exit 1
    }
}


# ---------------------------------------------------------------------------
# Limite du nombre d'offres
# ---------------------------------------------------------------------------

if ($MaxOffers -gt 0) {
    $offres = @(
        $offres |
            Select-Object -First $MaxOffers
    )
}


# ---------------------------------------------------------------------------
# Initialisation du traitement
# ---------------------------------------------------------------------------

$total = $offres.Count

Write-Host ""
Write-Host (
    "============================================================"
) -ForegroundColor Cyan

if ($SourceType -eq "spontaneous") {
    $titrePipeline = "Pipeline de candidatures spontanées"
}
else {
    $titrePipeline = "Pipeline de candidatures sur offres publiées"
}

Write-Host $titrePipeline -ForegroundColor Cyan

Write-Host (
    "============================================================"
) -ForegroundColor Cyan

Write-Host "CSV                : $ResolvedCsvPath"
Write-Host "Source             : $SourceType"
Write-Host "Type de candidature: $ResolvedTypeCandidature"
Write-Host "Offres à examiner  : $total"
Write-Host "Registre           : $ResolvedRegistrePath"

if (-not $SkipMerge) {
    if ($SansAnnexes) {
        Write-Host "Annexes            : désactivées"
    }
    else {
        Write-Host "Dossier annexes    : $ResolvedExtraDir"
    }
}
else {
    Write-Host "Fusion             : ignorée"
}

Write-Host ""

if ($Force) {
    Write-Host (
        "Mode -Force actif : les candidatures déjà " +
        "traitées seront retraitées."
    ) -ForegroundColor DarkYellow
}

if (-not $TraiterNonPrecisees) {
    Write-Host (
        "Les offres sans entreprise précise seront ignorées."
    ) -ForegroundColor DarkYellow
}

if ($PauseTousLesXOffres -gt 0) {
    Write-Host (
        "Pause : $DelaiEntreOffresSec seconde(s) entre les " +
        "traitements et $DureePauseLongueSec seconde(s) " +
        "toutes les $PauseTousLesXOffres candidatures."
    ) -ForegroundColor DarkGray
}
else {
    Write-Host (
        "Pause longue désactivée. " +
        "Pause courte : $DelaiEntreOffresSec seconde(s)."
    ) -ForegroundColor DarkGray
}


$resultats = (
    New-Object `
        "System.Collections.Generic.List[object]"
)

$compteur = 0
$nbIgnoreesRegistre = 0
$nbIgnoreesDoublon = 0
$nbIgnoreesEntreprise = 0
$traitementsReels = 0


# ---------------------------------------------------------------------------
# Traitement des offres
# ---------------------------------------------------------------------------

foreach ($offre in $offres) {
    $compteur++

    $id = ([string]$offre.id).Trim()

    $intitule = ([string]$offre.intitule).Trim()

    $entreprise = Get-NomEntreprise `
        ([string]$offre.entreprise)

    Write-Host ""
    Write-Host (
        "------------------------------------------------------------"
    ) -ForegroundColor DarkGray

    Write-Host (
        "[$compteur/$total] $id : " +
        "$intitule - $entreprise"
    ) -ForegroundColor Yellow

    if ([string]::IsNullOrWhiteSpace($id)) {
        Write-Warning (
            "Ligne ignorée : identifiant vide."
        )

        Add-PipelineResult `
            -ResultList $resultats `
            -Id "" `
            -Intitule $intitule `
            -Entreprise $entreprise `
            -Statut "IGNOREE (identifiant vide)" `
            -Erreur "La colonne id est vide." `
            -ContractType $ResolvedTypeCandidature

        continue
    }

    # -----------------------------------------------------------------------
    # Entreprise inconnue
    # -----------------------------------------------------------------------

    if (
        -not $TraiterNonPrecisees -and
        (
            Test-EntrepriseNonPrecisee `
                $entreprise
        )
    ) {
        Write-Host (
            "[$compteur/$total] IGNORÉE : entreprise non précisée. " +
            "Aucun appel LLM effectué."
        ) -ForegroundColor DarkCyan

        $nbIgnoreesEntreprise++

        Add-PipelineResult `
            -ResultList $resultats `
            -Id $id `
            -Intitule $intitule `
            -Entreprise $entreprise `
            -Statut "IGNOREE (entreprise non precisee)" `
            -Erreur "" `
            -ContractType $ResolvedTypeCandidature

        continue
    }

    # -----------------------------------------------------------------------
    # Vérification du registre
    # -----------------------------------------------------------------------

    if (-not $Force) {
        try {
            $dejaTraitee = (
                Test-CandidatureDejaTraitee `
                    -ApplicationId $id `
                    -RegistryPath $ResolvedRegistrePath `
                    -ContractType $ResolvedTypeCandidature
            )
        }
        catch {
            Write-Warning (
                "[$compteur/$total] ÉCHEC de vérification " +
                "du registre pour '$id' : " +
                "$($_.Exception.Message)"
            )

            Add-PipelineResult `
                -ResultList $resultats `
                -Id $id `
                -Intitule $intitule `
                -Entreprise $entreprise `
                -Statut "ECHEC (registre --check)" `
                -Erreur $_.Exception.Message `
                -ContractType $ResolvedTypeCandidature

            continue
        }

        if ($dejaTraitee) {
            Write-Host (
                "[$compteur/$total] IGNORÉE : candidature " +
                "déjà présente dans le registre."
            ) -ForegroundColor DarkCyan

            $nbIgnoreesRegistre++

            Add-PipelineResult `
                -ResultList $resultats `
                -Id $id `
                -Intitule $intitule `
                -Entreprise $entreprise `
                -Statut "IGNOREE (deja traitee)" `
                -Erreur "" `
                -ContractType $ResolvedTypeCandidature

            continue
        }

        # -------------------------------------------------------------------
        # Même offre déjà préparée depuis une autre source
        # -------------------------------------------------------------------

        $doublon = & $PythonExecutable `
            $CheckDuplicateScript `
            --csv $ResolvedCsvPath `
            --offer-id $id

        if ($LASTEXITCODE -eq 1) {
            Write-Host (
                "[$compteur/$total] IGNORÉE : même offre déjà " +
                "préparée depuis une autre source : $doublon"
            ) -ForegroundColor DarkCyan

            $nbIgnoreesDoublon++

            Add-PipelineResult `
                -ResultList $resultats `
                -Id $id `
                -Intitule $intitule `
                -Entreprise $entreprise `
                -Statut "IGNOREE (doublon autre source)" `
                -Erreur "$doublon" `
                -ContractType $ResolvedTypeCandidature

            continue
        }

        if ($LASTEXITCODE -ne 0) {
            Write-Warning (
                "[$compteur/$total] Vérification des doublons " +
                "impossible pour '$id' : $doublon. L'offre est traitée."
            )
        }
    }

    # À partir d'ici, les scripts LLM vont réellement être appelés.
    $traitementsReels++

    $etapeEnCours = ""

    try {
        # -------------------------------------------------------------------
        # CV
        # -------------------------------------------------------------------

        $etapeEnCours = "tailor_cv.py"

        $tailorArguments = @(
            "--csv",
            $ResolvedCsvPath,

            "--offer-id",
            $id,

            "--source-type",
            $SourceType,

            "--type-candidature",
            $ResolvedTypeCandidature
        )

        Invoke-PythonStep `
            -StepName $etapeEnCours `
            -ScriptPath $TailorCvScript `
            -Arguments $tailorArguments

        # -------------------------------------------------------------------
        # Lettre de motivation
        # -------------------------------------------------------------------

        $etapeEnCours = "generate_letter.py"

        $letterArguments = @(
            "--csv",
            $ResolvedCsvPath,

            "--offer-id",
            $id,

            "--source-type",
            $SourceType,

            "--type-candidature",
            $ResolvedTypeCandidature
        )

        Invoke-PythonStep `
            -StepName $etapeEnCours `
            -ScriptPath $GenerateLetterScript `
            -Arguments $letterArguments

        # -------------------------------------------------------------------
        # Fusion des PDF
        # -------------------------------------------------------------------

        if (-not $SkipMerge) {
            $etapeEnCours = "merge_dossier.py"

            $mergeArguments = @(
                "--application-id",
                $id
            )

            if ($SansAnnexes) {
                $mergeArguments += "--sans-annexes"
            }
            else {
                $mergeArguments += @(
                    "--extra-dir",
                    $ResolvedExtraDir
                )
            }

            Invoke-PythonStep `
                -StepName $etapeEnCours `
                -ScriptPath $MergeDossierScript `
                -Arguments $mergeArguments
        }

        # -------------------------------------------------------------------
        # Ajout au registre
        # -------------------------------------------------------------------

        $etapeEnCours = "registre_offres.py --add"

        Add-CandidatureAuRegistre `
            -ApplicationId $id `
            -RegistryPath $ResolvedRegistrePath `
            -ContractType $ResolvedTypeCandidature

        Write-Host (
            "[$compteur/$total] OK : $id - $entreprise"
        ) -ForegroundColor Green

        Add-PipelineResult `
            -ResultList $resultats `
            -Id $id `
            -Intitule $intitule `
            -Entreprise $entreprise `
            -Statut "OK" `
            -Erreur "" `
            -ContractType $ResolvedTypeCandidature
    }
    catch {
        $errorMessage = $_.Exception.Message

        Write-Warning (
            "[$compteur/$total] ÉCHEC sur '$id' " +
            "à l'étape '$etapeEnCours' : $errorMessage"
        )

        Add-PipelineResult `
            -ResultList $resultats `
            -Id $id `
            -Intitule $intitule `
            -Entreprise $entreprise `
            -Statut "ECHEC ($etapeEnCours)" `
            -Erreur $errorMessage `
            -ContractType $ResolvedTypeCandidature
    }

    # -----------------------------------------------------------------------
    # Pause entre les traitements réels
    # -----------------------------------------------------------------------

    if ($compteur -lt $total) {
        $pauseLongue = (
            $PauseTousLesXOffres -gt 0 -and
            $traitementsReels -gt 0 -and
            (
                $traitementsReels %
                $PauseTousLesXOffres
            ) -eq 0
        )

        if ($pauseLongue) {
            if ($DureePauseLongueSec -gt 0) {
                Write-Host (
                    "`nPause longue de " +
                    "$DureePauseLongueSec seconde(s) " +
                    "après $traitementsReels candidature(s) " +
                    "ayant appelé le LLM..."
                ) -ForegroundColor DarkGray

                Start-Sleep `
                    -Seconds $DureePauseLongueSec
            }
        }
        elseif ($DelaiEntreOffresSec -gt 0) {
            Write-Host (
                "Pause de $DelaiEntreOffresSec seconde(s)..."
            ) -ForegroundColor DarkGray

            Start-Sleep `
                -Seconds $DelaiEntreOffresSec
        }
    }
}


# ---------------------------------------------------------------------------
# Résumé
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host (
    "============================================================"
) -ForegroundColor Cyan

Write-Host "Résumé du pipeline" -ForegroundColor Cyan

Write-Host (
    "============================================================"
) -ForegroundColor Cyan

$resultats |
    Format-Table `
        Id,
        TypeCandidature,
        Intitule,
        Entreprise,
        Statut `
        -AutoSize


$nbOk = @(
    $resultats |
        Where-Object {
            $_.Statut -eq "OK"
        }
).Count

$nbEchec = @(
    $resultats |
        Where-Object {
            $_.Statut -like "ECHEC*"
        }
).Count

$nbIgnoreesTotal = (
    $nbIgnoreesRegistre +
    $nbIgnoreesDoublon +
    $nbIgnoreesEntreprise
)


if ($nbEchec -eq 0) {
    $couleurResume = "Green"
}
else {
    $couleurResume = "Yellow"
}


Write-Host ""

Write-Host (
    "$nbOk candidature(s) traitée(s) avec succès, " +
    "$nbIgnoreesRegistre déjà traitée(s), " +
    "$nbIgnoreesDoublon en double d'une autre source, " +
    "$nbIgnoreesEntreprise sans entreprise précise, " +
    "$nbEchec échec(s), " +
    "sur $total examinée(s)."
) -ForegroundColor $couleurResume


# ---------------------------------------------------------------------------
# Export du résumé
# ---------------------------------------------------------------------------

$csvDirectory = Split-Path `
    $ResolvedCsvPath `
    -Parent

$resumeFilename = (
    "resume_pipeline_" +
    $SourceType +
    "_" +
    $ResolvedTypeCandidature +
    "_" +
    (Get-Date -Format "yyyyMMdd_HHmmss") +
    ".csv"
)

$resumePath = Join-Path `
    $csvDirectory `
    $resumeFilename

try {
    $resultats |
        Export-Csv `
            -LiteralPath $resumePath `
            -NoTypeInformation `
            -Encoding UTF8

    Write-Host ""
    Write-Host (
        "Résumé détaillé : $resumePath"
    ) -ForegroundColor DarkGray
}
catch {
    Write-Warning (
        "Impossible d'enregistrer le résumé CSV : " +
        "$($_.Exception.Message)"
    )
}


Write-Host (
    "Registre : $ResolvedRegistrePath"
) -ForegroundColor DarkGray


# ---------------------------------------------------------------------------
# Code de sortie global
# ---------------------------------------------------------------------------

if ($nbEchec -gt 0) {
    exit 1
}

exit 0