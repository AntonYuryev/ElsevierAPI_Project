# Sync script for ElsevierAPI from GitHub
# This script synchronizes the local ElsevierAPI directory with the GitHub repository
# GitHub structure: https://github.com/AntonYuryev/ElsevierAPI/tree/main/ElsevierAPI
# Local structure: D:\Python\ENTELLECT_API_SCRIPTS\SCRIPTS\ElsevierAPI (root level)

Write-Host "Synchronizing ElsevierAPI from GitHub..." -ForegroundColor Cyan

# Fetch latest changes from remote
Write-Host "`nFetching from origin/main..." -ForegroundColor Yellow
git fetch origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error fetching from remote. Please check your connection." -ForegroundColor Red
    exit 1
}

# Create a temporary directory for the sync
$tempDir = ".\__temp_sync__"
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}

# Checkout the ElsevierAPI subdirectory from remote to temp location
Write-Host "`nChecking out ElsevierAPI subdirectory from remote..." -ForegroundColor Yellow
git checkout origin/main -- ElsevierAPI/

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error checking out from remote." -ForegroundColor Red
    exit 1
}

# Copy files from ElsevierAPI/ to root, excluding files in .gitignore
Write-Host "`nSyncing files (preserving local config and credentials)..." -ForegroundColor Yellow
Copy-Item -Path .\ElsevierAPI\* -Destination . -Recurse -Force -Exclude "APIconfig.json"

# Remove the temporary ElsevierAPI directory
Remove-Item -Path .\ElsevierAPI -Recurse -Force

# Show status
Write-Host "`nChanges detected:" -ForegroundColor Yellow
git status --short

# Ask if user wants to commit
Write-Host "`nDo you want to commit these changes? (Y/N): " -ForegroundColor Cyan -NoNewline
$commit = Read-Host

if ($commit -eq "Y" -or $commit -eq "y") {
    $date = Get-Date -Format "yyyy-MM-dd HH:mm"
    git add -A
    git commit -m "Sync from GitHub ElsevierAPI - $date"
    Write-Host "`nSync completed and committed!" -ForegroundColor Green
} else {
    Write-Host "`nSync completed but not committed. Review changes with 'git status'" -ForegroundColor Yellow
}

Write-Host "`nNote: Your local config/ directory and APIconfig.json were preserved." -ForegroundColor Cyan
