# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    把自签名代码签名证书导入「受信任的根证书颁发机构」，让本机认可签名。

.DESCRIPTION
    Windows 判断 Authenticode 签名的发布者，靠的是证书链能否追到**受信任根**。
    自签名证书自己是根，默认不受信任，所以属性页仍写「未知发布者」。
    把 tools/signing/cr-lbj-codesign.cer 导入受信任根后，本机就会显示
    「发布者：刘纪彤（BG2GBQ）」。

    注意：
      * 只影响**这台电脑**；别人电脑仍显示未知发布者（要全球通用必须买 CA 证书）。
      * 需要管理员权限（未提权会失败）。
      * 导入后，任何用该私钥签名的文件都会被本机信任——私钥务必妥善保管。

.EXAMPLE
    # 以管理员身份打开 PowerShell 后运行
    pwsh tools/install_codesign_trust.ps1
    pwsh tools/install_codesign_trust.ps1 -Uninstall
#>
param(
    [switch]$Uninstall,
    [string]$Cer = ""
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Cer) { $Cer = Join-Path $PSScriptRoot 'signing\cr-lbj-codesign.cer' }
if (-not (Test-Path $Cer)) { throw "找不到证书文件: $Cer（先运行 tools/sign_exe.ps1 -MakeCert）" }

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw '需要管理员权限：请右键「以管理员身份运行」PowerShell 后重试。'
}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $Cer
Write-Host "[trust] 证书主体: $($cert.Subject)"
Write-Host "[trust] Thumbprint: $($cert.Thumbprint)"

$stores = @(
    'Cert:\LocalMachine\Root',
    'Cert:\LocalMachine\TrustedPublisher'
)
foreach ($store in $stores) {
    if ($Uninstall) {
        Get-ChildItem $store | Where-Object { $_.Thumbprint -eq $cert.Thumbprint } |
            ForEach-Object {
                Remove-Item $_.PSPath -Force
                Write-Host "[trust] 已从 $store 移除"
            }
    } else {
        Import-Certificate -FilePath $Cer -CertStoreLocation $store | Out-Null
        Write-Host "[trust] 已导入 $store"
    }
}

Write-Host ''
if ($Uninstall) {
    Write-Host '[trust] 已撤销本机信任。'
} else {
    Write-Host '[trust] 完成。现在重新查看 EXE 属性 → 数字签名，应显示：'
    Write-Host '        签名者: 刘纪彤（BG2GBQ）'
    Write-Host '        签名状态: 有效（本机信任）'
    Write-Host '  提示：SmartScreen 仍可能对「新发布者」的下载文件提示，'
    Write-Host '        这属于声誉机制，多下载几次/时间积累后会消失；'
    Write-Host '        要完全无提示需购买 EV 代码签名证书。'
}