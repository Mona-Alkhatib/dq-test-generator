"""Emit dbt schema.yml and a per-test Markdown rationale.

Tests with no args render in dbt's short form (just the test name).
Tests with args render in the dict form ({test_name: {args...}}).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import yaml

from dqgen.models import ValidTest


def _test_yaml(test: ValidTest) -> str | dict[str, dict[str, Any]]:
    if not test.args:
        return test.test
    return {test.test: dict(test.args)}


def emit_schema_yaml(*, model_name: str, tests: list[ValidTest]) -> str:
    by_column: dict[str, list[ValidTest]] = defaultdict(list)
    for t in tests:
        by_column[t.column].append(t)

    columns_block = [
        {"name": col, "tests": [_test_yaml(t) for t in col_tests]}
        for col, col_tests in by_column.items()
    ]

    doc = {
        "version": 2,
        "models": [
            {
                "name": model_name,
                "columns": columns_block,
            }
        ],
    }
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


def emit_rationale(tests: list[ValidTest]) -> str:
    lines = ["# DQ test rationale", ""]
    for t in tests:
        lines.append(f"- **{t.column}.{t.test}** — {t.rationale}")
    return "\n".join(lines) + "\n"
