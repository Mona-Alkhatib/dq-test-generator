"""Eval harness: catch-rate / false-positive tests against fixture tables.

For each fixture:
1. Load clean CSV into an ephemeral DuckDB.
2. Run the generator → validator → emit pipeline.
3. Run the generated tests against clean — expect zero failures (no false positives).
4. Run the generated tests against dirty — record which planted defects were caught.
5. Assert catch_rate >= 0.80 and false_positives == 0.

Skipped automatically when ANTHROPIC_API_KEY is not set so unit-test runs
don't pay for API calls.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

from dqgen.generator import generate_proposed_tests
from dqgen.profile import profile_table
from dqgen.validator import validate_proposals
from evals.conftest import HAS_KEY, fixture_dirs, load_csv, load_manifest

CATCH_RATE_THRESHOLD = 0.80


def _load_csv_into_duckdb(db: Path, schema: str, table: str, csv_path: Path) -> None:
    con = duckdb.connect(str(db))
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    con.execute(
        f"CREATE TABLE {schema}.{table} AS SELECT * FROM read_csv_auto('{csv_path}', header=True)"
    )
    con.close()


def _run_test_against(db: Path, schema: str, table: str, vt) -> int:
    """Return number of rows the test catches (i.e. failing rows)."""
    con = duckdb.connect(str(db), read_only=True)
    qt = f'"{schema}"."{table}"'
    qc = f'"{vt.column}"'
    try:
        if vt.test == "not_null":
            sql = f"SELECT COUNT(*) FROM {qt} WHERE {qc} IS NULL"
        elif vt.test == "unique":
            sql = (
                f"SELECT COALESCE(SUM(c - 1), 0) FROM "
                f"(SELECT COUNT(*) AS c FROM {qt} WHERE {qc} IS NOT NULL GROUP BY {qc} HAVING COUNT(*) > 1) sub"
            )
        elif vt.test == "accepted_values":
            values = vt.args["values"]
            placeholders = ", ".join("?" for _ in values)
            sql = (
                f"SELECT COUNT(*) FROM {qt} "
                f"WHERE {qc} IS NOT NULL AND {qc} NOT IN ({placeholders})"
            )
            return con.execute(sql, values).fetchone()[0]
        elif vt.test == "dbt_utils.accepted_range":
            clauses = []
            params: list = []
            if "min_value" in vt.args:
                clauses.append(f"{qc} < ?")
                params.append(vt.args["min_value"])
            if "max_value" in vt.args:
                clauses.append(f"{qc} > ?")
                params.append(vt.args["max_value"])
            sql = f"SELECT COUNT(*) FROM {qt} WHERE {qc} IS NOT NULL AND ({' OR '.join(clauses)})"
            return con.execute(sql, params).fetchone()[0]
        elif vt.test == "relationships":
            # Skip relationships in eval harness — fixtures are single-table.
            return 0
        else:
            return 0
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


@pytest.mark.skipif(not HAS_KEY, reason="ANTHROPIC_API_KEY not configured")
@pytest.mark.parametrize("fixture", fixture_dirs(), ids=lambda p: p.name)
def test_fixture(fixture: Path, tmp_path: Path):
    import anthropic

    manifest = load_manifest(fixture)
    table = manifest["table"]
    schema = "test"

    clean_db = tmp_path / "clean.duckdb"
    dirty_db = tmp_path / "dirty.duckdb"
    _load_csv_into_duckdb(clean_db, schema, table, fixture / "clean.csv")
    _load_csv_into_duckdb(dirty_db, schema, table, fixture / "dirty.csv")

    profile = profile_table(clean_db, schema, table)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    proposals = generate_proposed_tests(profile, client=client)
    valid, _ = validate_proposals(proposals, profile)

    # 1) False-positive check: tests must pass on clean data.
    fp_failures = sum(_run_test_against(clean_db, schema, table, vt) for vt in valid)
    assert fp_failures == 0, f"{fixture.name}: {fp_failures} false positive(s) on clean data"

    # 2) Catch-rate check: count caught defects.
    defects = manifest["defects"]
    caught = 0
    for defect in defects:
        for vt in valid:
            if vt.column != defect["column"]:
                continue
            if vt.test != defect["expected_test"]:
                continue
            if _run_test_against(dirty_db, schema, table, vt) > 0:
                caught += 1
                break

    catch_rate = caught / len(defects)
    assert catch_rate >= CATCH_RATE_THRESHOLD, (
        f"{fixture.name}: catch rate {catch_rate:.2f} below {CATCH_RATE_THRESHOLD}\n"
        f"  defects: {len(defects)}, caught: {caught}\n"
        f"  generated tests: {[(t.column, t.test) for t in valid]}"
    )
