# One-command pipeline: train -> export -> register with Ollama
# Usage:
#   .\models\finetune\rebuild_model.ps1              # personal track (default)
#   .\models\finetune\rebuild_model.ps1 -Track shippable
#
# Run from terminal-monitor project root.

param(
    [ValidateSet("personal", "shippable")]
    [string]$Track = "personal"
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PYTHON = Join-Path $ROOT ".venv-finetune\Scripts\python.exe"

if (-not (Test-Path $PYTHON)) {
    Write-Error "Fine-tune venv not found. Run .\models\finetune\setup.ps1 first."
    exit 1
}

$TrainScript = if ($Track -eq "personal") {
    Join-Path $PSScriptRoot "train_personal.py"
} else {
    Join-Path $PSScriptRoot "train_shippable.py"
}
$ExportScript = Join-Path $PSScriptRoot "export_gguf.py"

Write-Host "=== Track: $Track ===" -ForegroundColor Cyan

Write-Host "`n[1/2] Training"
& $PYTHON $TrainScript

Write-Host "`n[2/2] Exporting GGUF + registering with Ollama"
& $PYTHON $ExportScript --track $Track

Write-Host "`nDone." -ForegroundColor Green
