# Terminal Integration

The AI tab contains two sub-panes: **CHAT** and **TERMINAL**. The terminal is a live PowerShell runner connected to the backend via WebSocket. Other tabs can open it with a pre-loaded command.

---

## Using the Terminal

Click **AI → TERMINAL** tab. Type any PowerShell command and press Enter or **RUN**.

```
PS> ollama list
PS> Get-Process | Sort-Object WorkingSet -Descending | Select -First 10
PS> nvidia-smi
PS> cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor && .venv\Scripts\python -m pytest
```

**CLR** clears the output. Each command runs as an independent PowerShell process (no state carried between commands).

---

## Cross-Tab Integration

### PROCESSES tab
Click any process row to expand its detail panel. A **⏸ inspect in terminal** button appears — it runs:
```powershell
Get-Process -Id <pid> | Format-List Id,Name,CPU,WorkingSet,Path,StartTime
```

### MCP / Services tab
Offline services show a **▶ start** button. Clicking it opens the terminal and runs the service's `start_command` from `hub-config.yaml`.

Example: if Terminal Monitor is offline, the button runs:
```powershell
cd C:\...\terminal-monitor && .venv\Scripts\python -m uvicorn termmon.main:app --port 8084
```

---

## Training Status

The AI tab header shows a training pair counter: **`16 / 100 pairs`** with a blue progress bar.

- Source: `models/training_seed.jsonl`
- Threshold: 100 pairs
- When ready: counter turns green and shows **✓ ready to fine-tune**

To run the fine-tune pipeline after hitting 100 pairs:
```powershell
.\models\finetune\rebuild_model.ps1
```
Then restart Ollama to load the updated `ops-brain`.

---

## Model Selector

A **MODEL** dropdown in the CHAT header loads all available Ollama models via `/api/ollama/models`. Your selection persists in localStorage.

Typical options:
- `ops-brain` — fine-tuned ops assistant (default)
- `llama3.2:3b` — base model, no ops system prompt
- `ops-brain-v2` — after your first fine-tune run

---

## Backend Endpoints

| Method | Path | Purpose |
|---|---|---|
| `WS` | `/ws/terminal` | PowerShell command runner |
| `GET` | `/api/training/status` | `{count, threshold, ready}` |
| `GET` | `/api/ollama/models` | List installed Ollama models |

---

## Security Note

`/ws/terminal` executes arbitrary PowerShell as your user account. Terminal Monitor binds to `localhost:8084` only — it is not exposed to the network unless you explicitly change the host binding.
