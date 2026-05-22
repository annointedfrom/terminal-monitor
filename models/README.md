# Terminal Monitor — Models

Local LLM infrastructure for the ops dashboard.

## Quick start (first time)

```powershell
# 1. Pull base model
ollama pull llama3.2:3b

# 2. Build ops-brain (baked-in system prompt)
ollama create ops-brain -f models/Modelfile

# 3. Test
ollama run ops-brain "What is svchost.exe?"
```

## Fine-tuning (personal track)

Train on your saved Q&A pairs from the AI tab (thumbs-up button saves to `training_seed.jsonl`):

```powershell
# First time only — create venv + install PyTorch CUDA
.\models\finetune\setup.ps1

# Train + export + re-register ops-brain
.\models\finetune\rebuild_model.ps1
```

Requires a CUDA GPU. The rebuilt `ops-brain` replaces the base Modelfile version.

## Fine-tuning (shippable track)

Produces `ops-brain-base.gguf` — generic ops knowledge, no personal data:

```powershell
.\models\finetune\rebuild_model.ps1 -Track shippable
```

## Buyer setup (ship flow)

Buyers receive `ops-brain-base.gguf` + `Modelfile.template`.  
The setup script personalizes the Modelfile from their own `hub-config.yaml`:

```powershell
python models/generate_modelfile.py
ollama create ops-brain -f models/Modelfile.generated
```

## Files

| File | Purpose |
|---|---|
| `Modelfile` | ops-brain with Angel's full stack baked in |
| `Modelfile.template` | Buyer template with `{{AGENT_BLOCK}}` placeholder |
| `Modelfile.generated` | Auto-generated per-buyer (gitignored) |
| `generate_modelfile.py` | Reads hub-config.yaml → fills Modelfile.template |
| `training_seed.jsonl` | Curated Q&A training pairs |
| `finetune/requirements-finetune.txt` | Python deps for fine-tuning |
| `finetune/setup.ps1` | One-time venv + PyTorch CUDA setup |
| `finetune/train_personal.py` | LoRA fine-tune on all seed pairs |
| `finetune/train_shippable.py` | LoRA fine-tune on generic-only pairs |
| `finetune/export_gguf.py` | Checkpoint → GGUF → `ollama create` |
| `finetune/rebuild_model.ps1` | End-to-end pipeline (train + export) |
