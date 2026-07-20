# Pack fengche/tool_server + fengche/warning_server into a deploy zip.
#
# Usage (run from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\pack_fengche.ps1
#
# Output: dist\fengche_deploy_<timestamp>.zip
#
# Source layout (in repo):
#   sz_tools/fengche/
#     ├── deploy/
#     │   ├── docker-compose.yml
#     │   ├── .env.example
#     │   └── DEPLOY.md
#     ├── tool_server/
#     └── warning_server/
#
# Zip layout (server-side, keeps the historical name fengche_deploy/):
#   fengche_deploy/
#     ├── docker-compose.fengche.yml      (renamed from deploy/docker-compose.yml)
#     ├── .env.fengche.example            (renamed from deploy/.env.example)
#     ├── DEPLOY_FENGCHE.md               (renamed from deploy/DEPLOY.md)
#     ├── fengche_tool_server/            (renamed from tool_server/)
#     └── fengche_warning_server/         (renamed from warning_server/)
#
# Excluded: __pycache__, .venv, .env*, demo_sample_output.*, data_samples/, shp_raw/, etc.

[CmdletBinding()]
param(
    [string] $OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $RepoRoot

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Stage = Join-Path $RepoRoot "$OutputDir\fengche_deploy_staging_$Timestamp"
$ZipPath = Join-Path $RepoRoot "$OutputDir\fengche_deploy_$Timestamp.zip"

if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $ZipPath) | Out-Null

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==> Staging at $Stage" -ForegroundColor Cyan

function Copy-WithExcludes {
    param(
        [string] $Source,
        [string] $Dest,
        [string[]] $Excludes
    )
    if (-not (Test-Path $Source)) { return }
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Get-ChildItem -Path $Source -Recurse -Force | ForEach-Object {
        $relPath = $_.FullName.Substring($Source.Length).TrimStart('\','/')
        $skip = $false
        foreach ($pat in $Excludes) {
            if ($relPath -like $pat -or $_.Name -like $pat) {
                $skip = $true
                break
            }
        }
        if ($skip) { return }
        $target = Join-Path $Dest $relPath
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $target | Out-Null
        } else {
            $parent = Split-Path $target
            if (-not (Test-Path $parent)) {
                New-Item -ItemType Directory -Force -Path $parent | Out-Null
            }
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

$commonExcludes = @(
    "__pycache__", "*.pyc", "*.pyo", "*.pyd",
    ".venv", "venv", ".pytest_cache",
    ".env", ".env.local", "*.log",
    "demo_sample_output.json", "demo_sample_output.txt"
)

Write-Host "==> Copy fengche/tool_server -> fengche_tool_server" -ForegroundColor Green
Copy-WithExcludes -Source (Join-Path $RepoRoot "sz_tools\fengche\tool_server") `
                  -Dest   (Join-Path $Stage    "fengche_tool_server") `
                  -Excludes $commonExcludes

Write-Host "==> Copy fengche/warning_server -> fengche_warning_server" -ForegroundColor Green
Copy-WithExcludes -Source (Join-Path $RepoRoot "sz_tools\fengche\warning_server") `
                  -Dest   (Join-Path $Stage    "fengche_warning_server") `
                  -Excludes $commonExcludes

Write-Host "==> Copy deploy files (rename to historical names so server-side commands stay unchanged)" -ForegroundColor Green
# 仓库内（移动后） -> zip 内（保持老命名，部署文档不用改）
$deployFiles = @{
    "sz_tools\fengche\deploy\docker-compose.yml" = "docker-compose.fengche.yml"
    "sz_tools\fengche\deploy\.env.example"       = ".env.fengche.example"
    "sz_tools\fengche\deploy\DEPLOY.md"          = "DEPLOY_FENGCHE.md"
}
foreach ($srcRel in $deployFiles.Keys) {
    $src = Join-Path $RepoRoot $srcRel
    $dstName = $deployFiles[$srcRel]
    if (Test-Path $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $Stage $dstName) -Force
    } else {
        Write-Warning "missing: $srcRel (skipped)"
    }
}

# zip 内的 docker-compose.fengche.yml 里 context 是 `..`，但部署目录里
# 没有上层（因为 zip 解压出来就是 fengche_deploy/ 这一层），所以要把 context 改成 `.`，
# dockerfile 路径相应改回 fengche_tool_server/Dockerfile / fengche_warning_server/Dockerfile，
# 同时 Dockerfile 内 COPY 的目录前缀也要改成 fengche_tool_server / fengche_warning_server。
Write-Host "==> Patch staged docker-compose & Dockerfiles for flat deploy layout" -ForegroundColor Green
$composeStaged = Join-Path $Stage "docker-compose.fengche.yml"
(Get-Content -LiteralPath $composeStaged -Raw) `
    -replace 'context:\s*\.\.', 'context: .' `
    -replace 'dockerfile:\s*tool_server/Dockerfile', 'dockerfile: fengche_tool_server/Dockerfile' `
    -replace 'dockerfile:\s*warning_server/Dockerfile', 'dockerfile: fengche_warning_server/Dockerfile' `
    -replace '- \.env\b', '- .env.fengche' `
    | Set-Content -LiteralPath $composeStaged -Encoding UTF8

$toolDockerStaged = Join-Path $Stage "fengche_tool_server\Dockerfile"
(Get-Content -LiteralPath $toolDockerStaged -Raw) `
    -replace 'COPY tool_server/', 'COPY fengche_tool_server/' `
    | Set-Content -LiteralPath $toolDockerStaged -Encoding UTF8

$warnDockerStaged = Join-Path $Stage "fengche_warning_server\Dockerfile"
(Get-Content -LiteralPath $warnDockerStaged -Raw) `
    -replace 'COPY tool_server/', 'COPY fengche_tool_server/' `
    -replace 'COPY warning_server/', 'COPY fengche_warning_server/' `
    | Set-Content -LiteralPath $warnDockerStaged -Encoding UTF8

# Rename staging top dir to fengche_deploy so the zip extracts to that name
$Final = Join-Path (Split-Path $Stage) "fengche_deploy"
if (Test-Path $Final) { Remove-Item -Recurse -Force $Final }
Rename-Item -LiteralPath $Stage -NewName "fengche_deploy"

Write-Host "==> Compress to $ZipPath" -ForegroundColor Cyan
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path $Final -DestinationPath $ZipPath -CompressionLevel Optimal

Remove-Item -Recurse -Force $Final

$sizeMB = "{0:N2}" -f ((Get-Item $ZipPath).Length / 1MB)
Write-Host ""
Write-Host "==> DONE" -ForegroundColor Yellow
Write-Host "    zip:  $ZipPath"
Write-Host "    size: $sizeMB MB"
Write-Host ""
Write-Host "Upload the zip to the server and follow DEPLOY_FENGCHE.md." -ForegroundColor Yellow
