"""Shared helpers for the eval harness."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


def fixture_dirs() -> list[Path]:
    return sorted(p for p in FIXTURES_DIR.iterdir() if p.is_dir())


def load_manifest(fixture: Path) -> dict:
    return json.loads((fixture / "manifest.json").read_text())


def load_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows
