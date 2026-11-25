<#
  test.ps1 — 在中文路径下跑 JVM 单元测试

  为什么需要它
  ------------
  Gradle 在 Windows 上把测试进程的 classpath 写进 `@argfile`
  （%USERPROFILE%\.gradle\.tmp\gradle-worker-classpath*.txt）。JDK 启动器解析
  argfile 时无法正确处理非 ASCII 路径，哪怕文件本身是 UTF-8：

      直接 -cp "E:\预警器\...\classes"  →  正常
      @argfile 里同样的路径            →  ClassNotFoundException

  表现是 `:app:testDebugUnitTest` 报
      Could not execute test class 'xyz.mlxkj.crlbj.data.LocoRosterTest'

  绕过办法：用 `subst` 给仓库父目录挂一个 ASCII 盘符（默认 X:），从 X: 下跑 Gradle。
  实测 Gradle **不会**把 subst 盘符规范化回真实路径，argfile 里全是 ASCII，测试正常。
  编译产物是同一份物理文件，不会重复构建。

  ⚠ 路径一致性
  ------------
  KSP / Kotlin 的增量缓存记录的是**绝对路径**，在 E: 和 X: 之间来回切会出现
      e: [ksp] java.lang.IllegalArgumentException: this and base files have different roots
  所以本脚本在开始和结束时都会清掉这几个增量缓存目录（只删缓存，不动 class/APK），
  让「E: 构建 → 跑测试 → 再 E: 构建」这条链路始终可用。

  用法
  ----
    pwsh -File tools/test.ps1                      # = :app:testDebugUnitTest
    pwsh -File tools/test.ps1 -Task :app:assembleDebug
    pwsh -File tools/test.ps1 -KeepDrive           # 保留盘符（调试用）
    pwsh -File tools/test.ps1 -ExtraArgs '--no-configuration-cache'
#>
[CmdletBinding()]
param(
    [string]$Task = ':app:testDebugUnitTest',
    [string[]]$ExtraArgs = @(),
    [switch]$KeepDrive
)

$ErrorActionPreference = 'Stop'

$androidDir = Split-Path -Parent $PSScriptRoot          # …\CR_LBJ_Receiver\android
$repoDir = Split-Path -Parent $androidDir               # …\CR_LBJ_Receiver
$parentDir = Split-Path -Parent $repoDir                # …\预警器
$repoName = Split-Path -Leaf $repoDir

# KSP / Kotlin 增量缓存记录绝对路径，跨盘符会 root 冲突 → 切路径前后都清掉
$cacheDirs = @(
    (Join-Path $androidDir 'app\build\kspCaches'),
    (Join-Path $androidDir 'app\build\kotlin'),
    (Join-Path $androidDir '.kotlin')
)

function Clear-BuildCaches {
    # 先停 daemon：KSP 缓存文件被 daemon 持有句柄时删不掉，跨盘符就会 root 冲突
    $gradlew = Join-Path $androidDir 'gradlew.bat'
    if (Test-Path $gradlew) { & $gradlew --stop 2>$null | Out-Null }
    Start-Sleep -Milliseconds 800
    foreach ($d in $cacheDirs) {
        if (-not (Test-Path $d)) { continue }
        # 句柄可能晚一点才释放：删不掉就重试几次（实测第一次偶尔会失败）
        for ($i = 0; $i -lt 3; $i++) {
            cmd /c "rd /s /q `"$d`"" 2>$null | Out-Null
            if (-not (Test-Path $d)) { break }
            Start-Sleep -Milliseconds 600
        }
        if (Test-Path $d) {
            Write-Host "  清理失败（可能有进程占用）：$d" -ForegroundColor Yellow
        } else {
            Write-Host "  清理增量缓存：$d" -ForegroundColor DarkGray
        }
    }
}

function Test-Ascii([string]$s) {
    return -not ($s.ToCharArray() | Where-Object { [int]$_ -gt 127 })
}

if (Test-Ascii $androidDir) {
    Write-Host "路径已是 ASCII，直接运行：$androidDir" -ForegroundColor Green
    Push-Location $androidDir
    try {
        & (Join-Path $androidDir 'gradlew.bat') $Task @ExtraArgs
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

$used = (& subst) 2>$null | ForEach-Object { ($_ -split ':')[0].Trim().ToUpper() }
$letter = $null
foreach ($c in 'X', 'Y', 'W', 'V', 'U') {
    if ($used -notcontains $c) { $letter = $c; break }
}
if (-not $letter) { throw "没有空闲盘符可用于 subst（已占用：$($used -join ',')）" }

$driveRoot = "${letter}:"
Write-Host "映射 $driveRoot → $parentDir" -ForegroundColor Cyan
subst $driveRoot $parentDir
if ($LASTEXITCODE -ne 0) { throw "subst 失败（$driveRoot）" }

$mappedAndroid = Join-Path "$driveRoot\" (Join-Path $repoName 'android')
Write-Host "项目路径：$mappedAndroid" -ForegroundColor Cyan

Clear-BuildCaches
try {
    Push-Location $mappedAndroid
    & (Join-Path $mappedAndroid 'gradlew.bat') $Task @ExtraArgs
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    Clear-BuildCaches
    if (-not $KeepDrive) {
        subst $driveRoot /d | Out-Null
        Write-Host "已解除 $driveRoot" -ForegroundColor DarkGray
    } else {
        Write-Host "保留 $driveRoot（清理：subst $driveRoot /d）" -ForegroundColor Yellow
    }
}
exit $code
