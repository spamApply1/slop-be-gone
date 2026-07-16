param(
    [Parameter(Position = 0)]
    [string]$TargetRepo = ".",

    [Parameter(Position = 1)]
    [string]$ManifestPath
)

$ErrorActionPreference = "Stop"

function Resolve-PythonCommand {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $sbgRepoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

    if (Test-Path -LiteralPath (Join-Path $sbgRepoRoot ".venv/bin/python") -PathType Leaf) {
        return @((Join-Path $sbgRepoRoot ".venv/bin/python"))
    }
    if (Test-Path -LiteralPath (Join-Path $sbgRepoRoot ".venv/Scripts/python.exe") -PathType Leaf) {
        return @((Join-Path $sbgRepoRoot ".venv/Scripts/python.exe"))
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        return @("python3")
    }
    throw "Python 3 is required to install SBG."
}

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    if ($script:PythonCommand.Length -eq 2) {
        & $script:PythonCommand[0] $script:PythonCommand[1] @Arguments
    }
    else {
        & $script:PythonCommand[0] @Arguments
    }
}

$script:PythonCommand = Resolve-PythonCommand
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sbgRepoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

if (-not (Test-Path -LiteralPath $TargetRepo -PathType Container)) {
    throw "Target repository not found: $TargetRepo"
}

$targetRepoPath = (Resolve-Path -LiteralPath $TargetRepo).Path

Write-Host "Installing SBG from $sbgRepoRoot..."
if ($script:PythonCommand.Length -eq 1) {
    Invoke-Python -m pip install --quiet --disable-pip-version-check -e $sbgRepoRoot
}
else {
    Invoke-Python -m pip install --quiet --disable-pip-version-check --user -e $sbgRepoRoot
}

Write-Host "Installing SBG hook into $targetRepoPath..."
if ($ManifestPath) {
    Invoke-Python -m sbg.cli install-hooks $targetRepoPath --manifest $ManifestPath
}
else {
    Invoke-Python -m sbg.cli install-hooks $targetRepoPath
}
