# Lance ce script pour diagnostiquer pourquoi le registre semble se vider.
# Colle-moi TOUTE la sortie, meme si certaines lignes te semblent inutiles.

Write-Host "=== 1. Le fichier existe-t-il reellement sur le disque ? ===" -ForegroundColor Cyan
Test-Path "data\offres_traitees.csv"

Write-Host "`n=== 2. Contenu BRUT du fichier (sans passer par Python) ===" -ForegroundColor Cyan
if (Test-Path "data\offres_traitees.csv") {
    Get-Content "data\offres_traitees.csv" -Raw
    Write-Host "`nTaille du fichier (octets) :" -ForegroundColor DarkGray
    (Get-Item "data\offres_traitees.csv").Length
}
else {
    Write-Host "LE FICHIER N'EXISTE PAS DU TOUT." -ForegroundColor Red
}

Write-Host "`n=== 3. Y a-t-il plusieurs copies de registre_offres.py sur le disque ? ===" -ForegroundColor Cyan
Get-ChildItem -Path . -Recurse -Filter "registre_offres.py" -ErrorAction SilentlyContinue | Select-Object FullName, LastWriteTime

Write-Host "`n=== 4. Quel 'python' est reellement utilise ? ===" -ForegroundColor Cyan
Get-Command python | Select-Object Source
python --version

Write-Host "`n=== 5. Chemin absolu calcule par le script lui-meme ===" -ForegroundColor Cyan
python -c "from pathlib import Path; import sys; sys.path.insert(0, 'src'); import registre_offres as r; print('BASE_DIR =', r.BASE_DIR); print('REGISTRE_PATH_DEFAUT =', r.REGISTRE_PATH_DEFAUT); print('Existe :', r.REGISTRE_PATH_DEFAUT.exists())"
