# release.ps1 - Creates and pushes a version tag based on Main.py VERSION and commit count.

function Exit-Script {
    param([string]$Message, [string]$Color = "Red", [int]$ExitCode = 1)
    Write-Host "Error: $Message" -ForegroundColor $Color
    # Ensure we are in the original location if Push-Location succeeded but the script failed later
    if ($initialLocation -and (Get-Location).Path -ne $initialLocation.Path) {
        try { Pop-Location -ErrorAction Stop } catch { Write-Host "Warning: Failed to Pop-Location." -ForegroundColor Yellow }
    }
    pause
    exit $ExitCode
}

# --- Script Setup ---
$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
$initialLocation = Get-Location # Store initial location for Exit-Script robustness
Push-Location $scriptDir

# --- Read Version ---
$mainPyPath = "Main.py"
$mainPyContent = Get-Content -Path $mainPyPath -ErrorAction SilentlyContinue
if (-not $mainPyContent) { Exit-Script "'$mainPyPath' not found." }
$majorMinorVersion = ($mainPyContent | Select-String -Pattern 'VERSION = "([0-9]+\.[0-9]+)"').Matches.Groups[1].Value
if (-not $majorMinorVersion) { Exit-Script "Could not find VERSION = \"x.y\" in '$mainPyPath'" }
Write-Host "Base Version: $majorMinorVersion"

# --- Sync and Get Commit Count ---
$mainBranch = "main" # <<< CHANGE THIS if your main branch is different
Write-Host "Pulling latest changes from origin/$mainBranch..."
git pull origin $mainBranch
if ($LASTEXITCODE -ne 0) { Write-Host "Warning: 'git pull origin $mainBranch' failed. Commit count might be inaccurate." -ForegroundColor Yellow }

$commitCount = git rev-list --count HEAD
if ($LASTEXITCODE -ne 0) { Exit-Script "Failed to get commit count. Is this a git repository?" }

# --- Calculate Tag and Validate ---
$tagName = "v$majorMinorVersion.$commitCount"
Write-Host "Proposed Tag: $tagName"
if (git tag -l $tagName) { Exit-Script "Tag '$tagName' already exists locally." }
if (git ls-remote --tags origin refs/tags/$tagName) { Exit-Script "Tag '$tagName' already exists remotely." }

# --- Create and Push Tag ---
Write-Host "Creating tag '$tagName'..."
git tag -a "$tagName" -m "Release $tagName"
if ($LASTEXITCODE -ne 0) { Exit-Script "Failed to create tag '$tagName'." }

Write-Host "Pushing tag '$tagName'..."
git push origin "$tagName"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: Failed push. Attempting to delete local tag '$tagName'..." -ForegroundColor Yellow
    git tag -d $tagName # Attempt cleanup
    Exit-Script "Failed to push tag '$tagName'. Manually check remote and local state."
}

# --- Find and Open GitHub Actions Run ---
Write-Host ""
Write-Host "Tag '$tagName' pushed successfully! Attempting to find GitHub Actions run..." -ForegroundColor Green
$repoFullName = "rainlizard/ImagesToVideoSlideshow" # <<< CHANGE THIS
$finalUrl = $null
$waitTimeSeconds = 5
$maxAttempts = 6 # Try for 30 seconds (6 attempts * 5 seconds)

if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "GitHub CLI ('gh') found. Attempting to fetch specific run URL..."
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        Write-Host "Attempt $attempt/${maxAttempts}: Waiting ${waitTimeSeconds} seconds..."
        Start-Sleep -Seconds $waitTimeSeconds
        $runId = gh run list --repo $repoFullName --event push --branch $tagName --limit 1 --json databaseId --jq ".[0].databaseId" -ErrorAction SilentlyContinue
        if ($LASTEXITCODE -eq 0 -and $runId -match '^\d+$') {
            Write-Host "Found run ID: $runId" -ForegroundColor Cyan
            $finalUrl = "https://github.com/$repoFullName/actions/runs/$runId"
            break
        } elseif ($attempt -eq $maxAttempts) {
            Write-Host "Max attempts reached. Could not find specific run ID via gh." -ForegroundColor Yellow
        } else {
             Write-Host "Run not found yet or 'gh' command failed."
        }
    }
} else {
    Write-Host "GitHub CLI ('gh') not found. Cannot fetch specific run URL." -ForegroundColor Yellow
    Write-Host "Waiting $waitTimeSeconds seconds before opening the filtered Actions page..."
    Start-Sleep -Seconds $waitTimeSeconds
}

# Determine fallback URL if needed
if (-not $finalUrl) {
    $encodedTagName = [System.Uri]::EscapeDataString($tagName)
    $finalUrl = "https://github.com/$repoFullName/actions?query=workflow_run:branch:refs/tags/$encodedTagName"
    Write-Host "Falling back to filtered Actions page."
}

# --- Open URL and Exit ---
Write-Host "Opening URL: $finalUrl ..."
Start-Process $finalUrl

Pop-Location
pause
exit 0