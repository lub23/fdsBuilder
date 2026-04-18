"""pytest fixtures for agent_damage tests."""

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACILITIES_DIR = PROJECT_ROOT / "facilities"


@pytest.fixture(scope="session")
def facilities_dir() -> Path:
    assert FACILITIES_DIR.is_dir(), f"Missing facilities dir: {FACILITIES_DIR}"
    return FACILITIES_DIR


@pytest.fixture(scope="session")
def aerospace_json(facilities_dir: Path) -> Path:
    return facilities_dir / "aerospace.json"


@pytest.fixture(scope="session")
def airport_hangar_json(facilities_dir: Path) -> Path:
    return facilities_dir / "airport_hangar.json"


@pytest.fixture(scope="session")
def machinery_json(facilities_dir: Path) -> Path:
    return facilities_dir / "machinery_manufacturing.json"


@pytest.fixture(scope="session")
def metallurgical_json(facilities_dir: Path) -> Path:
    return facilities_dir / "metallurgical_facilities.json"
