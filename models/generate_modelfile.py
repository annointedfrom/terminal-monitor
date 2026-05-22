"""
Buyer setup helper: reads hub-config.yaml and writes a personal Modelfile
from Modelfile.template by filling in {{AGENT_BLOCK}}.

Usage:
    python models/generate_modelfile.py
    ollama create ops-brain -f models/Modelfile.generated
"""

import pathlib
import sys

try:
    import yaml
except ImportError:
    print("pyyaml not installed.  Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

MODELS_DIR = pathlib.Path(__file__).parent
HUB_CONFIG = MODELS_DIR.parent.parent / "agent-hub" / "hub-config.yaml"
TEMPLATE = MODELS_DIR / "Modelfile.template"
OUTPUT = MODELS_DIR / "Modelfile.generated"


def build_agent_block(config: dict) -> str:
    agents = config.get("agents", [])
    lines = []
    for agent in agents:
        name = agent.get("name", "unknown")
        port = agent.get("port", "?")
        start = agent.get("start_cmd", "")
        lines.append(f"- {name} on port {port}" + (f" — start: {start}" if start else ""))
    return "\n".join(lines) if lines else "No agents configured."


def main() -> None:
    if not HUB_CONFIG.exists():
        print(f"hub-config.yaml not found at {HUB_CONFIG}", file=sys.stderr)
        print("Edit HUB_CONFIG path in this script if your config lives elsewhere.")
        sys.exit(1)

    config = yaml.safe_load(HUB_CONFIG.read_text(encoding="utf-8"))
    agent_block = build_agent_block(config)

    template = TEMPLATE.read_text(encoding="utf-8")
    output = template.replace("{{AGENT_BLOCK}}", agent_block)

    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Written: {OUTPUT}")
    print("Next step:  ollama create ops-brain -f models/Modelfile.generated")


if __name__ == "__main__":
    main()
