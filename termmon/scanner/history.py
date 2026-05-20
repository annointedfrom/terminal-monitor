from __future__ import annotations

import json
import pathlib

_DATA_DIR = pathlib.Path(__file__).parent.parent.parent / "data"
_SCAN_PATH = _DATA_DIR / "scan_history.jsonl"
_RESOURCE_PATH = _DATA_DIR / "resource_history.jsonl"
_CAP = 500


def _append(path: pathlib.Path, entry: dict) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    lines: list[str] = []
    if path.exists():
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    lines.append(json.dumps(entry, ensure_ascii=False))
    if len(lines) > _CAP:
        lines = lines[-_CAP:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load(path: pathlib.Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines[-n:]]


def append_scan(entry: dict) -> None:
    _append(_SCAN_PATH, entry)


def append_resource(entry: dict) -> None:
    _append(_RESOURCE_PATH, entry)


def load_scan_history(n: int = 30) -> list[dict]:
    return _load(_SCAN_PATH, n)


def load_resource_history(n: int = 30) -> list[dict]:
    return _load(_RESOURCE_PATH, n)
