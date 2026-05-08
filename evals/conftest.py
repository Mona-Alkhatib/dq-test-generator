"""Shared helpers for the eval harness."""
from __future__ import annotations

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
