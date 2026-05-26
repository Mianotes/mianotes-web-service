param(
    [switch]$Dev,
    [switch]$SkillsOnly
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    if ($env:PYTHON) {
        return @($env:PYTHON)
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
        if ($LASTEXITCODE -eq 0) {
            return @($py.Source, "-3")
        }
    }

    foreach ($name in @("python3", "python")) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate) {
            & $candidate.Source -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
            if ($LASTEXITCODE -eq 0) {
                return @($candidate.Source)
            }
        }
    }

    throw "Python 3.11 or newer is required. Install Python, then run this installer again."
}

function Invoke-Python {
    param(
        [string[]]$PythonCommand,
        [string[]]$PythonArguments
    )

    $exe = $PythonCommand[0]
    $prefixArgs = @()
    if ($PythonCommand.Count -gt 1) {
        $prefixArgs = $PythonCommand[1..($PythonCommand.Count - 1)]
    }
    & $exe @prefixArgs @PythonArguments
}

function Install-Skill {
    param([string]$TargetDir)

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    Copy-Item -Force -Path (Join-Path $RootDir "skills/mianotes/SKILL.md") -Destination (Join-Path $TargetDir "SKILL.md")
    Write-Host "Installed Mianotes skill: $(Join-Path $TargetDir "SKILL.md")"
}

if (-not $SkillsOnly) {
    $Python = Find-Python
    $PackagePath = $RootDir
    if ($Dev) {
        $PackagePath = "$RootDir[dev]"
    }
    Invoke-Python -PythonCommand $Python -PythonArguments @("-m", "pip", "install", "-e", $PackagePath)
}

if (-not $env:USERPROFILE) {
    throw "USERPROFILE is not set; cannot install agent skills."
}

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$ClaudeHome = if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { Join-Path $env:USERPROFILE ".claude" }

Install-Skill (Join-Path $CodexHome "skills/mianotes")
Install-Skill (Join-Path $ClaudeHome "skills/mianotes")

Write-Host ""
if ($SkillsOnly) {
    Write-Host "Mianotes agent skills installed."
} else {
    Write-Host "Mianotes web service installed."
    Write-Host ""
    Write-Host "Next:"
    Write-Host "  mianotes-web-service init-db"
    Write-Host "  mianotes-web-service --host 0.0.0.0 --port 8200"
}
