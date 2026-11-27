#!/usr/bin/env pwsh
# -*- coding: utf-8 -*-
<#
.SYNOPSIS
    给 dist/CR-LBJ-Receiver.exe 做 Authenticode 代码签名（v3.2.10）。

.DESCRIPTION
    签名材料放在 tools/signing/（已 gitignore，含私钥，绝不入库）：
      cr-lbj-codesign.pfx   代码签名证书 + 私钥
      password.txt          pfx 口令（仅本机保存）

    支持两种证书：
      1) 自签名证书（本脚本 make-cert 子命令生成）
         → 文件属性里能看到「数字签名」，但 Windows SmartScreen / 属性页
           仍显示「未知发布者」，除非把 .cer 导入「受信任的根证书颁发机构」。
      2) CA 签发的代码签名证书（OV / EV，需购买）
         → Windows 直接显示「发布者：刘纪彤（BG2GBQ）」，不弹「未知发布者」。

.PARAMETER Exe
    要签名的 exe 路径，默认 dist/CR-LBJ-Receiver.exe。

.PARAMETER MakeCert
    先生成/更新自签名证书（4096-bit RSA / SHA256 / 10 年）。

.EXAMPLE
    pwsh tools/sign_exe.ps1 -MakeCert
    pwsh tools/sign_exe.ps1
#>
param(
    [string]$Exe = "",
    [switch]$MakeCert
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SignDir = Join-Path $PSScriptRoot 'signing'
$Pfx = Join-Path $SignDir 'cr-lbj-codesign.pfx'
$PwFile = Join-Path $SignDir 'password.txt'
$Cer = Join-Path $SignDir 'cr-lbj-codesign.cer'

# 发布者信息（与 desktop/SDR_LBJ.spec 的版本资源保持一致）
$Subject = 'CN=刘纪彤（BG2GBQ）, O=刘纪彤, OU=BG2GBQ, L=北京, S=北京, C=CN, E=bg2gbq@mlxkj.xyz'

function Find-SignTool {
    $kits = 'C:\Program Files (x86)\Windows Kits\10\bin'
    if (Test-Path $kits) {
        $hit = Get-ChildItem $kits -Directory |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName 'x64\signtool.exe' } |
            Where-Object { Test-Path $_ } |
            Select-Object -First 1
        if ($hit) { return $hit }
    }
    throw '找不到 signtool.exe（需安装 Windows SDK）'
}

if ($MakeCert) {
    # 交给 make_codesign_cert.ps1（OpenSSL 生成，DN 精简为 C/O/CN，避免 SmartScreen 摊开显示）
    & (Join-Path $PSScriptRoot 'make_codesign_cert.ps1')
    exit $LASTEXITCODE
}
if (-not $Exe) { $Exe = Join-Path $RepoRoot 'dist\CR-LBJ-Receiver.exe' }
if (-not (Test-Path $Exe)) { throw "找不到待签名文件: $Exe" }
if (-not (Test-Path $Pfx)) {
    throw "缺少签名证书 $Pfx —— 先运行: pwsh tools/sign_exe.ps1 -MakeCert"
}
if (-not (Test-Path $PwFile)) { throw "缺少 pfx 口令文件: $PwFile" }
$pw = (Get-Content $PwFile -Raw).Trim()
$signtool = Find-SignTool

Write-Host "[sign] signtool: $signtool"
Write-Host "[sign] 目标: $Exe"

# 优先带 RFC3161 时间戳；网络不通时退回不带时间戳（仍有效，但证书到期后签名失效）
$signed = $false
foreach ($ts in @('http://timestamp.digicert.com',
                  'http://timestamp.sectigo.com',
                  '')) {
    $args = @('sign', '/fd', 'SHA256', '/f', $Pfx, '/p', $pw, '/a')
    if ($ts) { $args += @('/tr', $ts, '/td', 'SHA256') }
    $args += $Exe
    Write-Host "[sign] 尝试: $(if($ts){"时间戳 $ts"}else{"无时间戳"})"
    & $signtool @args 2>&1 | ForEach-Object { "    $_" }
    if ($LASTEXITCODE -eq 0) { $signed = $true; break }
}

if (-not $signed) { throw '签名失败（三次尝试均未成功）' }

Write-Host "[sign] 校验签名:"
# 注意：自签名证书链终止于「不受信任的根」，signtool verify /pa 必然非 0 退出——
# 这是预期行为，绝不能当成签名失败（用 Get-AuthenticodeSignature 看真实状态）。
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $signtool verify /pa $Exe 2>&1 |
    Select-String -Pattern 'Signing Certificate|Issued to|Successfully verified|Number of errors|terminated in a root' |
    ForEach-Object { "    $($_.Line.Trim())" } | Out-Null
$ErrorActionPreference = $prevEap

$sig = Get-AuthenticodeSignature $Exe
Write-Host "    签名者: $($sig.SignerCertificate.Subject)"
Write-Host "    时间戳: $($sig.TimeStamperCertificate.Subject)"
Write-Host "    链状态: $($sig.Status)  （自签名=UnknownError 属正常，见下方说明）"

Write-Host ''
Write-Host '[sign] 完成。注意：'
Write-Host '  自签名证书 → Windows 属性页仍显示「未知发布者」（除非本机导入受信任根）。'
Write-Host '  本机信任: 管理员运行 tools/install_codesign_trust.ps1'
Write-Host '  全球显示发布者: 需购买 CA 代码签名证书（OV/EV），详见 docs/代码签名.md'

exit 0
