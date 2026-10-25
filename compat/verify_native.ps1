param(
    [Parameter(Mandatory=$true)][string]$Delphi7Compiler,
    [Parameter(Mandatory=$true)][string]$Delphi5Compiler
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
foreach ($target in @(@('7',$Delphi7Compiler),@('5',$Delphi5Compiler))) {
    $version = $target[0]
    $compiler = (Resolve-Path -LiteralPath $target[1]).Path
    $outDir = Join-Path $projectRoot "evidence\legacy\native$version"
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    & $compiler '-B' "-E$outDir" "-N$outDir" (Join-Path $PSScriptRoot 'CompatProbe.dpr')
    if ($LASTEXITCODE -ne 0) { throw "Delphi $version probe compilation failed" }
    & (Join-Path $outDir 'CompatProbe.exe') (Join-Path $projectRoot "evidence\legacy\Delphi$version.dfm") $outDir
    if ($LASTEXITCODE -ne 0) { throw "Delphi $version native loading failed" }
    $actual = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outDir 'FuncDemo.txt')
    $expected = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $projectRoot "evidence\legacy\Delphi$version.expected.gbk.txt")
    if ($actual.Hash -ne $expected.Hash) { throw "Delphi $version TMemo content differs from expected GBK bytes" }
    Write-Output "PASS Delphi $version native parser, TMemo and GBK byte comparison"
}
