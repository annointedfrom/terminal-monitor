# Fine-tuning environment setup (Windows, CUDA 12.1)
# Run once from the terminal-monitor root:  .\models\finetune\setup.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VENV = Join-Path $ROOT ".venv-finetune"

Write-Host "==> Creating venv at $VENV"
python -m venv $VENV

$PIP = Join-Path $VENV "Scripts\pip.exe"
$PYTHON = Join-Path $VENV "Scripts\python.exe"

Write-Host "==> Upgrading pip"
& $PYTHON -m pip install --upgrade pip

Write-Host "==> Installing PyTorch 2.3 with CUDA 12.1"
& $PIP install torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 `
    --index-url https://download.pytorch.org/whl/cu121

Write-Host "==> Installing fine-tuning stack"
& $PIP install -r "$PSScriptRoot\requirements-finetune.txt"

Write-Host ""
Write-Host "Setup complete.  Activate with:"
Write-Host "  & '$VENV\Scripts\Activate.ps1'"
