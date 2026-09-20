<#
.SYNOPSIS
    Enchaine automatiquement, pour chaque offre d'un CSV filtre :
      0. registre_offres.py --check  (ignore l'offre si deja traitee lors d'un run precedent)
      1. tailor_cv.py                (genere le CV adapte)
      2. generate_letter.py          (genere la lettre de motivation, basee sur le CV genere)
      3. merge_dossier.py            (fusionne CV + LM + documents annexes en PDF finaux)
      4. registre_offres.py --add    (enregistre l'offre comme traitee, SEULEMENT si tout a reussi)

    Inclut un espacement automatique entre les offres (et une pause plus longue
    tous les N offres) pour eviter de saturer l'API du LLM (erreurs 429 "trop de
    requetes") lors d'un traitement en lot de plusieurs dizaines de candidatures.
    .\run_pipeline.ps1 -CsvPath "data\offres_filtrees\2026-09-10\offres_filtrees_2026-09-10_203158.csv" -PauseTousLesXOffres 3 -DureePauseLongueSec 30    

.PARAMETER CsvPath
    Chemin vers le CSV des offres filtrees (doit contenir une colonne "id").

.PARAMETER OfferIds
    (Optionnel) Liste explicite d'IDs a traiter, au lieu de tout le CSV.

.PARAMETER MaxOffers
    (Optionnel) Limite le nombre d'offres traitees (0 = toutes).

.PARAMETER SkipMerge
    (Optionnel) Si present, n'execute pas merge_dossier.py (juste CV + lettre).

.PARAMETER Force
    (Optionnel) Retraite meme les offres deja presentes dans le registre.

.PARAMETER RegistrePath
    (Optionnel) Chemin du registre des offres deja traitees. Defaut : data\offres_traitees.csv

.PARAMETER DelaiEntreOffresSec
    (Optionnel) Pause en secondes entre deux offres traitees (celles qui appellent
    reellement le LLM, pas les ignorees). Defaut : 4 secondes.

.PARAMETER PauseTousLesXOffres
    (Optionnel) Frequence de la pause longue : une pause plus importante est
    inseree toutes les X offres reellement traitees, pour laisser l'API respirer
    sur un gros lot. Defaut : 3.

.PARAMETER DureePauseLongueSec
    (Optionnel) Duree de la pause longue, en secondes. Defaut : 30 secondes.

.EXAMPLE
    .\run_pipeline.ps1 -CsvPath "data\offres_filtrees\2026-09-10\offres_filtrees_2026-09-10_125748.csv"

.EXAMPLE
    # Lot de 20 offres, pause de 45s toutes les 3 offres au lieu des reglages par defaut
    .\run_pipeline.ps1 -CsvPath "data\offres_filtrees\...\....csv" -PauseTousLesXOffres 3 -DureePauseLongueSec 45
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath,

    [string[]]$OfferIds,

    [int]$MaxOffers = 0,

    [switch]$SkipMerge,

    [switch]$Force,

    [string]$RegistrePath = "data\offres_traitees.csv",

    [int]$DelaiEntreOffresSec = 4,

    [int]$PauseTousLesXOffres = 3,

    [int]$DureePauseLongueSec = 30
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $CsvPath)) {
    Write-Error "CSV introuvable : $CsvPath"
    exit 1
}

# Le CSV est produit par le pipeline de scraping/filtrage, en UTF-8.
$offres = Import-Csv -Path $CsvPath -Encoding UTF8

if (-not $offres -or -not ($offres[0].PSObject.Properties.Name -contains "id")) {
    Write-Error "Le CSV ne contient pas de colonne 'id'. Colonnes trouvees : $($offres[0].PSObject.Properties.Name -join ', ')"
    exit 1
}

if ($OfferIds) {
    $offres = $offres | Where-Object { $OfferIds -contains $_.id }
    if (-not $offres) {
        Write-Error "Aucune offre du CSV ne correspond aux IDs fournis : $($OfferIds -join ', ')"
        exit 1
    }
}

if ($MaxOffers -gt 0) {
    $offres = $offres | Select-Object -First $MaxOffers
}

$total = $offres.Count
Write-Host "`n=== Pipeline candidatures : $total offre(s) a examiner ===`n" -ForegroundColor Cyan
Write-Host "Espacement : $DelaiEntreOffresSec s entre chaque offre traitee, pause de $DureePauseLongueSec s toutes les $PauseTousLesXOffres offres.`n" -ForegroundColor DarkGray
if ($Force) {
    Write-Host "(mode -Force actif : les offres deja traitees seront retraitees quand meme)`n" -ForegroundColor DarkYellow
}

$resultats = @()
$compteur = 0
$nbIgnorees = 0
$traitementsReels = 0

