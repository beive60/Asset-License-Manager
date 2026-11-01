<#
.SYNOPSIS
    ローカル環境で AssetLicenseManager のビルド・署名・リリースを一括実行する。

.DESCRIPTION
    以下の手順を順次実行する:
        1. PyInstaller (uv 経由) で exe および依存ファイルを生成
        2. signtool で物理トークンを用いたコード署名と検証
        3. 成果物の ZIP アーカイブ作成
        4. git tag 作成と gh release によるアセットアップロード

    物理ハードウェアトークンが接続されていない場合、ステップ 2 で失敗する。

.PARAMETER Version
    リリースバージョン文字列 (例: "0.1.0")。
    git tag には "v" プレフィックスが自動付与される。

.EXAMPLE
    .\scripts\release.ps1 -Version "0.1.0"

.NOTES
    前提条件: uv, signtool, git, gh CLI がパス上に存在すること。
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"

# Helper function to check for command existence
function Assert-CommandExists {
    param($command)
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command '$command' not found in PATH. Please install it and try again."
    }
}

function Assert-LastExitCode {
    param([string]$Action)

    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE."
    }
}

try {
    Write-Host "=== 0/5: Check Prerequisites ==="
    "uv", "signtool", "git", "gh" | ForEach-Object { Assert-CommandExists $_ }
    Write-Host "All prerequisites found."

    # スクリプトがリポジトリ直下の scripts/ などにあることを前提にルートを取得
    $repoRoot = Split-Path -Parent $PSScriptRoot

    Write-Host "=== 1/5: Build ==="
    
    # 実行パスをリポジトリルートに移動して PyInstaller を実行
    Push-Location $repoRoot
    try {
        uv run pyinstaller --noconfirm --onedir --windowed --icon="assets\icon\icon.ico" --add-data="assets\icon\icon.ico;assets\icon" --name "AssetLicenseManager" "src\asset_license_manager\main.py"
        Assert-LastExitCode "PyInstaller build"
    }
    finally {
        Pop-Location
    }

    Write-Host "=== 2/5: Sign ==="

    # PyInstaller の --onedir オプションにより dist\AssetLicenseManager フォルダ内に生成される
    $releaseDir = Join-Path $repoRoot "dist\AssetLicenseManager"
    $exePath = Join-Path $releaseDir "AssetLicenseManager.exe"

    if (-not (Test-Path $exePath)) {
        throw "Executable not found at: $exePath"
    }

    signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a $exePath
    Assert-LastExitCode "signtool sign (AssetLicenseManager.exe)"

    signtool verify /pa $exePath
    Assert-LastExitCode "signtool verify (AssetLicenseManager.exe)"

    Write-Host "=== 3/5: Zip Artifacts ==="

    $distDir = Join-Path $repoRoot "dist"
    $zipFileName = "AssetLicenseManager-v$($Version).zip"
    $zipPath = Join-Path $distDir $zipFileName

    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }

    # dist\AssetLicenseManager ディレクトリごと ZIP に圧縮
    Compress-Archive -Path $releaseDir -DestinationPath $zipPath -Force
    
    Write-Host "Created release zip: $zipPath"

    Write-Host "=== 4/5: Release ==="

    Write-Host "Checking GitHub CLI authentication status..."
    gh auth status
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI not authenticated. Please run 'gh auth login' and try again."
    }
    Write-Host "GitHub CLI is authenticated."

    git -C $repoRoot tag "v$Version"
    Assert-LastExitCode "git tag"

    git -C $repoRoot push origin "v$Version"
    Assert-LastExitCode "git push origin v$Version"

    # カレントディレクトリが Git リポジトリであれば --repo を省略可能です
    # 指定が必要な場合は `--repo user/repo` を追加してください
    Push-Location $repoRoot
    try {
        gh release create "v$Version" $zipPath --title "Release v$Version" --generate-notes
        Assert-LastExitCode "gh release create"
    }
    finally {
        Pop-Location
    }

    Write-Host "=== 5/5: Done ==="
    Write-Host "Released v$Version successfully."
}
catch {
    Write-Host "`nError during release process:"
    Write-Host "  - $($_.Exception.Message)"
    exit 1
}
