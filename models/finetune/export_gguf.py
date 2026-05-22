"""
Export a LoRA checkpoint to GGUF and register it with Ollama.

Usage:
    python export_gguf.py --track personal   # -> ops-brain
    python export_gguf.py --track shippable  # -> ops-brain-base (for buyers)

Requires:
    - llama.cpp built at LLAMA_CPP_DIR (or on PATH as convert_hf_to_gguf.py)
    - Ollama installed and running
"""

import argparse
import pathlib
import shutil
import subprocess
import sys

MODELS_DIR = pathlib.Path(__file__).parent.parent
CHECKPOINTS = {
    "personal": MODELS_DIR / "checkpoints" / "personal" / "final",
    "shippable": MODELS_DIR / "checkpoints" / "shippable" / "final",
}
GGUF_OUT = {
    "personal": MODELS_DIR / "ops-brain.gguf",
    "shippable": MODELS_DIR / "ops-brain-base.gguf",
}
OLLAMA_NAME = {
    "personal": "ops-brain",
    "shippable": "ops-brain-base",
}
MODELFILE = {
    "personal": MODELS_DIR / "Modelfile",
    "shippable": MODELS_DIR / "Modelfile.template",
}

# llama.cpp convert script — adjust if built at a custom path
_LLAMA_CPP_CONVERT = shutil.which("convert_hf_to_gguf.py") or shutil.which(
    "convert_hf_to_gguf"
)


def find_convert_script() -> str:
    env_path = pathlib.Path(
        __file__
    ).parent.parent.parent.parent / "llama.cpp" / "convert_hf_to_gguf.py"
    if env_path.exists():
        return str(env_path)
    if _LLAMA_CPP_CONVERT:
        return _LLAMA_CPP_CONVERT
    print(
        "ERROR: convert_hf_to_gguf.py not found.\n"
        "Build llama.cpp and place it at <project>/../llama.cpp/ or add it to PATH.",
        file=sys.stderr,
    )
    sys.exit(1)


def run(cmd: list[str], **kwargs) -> None:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--track",
        choices=["personal", "shippable"],
        default="personal",
        help="Which checkpoint to export",
    )
    args = parser.parse_args()

    checkpoint = CHECKPOINTS[args.track]
    gguf_path = GGUF_OUT[args.track]
    ollama_name = OLLAMA_NAME[args.track]
    modelfile_path = MODELFILE[args.track]

    if not checkpoint.exists():
        print(f"Checkpoint not found: {checkpoint}", file=sys.stderr)
        print(
            f"Run train_{'personal' if args.track == 'personal' else 'shippable'}.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    convert = find_convert_script()

    print(f"\n[1/3] Converting {checkpoint} -> {gguf_path}")
    run(
        [
            sys.executable, convert,
            str(checkpoint),
            "--outfile", str(gguf_path),
            "--outtype", "q4_k_m",
        ]
    )

    if not gguf_path.exists():
        print("ERROR: GGUF file not created.", file=sys.stderr)
        sys.exit(1)

    print(f"\n[2/3] Writing Modelfile FROM {gguf_path.name}")
    if args.track == "personal":
        # Patch existing Modelfile to point at new GGUF
        mf_text = modelfile_path.read_text(encoding="utf-8")
        mf_text = mf_text.splitlines()
        mf_text[0] = f"FROM ./{gguf_path.name}"
        patched = MODELS_DIR / "Modelfile.gguf"
        patched.write_text("\n".join(mf_text), encoding="utf-8")
        create_from = patched
    else:
        # Modelfile.template already uses a placeholder FROM line
        create_from = modelfile_path

    print(f"\n[3/3] ollama create {ollama_name}")
    run(
        ["ollama", "create", ollama_name, "-f", str(create_from)],
        cwd=str(MODELS_DIR),
    )

    print(f"\nDone. Test with:  ollama run {ollama_name}")


if __name__ == "__main__":
    main()
