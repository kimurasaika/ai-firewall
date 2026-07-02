<#
.SYNOPSIS
    Generates the CA and all mTLS / Redis TLS certificates for AI Firewall,
    using `docker run alpine/openssl` (no local openssl install required).

.DESCRIPTION
    Recreates certs/ from scratch:
      - certs/ca.key, certs/ca.crt              (root CA, /CN=DLP-CA)
      - certs/mtls/<service>.key/.crt            (one per internal service, CA-signed)
      - certs/redis/redis.key/.crt                (redis server cert, CA-signed)
      - certs/redis/client.key/.crt               (redis client cert, CA-signed)

    Any existing certs/ directory is moved aside to certs.backup.<timestamp>
    before regenerating, so nothing is deleted outright.

.PARAMETER Force
    Skip the confirmation prompt before backing up an existing certs/ directory.

.EXAMPLE
    ./scripts/generate_certs.ps1
    ./scripts/generate_certs.ps1 -Force
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$OpenSslImage = 'alpine/openssl'
$MtlsServices = @(
    'orchestrator',
    'proxy',
    'dashboard_api',
    'deanonymizer',
    'text_worker',
    'ocr_worker',
    'file_worker',
    'domain_updater'
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$CertsDir = Join-Path $RepoRoot 'certs'
$MtlsDir  = Join-Path $CertsDir 'mtls'
$RedisDir = Join-Path $CertsDir 'redis'

function Invoke-Docker {
    param([Parameter(Mandatory)][string[]]$DockerArgs)
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker $($DockerArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function New-CaCert {
    Write-Host "Generating root CA (/CN=DLP-CA) ..." -ForegroundColor Cyan
    Invoke-Docker @(
        'run', '--rm',
        '-v', "${CertsDir}:/certs",
        $OpenSslImage,
        'req', '-x509', '-newkey', 'rsa:4096',
        '-keyout', '/certs/ca.key',
        '-out', '/certs/ca.crt',
        '-days', '3650', '-nodes',
        '-subj', '/CN=DLP-CA'
    )
}

function New-SignedCert {
    param(
        [Parameter(Mandatory)][string]$CommonName,
        [Parameter(Mandatory)][string]$OutDirContainer,
        [Parameter(Mandatory)][string]$FileBaseName
    )
    Write-Host "Generating cert for CN=$CommonName ..." -ForegroundColor Cyan
    $shCmd = "openssl req -newkey rsa:2048 " +
             "-keyout $OutDirContainer/$FileBaseName.key " +
             "-out /tmp/$FileBaseName.csr -nodes -subj '/CN=$CommonName' && " +
             "openssl x509 -req -in /tmp/$FileBaseName.csr " +
             "-CA /certs/ca.crt -CAkey /certs/ca.key -CAcreateserial " +
             "-out $OutDirContainer/$FileBaseName.crt -days 3650"

    Invoke-Docker @(
        'run', '--rm',
        '--entrypoint', 'sh',
        '-v', "${CertsDir}:/certs",
        $OpenSslImage,
        '-c', $shCmd
    )
}

function Test-DockerAvailable {
    $null = & docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker does not appear to be running. Start Docker Desktop and try again."
    }
}

# --- Preflight ---------------------------------------------------------
Test-DockerAvailable

if (Test-Path $CertsDir) {
    $existing = Get-ChildItem -Path $CertsDir -Recurse -File -ErrorAction SilentlyContinue
    if ($existing.Count -gt 0) {
        Write-Host "Existing certs/ directory found ($($existing.Count) file(s))." -ForegroundColor Yellow
        if (-not $Force) {
            $answer = Read-Host "Back it up and regenerate everything? [y/N]"
            if ($answer -notmatch '^[Yy]') {
                Write-Host "Aborted. No changes made." -ForegroundColor Yellow
                exit 0
            }
        }
        $backupDir = Join-Path $RepoRoot ("certs.backup." + (Get-Date -Format 'yyyyMMddHHmmss'))
        Write-Host "Backing up certs/ -> $backupDir" -ForegroundColor Yellow
        Move-Item -Path $CertsDir -Destination $backupDir
    }
}

New-Item -ItemType Directory -Force -Path $MtlsDir  | Out-Null
New-Item -ItemType Directory -Force -Path $RedisDir | Out-Null

# --- Pull image once so per-cert docker run calls are fast -------------
Write-Host "Pulling $OpenSslImage ..." -ForegroundColor Cyan
Invoke-Docker @('pull', $OpenSslImage)

# --- CA ------------------------------------------------------------------
New-CaCert

# --- Per-service mTLS certs ----------------------------------------------
foreach ($svc in $MtlsServices) {
    New-SignedCert -CommonName $svc -OutDirContainer '/certs/mtls' -FileBaseName $svc
}

# --- Redis server + client certs -----------------------------------------
New-SignedCert -CommonName 'redis'        -OutDirContainer '/certs/redis' -FileBaseName 'redis'
New-SignedCert -CommonName 'redis-client' -OutDirContainer '/certs/redis' -FileBaseName 'client'

# --- Verify ----------------------------------------------------------------
Write-Host "`nVerifying generated certificates:" -ForegroundColor Cyan
$allCerts = @(Join-Path $CertsDir 'ca.crt')
$allCerts += $MtlsServices | ForEach-Object { Join-Path $MtlsDir "$_.crt" }
$allCerts += (Join-Path $RedisDir 'redis.crt'), (Join-Path $RedisDir 'client.crt')

foreach ($certPath in $allCerts) {
    $relPath = $certPath.Substring($CertsDir.Length + 1) -replace '\\', '/'
    & docker run --rm -v "${CertsDir}:/certs" $OpenSslImage `
        x509 -in "/certs/$relPath" -noout -subject -issuer -dates
}

Write-Host "`nAll certificates generated under $CertsDir" -ForegroundColor Green
