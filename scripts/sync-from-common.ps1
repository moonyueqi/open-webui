# sync-from-common.ps1
#
# Sync latest changes from origin/common into the current deployment branch
# (dev-bj or dev-sz).
#
# Branch model:
#   common  - shared features / UI changes for both deployments
#   dev-bj  - common + Beijing-specific brand (logo, name, system prompt, ...)
#   dev-sz  - common + Suzhou-specific brand
#
# Daily workflow:
#   1) Write feature / UI change:
#        git checkout common
#        ... edit, commit, push ...
#   2) Pull it into a deployment branch:
#        # in a dev-bj or dev-sz worktree
#        .\scripts\sync-from-common.ps1
#
# Conflict rules (rare, only if you accidentally edit brand-only files on common):
#   - APP_NAME / WEBUI_NAME / page title / METEO_SYSTEM_PROMPT  => keep ours
#   - logo / favicon / splash / web-app-manifest images         => keep ours
#   - everything else                                           => prefer theirs
#   then:  git add <files>; git merge --continue; git push origin <branch>

$ErrorActionPreference = 'Stop'

$repoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] not inside a git repository' -ForegroundColor Red
    exit 1
}
Set-Location $repoRoot

$current = (git rev-parse --abbrev-ref HEAD).Trim()
if ($current -ne 'dev-bj' -and $current -ne 'dev-sz') {
    Write-Host "[ERROR] current branch is '$current'" -ForegroundColor Red
    Write-Host '        This script must be run on dev-bj or dev-sz.' -ForegroundColor Red
    Write-Host '        To update common itself: git checkout common; git pull' -ForegroundColor Yellow
    exit 1
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Host '[ERROR] working tree is not clean. Commit or stash first:' -ForegroundColor Red
    Write-Host $dirty
    exit 1
}

Write-Host "[1/2] git fetch origin ..." -ForegroundColor Cyan
git fetch origin
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "[2/2] merging origin/common into $current ..." -ForegroundColor Cyan
git merge origin/common --no-edit
$mergeExit = $LASTEXITCODE

if ($mergeExit -ne 0) {
    Write-Host ''
    Write-Host '[!] Merge conflicts. Resolve with these rules:' -ForegroundColor Yellow
    Write-Host '    - brand strings (APP_NAME / WEBUI_NAME / page title / METEO_SYSTEM_PROMPT)'
    Write-Host '        -> keep ours:   git checkout --ours <file>'
    Write-Host '    - brand images (logo / favicon / splash / web-app-manifest)'
    Write-Host '        -> keep ours:   git checkout --ours <file>'
    Write-Host '    - other business code'
    Write-Host '        -> prefer theirs, merge manually as needed'
    Write-Host ''
    Write-Host '    Then:'
    Write-Host '      git add <files>'
    Write-Host '      git merge --continue'
    Write-Host "      git push origin $current"
    exit 1
}

Write-Host ''
Write-Host "[OK] merged origin/common into $current" -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Cyan
Write-Host '  1) verify locally:  npm run build (frontend) or restart backend'
Write-Host "  2) if OK:           git push origin $current"