foreach ($offre in $offres) {
    $compteur++
    $id = $offre.id
    $intitule = $offre.intitule
    $entreprise = $offre.entreprise

    Write-Host "----------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "[$compteur/$total] Offre $id : $intitule - $entreprise" -ForegroundColor Yellow

    # --- Etape 0 : verification du registre (deja traitee ?) ---
    if (-not $Force) {
        python src\registre_offres.py --check "$id" --registre "$RegistrePath" | Out-Null
        $dejaTraitee = ($LASTEXITCODE -eq 1)

        if ($dejaTraitee) {
            Write-Host "[$compteur/$total] IGNOREE : offre $id deja traitee (presente dans le registre)." -ForegroundColor DarkCyan
            $nbIgnorees++
            $resultats += [PSCustomObject]@{
                Id         = $id
                Intitule   = $intitule
                Entreprise = $entreprise
                Statut     = "IGNOREE (deja traitee)"
                Erreur     = ""
            }
            continue
        }
    }

    $etapeEnCours = "tailor_cv.py"
    try {
        python src\tailor_cv.py --csv "$CsvPath" --offer-id "$id"
        if ($LASTEXITCODE -ne 0) { throw "$etapeEnCours a echoue (code $LASTEXITCODE)" }

        $etapeEnCours = "generate_letter.py"
        python src\generate_letter.py --offer-id "$id"
        if ($LASTEXITCODE -ne 0) { throw "$etapeEnCours a echoue (code $LASTEXITCODE)" }

        if (-not $SkipMerge) {
            $etapeEnCours = "merge_dossier.py"
            python src\merge_dossier.py --offer-id "$id"
            if ($LASTEXITCODE -ne 0) { throw "$etapeEnCours a echoue (code $LASTEXITCODE)" }
        }

        # --- Etape finale : on enregistre l'offre comme traitee UNIQUEMENT si tout a reussi ---
        $etapeEnCours = "registre_offres.py --add"
        python src\registre_offres.py --add "$id" --registre "$RegistrePath" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "$etapeEnCours a echoue (code $LASTEXITCODE)" }

        Write-Host "[$compteur/$total] OK : $id (ajoutee au registre)" -ForegroundColor Green
        $resultats += [PSCustomObject]@{
            Id         = $id
            Intitule   = $intitule
            Entreprise = $entreprise
            Statut     = "OK"
            Erreur     = ""
        }
    }
    catch {
        Write-Warning "[$compteur/$total] ECHEC sur $id a l'etape '$etapeEnCours' : $($_.Exception.Message)"
        $resultats += [PSCustomObject]@{
            Id         = $id
            Intitule   = $intitule
            Entreprise = $entreprise
            Statut     = "ECHEC ($etapeEnCours)"
            Erreur     = $_.Exception.Message
        }
    }

    # --- Espacement entre offres : uniquement pour celles qui ont reellement
    # appele le LLM (pas les ignorees), et seulement s'il reste des offres a traiter. ---
    $traitementsReels++

    if ($compteur -lt $total) {
        if ($traitementsReels % $PauseTousLesXOffres -eq 0) {
            Write-Host "`nPause de $DureePauseLongueSec s (toutes les $PauseTousLesXOffres offres) pour menager l'API..." -ForegroundColor DarkGray
            Start-Sleep -Seconds $DureePauseLongueSec
        }
        else {
            Start-Sleep -Seconds $DelaiEntreOffresSec
        }
    }
}

Write-Host "`n=== Resume ===`n" -ForegroundColor Cyan
$resultats | Format-Table -AutoSize

$nbOk = ($resultats | Where-Object { $_.Statut -eq "OK" }).Count
$nbEchec = ($resultats | Where-Object { $_.Statut -like "ECHEC*" }).Count
$couleurResume = "Yellow"
if ($nbEchec -eq 0) { $couleurResume = "Green" }

Write-Host "`n$nbOk offre(s) traitee(s) avec succes, $nbIgnorees deja traitee(s) (ignoree(s)), $nbEchec echec(s), sur $total examinee(s)." -ForegroundColor $couleurResume
if ($nbEchec -gt 0) {
    Write-Host "$nbEchec echec(s) - voir le detail ci-dessus." -ForegroundColor Red
}

# Sauvegarde le resume en CSV pour reference, a cote du CSV source
$resumePath = Join-Path (Split-Path $CsvPath -Parent) "resume_pipeline_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv"
$resultats | Export-Csv -Path $resumePath -NoTypeInformation -Encoding UTF8
Write-Host "`nResume detaille sauvegarde dans : $resumePath" -ForegroundColor DarkGray
Write-Host "Registre des offres traitees : $RegistrePath" -ForegroundColor DarkGray