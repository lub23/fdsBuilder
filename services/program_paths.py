"""Read/write configured external program paths used by the UI."""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "program_paths.json"


def load_program_paths(config_file: Path = CONFIG_FILE) -> dict[str, str]:
    """Load all configured program paths, returning `{}` on missing/bad files."""

    if not config_file.exists():
        return {}
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_program_path(program: str, config_file: Path = CONFIG_FILE) -> str:
    """Load one configured program path."""

    value = load_program_paths(config_file).get(program, "")
    return value if isinstance(value, str) else ""


def save_program_path(program: str, path: str, config_file: Path = CONFIG_FILE) -> None:
    """Persist one configured program path."""

    paths = load_program_paths(config_file)
    paths[program] = path
    config_file.write_text(
        json.dumps(paths, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
