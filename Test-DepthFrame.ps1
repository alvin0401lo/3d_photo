$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Invoke-DepthCheck {
    param([string]$Label, [string]$Program, [string[]]$Arguments)
    Write-Output $Label
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)." }
}
$depthTestTemp = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ('artifacts\pytest-' + [Guid]::NewGuid().ToString('N'))))
if (-not $depthTestTemp.StartsWith($PSScriptRoot + [System.IO.Path]::DirectorySeparatorChar) -or (Test-Path -LiteralPath $depthTestTemp)) { throw 'Unsafe or reused test scratch directory.' }
Invoke-DepthCheck 'Backend regression' '.\.venv\Scripts\python.exe' @('-m','pytest','backend/tests','-q','-p','no:cacheprovider','--basetemp',$depthTestTemp)
Invoke-DepthCheck 'Python compilation' '.\.venv\Scripts\python.exe' @('-m','compileall','-q','backend','scripts')
Invoke-DepthCheck 'Dependency consistency' '.\.venv\Scripts\python.exe' @('-m','pip','check')
Invoke-DepthCheck 'Frontend geometry tests' 'npm.cmd' @('--prefix','frontend','test')
Invoke-DepthCheck 'Production build' 'npm.cmd' @('--prefix','frontend','run','build')
Invoke-DepthCheck 'Browser acceptance (requires running application and Chrome)' 'npm.cmd' @('--prefix','frontend','run','test:e2e')
Invoke-DepthCheck 'Real worker failure/recovery checks' '.\.venv\Scripts\python.exe' @('scripts/worker_checks.py')
Invoke-DepthCheck 'Reopen downloaded exports' '.\.venv\Scripts\python.exe' @('scripts/validate_exports.py')
Write-Output 'PASS: all local CPU release checks in this script passed.'
