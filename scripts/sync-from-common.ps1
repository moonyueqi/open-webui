<#
.SYNOPSIS
    把 origin/common 上的最新改动同步到当前部署分支 (dev-bj 或 dev-sz)。

.DESCRIPTION
    本仓库采用 "common + dev-bj/dev-sz" 的分支模式：
      common  ← 两个部署共用的功能/UI 改动
      dev-bj  ← common 之上叠加北京专属品牌 (logo/名称/系统提示词等)
      dev-sz  ← common 之上叠加苏州专属品牌

    日常开发流程：
      1) 写功能 / 改 UI:  切到 common, 编码, commit, push
      2) 部署分支同步:    在 dev-bj 或 dev-sz 的 worktree 里跑本脚本即可

    脚本会:
      - 校验当前分支必须是 dev-bj 或 dev-sz
      - 校验工作区干净 (避免脏目录 merge 出意外)
      - fetch origin
      - 把 origin/common merge 进当前分支
      - 如果有冲突, 给出"品牌字段保 ours, 其他保 theirs"的提示

.EXAMPLE
    # 在 D:\Dev Project\open-webui 或 D:\Dev Project\open-webui-sz 任一目录下:
    PS> .\scripts\sync-from-common.ps1
#>

$ErrorActionPreference = 'Stop'

# 切到脚本所在仓库根目录 (避免在其他目录里跑出错)
$RepoRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERR] 当前目录不是 git 仓库" -ForegroundColor Red
    exit 1
}
Set-Location $RepoRoot

# 1. 校验分支
$current = (git rev-parse --abbrev-ref HEAD).Trim()
if ($current -ne 'dev-bj' -and $current -ne 'dev-sz') {
    Write-Host "[ERR] 当前分支是 '$current', 本脚本只允许在 dev-bj 或 dev-sz 上运行" -ForegroundColor Red
    Write-Host "      如果你想更新 common 本身, 请直接: git checkout common; git pull" -ForegroundColor Yellow
    exit 1
}

# 2. 校验干净
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "[ERR] 工作区不干净, 请先 commit 或 stash:" -ForegroundColor Red
    Write-Host $dirty
    exit 1
}

# 3. fetch
Write-Host "[1/3] git fetch origin ..." -ForegroundColor Cyan
git fetch origin
if ($LASTEXITCODE -ne 0) { exit 1 }

# 4. merge
Write-Host "[2/3] merging origin/common into $current ..." -ForegroundColor Cyan
git merge origin/common --no-edit
$mergeExit = $LASTEXITCODE

if ($mergeExit -ne 0) {
    Write-Host ""
    Write-Host "[!] 出现冲突. 处理规则:" -ForegroundColor Yellow
    Write-Host "    - 品牌字段 (APP_NAME / WEBUI_NAME / <title> / METEO_SYSTEM_PROMPT)"
    Write-Host "      => 保留 ours (当前部署的版本)"
    Write-Host "      => git checkout --ours <file>"
    Write-Host "    - logo / favicon / splash / web-app-manifest 等品牌图片"
    Write-Host "      => 保留 ours"
    Write-Host "      => git checkout --ours <file>"
    Write-Host "    - 其他业务代码冲突 => 手工解决, 优先 theirs (来自 common 的新版本)"
    Write-Host ""
    Write-Host "    解决完后:"
    Write-Host "      git add <files>"
    Write-Host "      git merge --continue"
    Write-Host "      git push origin $current"
    exit 1
}

# 5. 提示推送
Write-Host "[3/3] merge 完成, 当前分支 = $current" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1) 先本地验证: npm run build (前端) / 重启后端"
Write-Host "  2) 验证 OK 后:  git push origin $current"
