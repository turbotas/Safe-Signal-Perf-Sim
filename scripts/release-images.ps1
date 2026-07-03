param(
    [ValidateSet("patch", "minor", "major")]
    [string]$Bump = "patch",
    [string]$Version,
    [string]$ImageRepo = "safesignal-simulator",
    [string]$ExportDir = "exports",
    [switch]$AllowDirty,
    [switch]$SkipBuild,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

if ($Help) {
    Write-Host "Usage: scripts/release-images.ps1 [-Bump patch|minor|major] [-Version X.Y.Z] [-ImageRepo name] [-ExportDir path] [-AllowDirty]"
    exit 0
}

function Assert-CleanTree {
    $status = git status --porcelain
    if ($status) {
        Fail "Working tree is not clean. Commit/stash changes first, or use -AllowDirty."
    }
}

function Get-LatestVersionTag {
    $tags = git tag --list "v*"
    $parsed = @()
    foreach ($tag in $tags) {
        if ($tag -match '^v(\d+)\.(\d+)\.(\d+)$') {
            $parsed += [PSCustomObject]@{
                Tag = $tag
                Major = [int]$Matches[1]
                Minor = [int]$Matches[2]
                Patch = [int]$Matches[3]
            }
        }
    }
    if (-not $parsed) {
        return "v0.0.0"
    }
    return ($parsed | Sort-Object Major, Minor, Patch | Select-Object -Last 1).Tag
}

function Get-NextVersion([string]$LatestTag, [string]$RequestedBump) {
    if ($LatestTag -notmatch '^v(\d+)\.(\d+)\.(\d+)$') {
        Fail "Invalid latest tag format: $LatestTag"
    }

    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    $patch = [int]$Matches[3]

    switch ($RequestedBump) {
        "major" { $major += 1; $minor = 0; $patch = 0 }
        "minor" { $minor += 1; $patch = 0 }
        "patch" { $patch += 1 }
        default { Fail "Unsupported bump: $RequestedBump" }
    }

    return "$major.$minor.$patch"
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git is not available in PATH"
}

if (-not $SkipBuild -and -not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "docker is not available in PATH"
}

if (-not $AllowDirty) {
    Assert-CleanTree
}

if ($Version) {
    $Version = $Version.TrimStart("v")
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        Fail "Version must match X.Y.Z"
    }
}
else {
    $latestTag = Get-LatestVersionTag
    $Version = Get-NextVersion -LatestTag $latestTag -RequestedBump $Bump
}

$tagName = "v$Version"
$shortSha = (git rev-parse --short HEAD).Trim()
$branch = (git rev-parse --abbrev-ref HEAD).Trim()

if (git tag --list $tagName) {
    Fail "Tag already exists locally: $tagName"
}
if (git ls-remote --tags origin "refs/tags/$tagName") {
    Fail "Tag already exists on origin: $tagName"
}

$versionImage = "${ImageRepo}:$tagName"
$prodImage = "${ImageRepo}:prod"
$shaImage = "${ImageRepo}:sha-$shortSha"

if (-not (Test-Path -LiteralPath $ExportDir)) {
    New-Item -ItemType Directory -Path $ExportDir | Out-Null
}

$tarPath = Join-Path $ExportDir "$ImageRepo-prod-$tagName.tar"
$manifestPath = Join-Path $ExportDir "$ImageRepo-image-$tagName.txt"

if (Test-Path -LiteralPath $tarPath) {
    Fail "Release artifact already exists and will not be overwritten: $tarPath"
}
if (Test-Path -LiteralPath $manifestPath) {
    Fail "Release manifest already exists and will not be overwritten: $manifestPath"
}

if (-not (Test-Path -LiteralPath "Dockerfile")) {
    Fail "Dockerfile not found in repository root."
}
if (-not (Test-Path -LiteralPath "backend/requirements.txt")) {
    Fail "backend/requirements.txt not found in repository root."
}

Write-Host "Branch: $branch"
Write-Host "Commit: $shortSha"
Write-Host "Version: $tagName"
Write-Host "Image (version): $versionImage"
Write-Host "Image (prod): $prodImage"

if (-not $SkipBuild) {
    Write-Host "[INFO] Building release image..."
    docker build --build-arg "APP_VERSION=$tagName" -t $versionImage -t $prodImage -t $shaImage .
    if ($LASTEXITCODE -ne 0) { Fail "Docker build failed." }

    Write-Host "[INFO] Exporting release image tar..."
    docker save -o $tarPath $versionImage
    if ($LASTEXITCODE -ne 0) { Fail "Failed to export release image tar." }
    attrib -h -a $tarPath
}

if (-not (Test-Path -LiteralPath $tarPath)) {
    Fail "Release export not found: $tarPath"
}

$imageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $tarPath).Hash
$imageSize = (Get-Item -LiteralPath $tarPath).Length

@(
    "tag=$tagName"
    "branch=$branch"
    "commit=$shortSha"
    "version_image=$versionImage"
    "prod_image=$prodImage"
    "sha_image=$shaImage"
    "tar=$tarPath"
    "size_bytes=$imageSize"
    "sha256=$imageHash"
) | Set-Content -LiteralPath $manifestPath -Encoding ascii

attrib -h -a $manifestPath

git tag -a $tagName -m "Release $tagName"
git push origin $tagName

Write-Host "TAR: $tarPath"
Write-Host "SHA256: $imageHash"
Write-Host "Manifest: $manifestPath"
