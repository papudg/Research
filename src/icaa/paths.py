"""Repository path constants for the ICAA reproducibility package."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK_REL = Path("docs/qbank_audit/cbse_class_x_maths_questions_full_updated.json")
BANK_PATH = REPO_ROOT / BANK_REL
MANIFEST_DIR = REPO_ROOT / "data" / "manifests"
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
RESULTS_DIR = EXPERIMENTS_DIR


def results_path(name: str) -> Path:
    """Return the canonical path for a result artifact cited by the paper."""
    return RESULTS_DIR / name


def resolve_bank_path(path: str | Path | None = None) -> Path:
    if path is None:
        return BANK_PATH
    candidate = Path(path)
    if not candidate.is_absolute() and candidate.as_posix() == BANK_REL.as_posix():
        return BANK_PATH
    if candidate == BANK_REL:
        return BANK_PATH
    return candidate
