<#
  fix_ninja.ps1 — 把支持 UTF-8 路径的 ninja 放到 <cmake.dir>\bin\ninja.exe

  背景
  ----
  本仓库物理路径含中文（…\预警器\…）。AGP 以 -DCMAKE_MAKE_PROGRAM 传入 ninja，
  默认会挑 Android SDK 里**版本最低**那个 CMake 附带的 ninja（3.22.1 → ninja 1.10.2）。
  ninja 1.10 在 Windows 上用 ANSI 代码页解释 build.ninja 里的路径，中文路径会触发

      ninja: error: FindFirstFileExA(e:/预警器/…/src/main/cpp): 文件名、目录名或卷标语法不正确

  CMake 本身没有这个问题（本机用 pip 版 CMake 4.4.5，local.properties 里配了 cmake.dir）。
  ninja 1.12 起按 UTF-8 处理路径。AGP 会优先使用 <cmake.dir>\bin\ninja.exe，
  所以本脚本把 SDK 里版本最高的 ninja 复制过去。

  用法
  ----
    pwsh -NoProfile -File tools/fix_ninja.ps1            # 自动探测并安装
    pwsh -NoProfile -File tools/fix_ninja.ps1 -Check     # 只检查，不改动
    pwsh -NoProfile -File tools/fix_ninja.ps1 -Source D:\path\to\ninja.exe
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [string]$Source
)

$ErrorActionPreference = 'Stop'
$androidDir = Split-Path -Parent $PSScriptRoot   # …/android
$localProps = Join-Path $androidDir 'local.properties'

function Read-Property([string]$path, [string]$key) {
    if (-not (Test-Path $path)) { return $null }
    $line = Get-Content $path -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($key))=" } | Select-Object -First 1
    if (-not $line) { return $null }
    # .properties 里冒号和等号都会被转义：D\:\\Android\\SDK
    return ($line -replace "^\s*$([regex]::Escape($key))=", '').Replace('\:', ':').Replace('\\', '\').Trim()
}

$cmakeDir = Read-Property $localProps 'cmake.dir'
$sdkDir = Read-Property $localProps 'sdk.dir'
if (-not $sdkDir) { $sdkDir = $env:ANDROID_HOME }
if (-not $cmakeDir) {
    Write-Host "local.properties 未配置 cmake.dir，无需安装（AGP 会用 SDK 自带 CMake）" -ForegroundColor Yellow
    exit 2
}

$dest = Join-Path $cmakeDir 'bin\ninja.exe'

if (-not $Source) {
    if (-not $sdkDir) { throw "无法确定 Android SDK 路径：local.properties 无 sdk.dir，且未设置 ANDROID_HOME" }
    $cands = Get-ChildItem (Join-Path $sdkDir 'cmake') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object {
            $ninja = Join-Path $_.FullName 'bin\ninja.exe'
            if (Test-Path $ninja) {
                [pscustomobject]@{
                    Path    = $ninja
                    Version = $_.Name
                }
            }
        } | Sort-Object { [version]($_.Version -replace '[^0-9.].*$', '') } -Descending
    if (-not $cands) { throw "在 $sdkDir\cmake 下没找到任何 ninja.exe" }
    $Source = $cands[0].Path
}

$srcVer = (& $Source --version) -replace '\s', ''
Write-Host "源 ninja : $Source (v$srcVer)"
Write-Host "目标位置 : $dest"

$destVer = $null
if (Test-Path $dest) { $destVer = (& $dest --version) -replace '\s', '' }
Write-Host "当前安装 : $(if ($destVer) { "v$destVer" } else { '（无）' })"

if ($Check) {
    if ($destVer -and [version]$destVer -ge [version]'1.12') {
        Write-Host "OK：已安装的 ninja >= 1.12，中文路径可构建" -ForegroundColor Green
        exit 0
    }
    Write-Host "需要安装：<cmake.dir>/bin/ninja.exe 缺失或低于 1.12" -ForegroundColor Yellow
    exit 1
}

Copy-Item $Source $dest -Force
$newVer = (& $dest --version) -replace '\s', ''
Write-Host "已安装 ninja v$newVer → $dest" -ForegroundColor Green
if ([version]$newVer -lt [version]'1.12') {
    Write-Host "警告：源 ninja 低于 1.12，中文路径仍可能失败" -ForegroundColor Yellow
    exit 1
}
exit 0
