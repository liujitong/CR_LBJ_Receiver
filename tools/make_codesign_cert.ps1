# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    生成 / 更新 CR-LBJ-Receiver 的 Windows 代码签名证书（自签名）。

.DESCRIPTION
    v3.2.10 起改用 **OpenSSL** 按 tools/codesign-openssl.cnf 生成，原因：
      * PowerShell 的 New-SelfSignedCertificate 生成 7 个 DN 字段
        （C/O/OU/L/S/CN/E），SmartScreen 会把它们**全部摊开**显示成
        「bg2gbq@mlxkj.xyz, CN, 北京, 北京, BG2GBQ, 刘纪彤, 刘纪彤（BG2GBQ）」；
      * 改用精简 DN（C + O + CN）+ 明确 UTF-8 编码后，SmartScreen 只显示
        「刘纪彤（BG2GBQ）」。

    产出（均在 tools/signing/，整个目录已被 .gitignore 忽略）：
      key.pem                    私钥
      cert.pem                   证书（PEM）
      cr-lbj-codesign.pfx        证书+私钥（供 signtool 使用）
      cr-lbj-codesign.cer        公钥证书（DER，供用户安装信任）
      password.txt               pfx 口令

    生成后请执行 tools/sign_exe.ps1 完成签名；用户端信任见 tools/install_cert.cmd。

.EXAMPLE
    pwsh tools/make_codesign_cert.ps1
#>
param(
    [int]$Days = 3650,
    [string]$OpenSSL = ""
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SignDir = Join-Path $PSScriptRoot 'signing'
$Cnf = Join-Path $PSScriptRoot 'codesign-openssl.cnf'
New-Item -ItemType Directory -Force -Path $SignDir | Out-Null

if (-not $OpenSSL) {
    $cmd = Get-Command openssl -ErrorAction SilentlyContinue
    if ($cmd) { $OpenSSL = $cmd.Source }
}
if (-not $OpenSSL) {
    foreach ($p in @('D:\anaconda3\Library\bin\openssl.exe',
                     'C:\Program Files\OpenSSL-Win64\bin\openssl.exe',
                     'C:\Program Files\Git\usr\bin\openssl.exe')) {
        if (Test-Path $p) { $OpenSSL = $p; break }
    }
}
if (-not $OpenSSL) { throw '找不到 openssl.exe（可 -OpenSSL 指定路径）' }
if (-not (Test-Path $Cnf)) { throw "缺少证书配置: $Cnf" }

$key = Join-Path $SignDir 'key.pem'
$certPem = Join-Path $SignDir 'cert.pem'
$pfx = Join-Path $SignDir 'cr-lbj-codesign.pfx'
$cer = Join-Path $SignDir 'cr-lbj-codesign.cer'
$pwFile = Join-Path $SignDir 'password.txt'
$pw = "CRLBJ-$([guid]::NewGuid().ToString('N').Substring(0,16))!"

Write-Host "[cert] openssl: $OpenSSL"
Write-Host "[cert] 配置   : $Cnf"
Write-Host "[cert] 生成自签名代码签名证书（RSA 4096 / SHA256 / $Days 天）..."

# 原生命令会往 stderr 打进度条；临时放宽错误策略避免被当成致命错误
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $OpenSSL req -x509 -newkey rsa:4096 -keyout $key -out $certPem `
    -days $Days -nodes -config $Cnf 2>&1 | Out-Null
$rcReq = $LASTEXITCODE
& $OpenSSL pkcs12 -export -out $pfx -inkey $key -in $certPem `
    -passout "pass:$pw" -name 'CR-LBJ-Receiver' 2>&1 | Out-Null
$rcPfx = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($rcReq -ne 0) { throw "openssl req 失败 (rc=$rcReq)" }
if ($rcPfx -ne 0) { throw "openssl pkcs12 失败 (rc=$rcPfx)" }

& $OpenSSL x509 -in $certPem -outform DER -out $cer
Set-Content -Path $pwFile -Value $pw -Encoding UTF8

Write-Host ''
Write-Host '[cert] 证书主体（应只有 C / O / CN 三个字段）:'
& $OpenSSL x509 -in $certPem -noout -subject | ForEach-Object { "    $($_.Trim())" }
& $OpenSSL x509 -in $certPem -noout -text |
    Select-String -Pattern 'CA:TRUE|Code Signing' |
    ForEach-Object { "    $($_.Line.Trim())" }

Write-Host ''
Write-Host '[cert] 产出:'
Write-Host "    $pfx"
Write-Host "    $cer"
Write-Host "    $pwFile"
Write-Host ''
Write-Host '[cert] 下一步:'
Write-Host '    1) pwsh tools/sign_exe.ps1            # 签名 dist/CR-LBJ-Receiver.exe'
Write-Host '    2) 让本机信任: 双击 tools/install_cert.cmd（点「是」）'
Write-Host '    3) 要让所有电脑显示发布者: 需购买 CA 代码签名证书（见 docs/代码签名.md）'
exit 0