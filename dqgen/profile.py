"""Deterministic SQL profiling against a DuckDB warehouse.

The profile is the only thing the generator sees about the data. We
build it from a fixed set of queries:
- declared schema (information_schema.columns)
- row count
- per-column null count + distinct count
- per-numeric-column min/max/avg
- per-low-cardinality-column top-5 values

A column qualifies as low-cardinality when its distinct count is ≤ 100
AND distinct/row ratio is ≤ 0.5.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb

from dqgen.models import ColumnProfile, TableProfile

NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT",
    "FLOAT", "DOUBLE", "DECIMAL",
}

LOW_CARDINALITY_DISTINCT_CAP = 100
LOW_CARDINALITY_RATIO_CAP = 0.5
TOP_K = 5


def _is_numeric(dtype: str) -> bool:
    base = dtype.split("(")[0].upper()
    return base in NUMERIC_TYPES


def _is_low_cardinality(distinct_count: int, row_count: int) -> bool:
    if distinct_count <= 0 or distinct_count > LOW_CARDINALITY_DISTINCT_CAP:
        return False
    ratio = (distinct_count / row_count) if row_count else 0.0
    return ratio <= LOW_CARDINALITY_RATIO_CAP


def _columns(con: duckdb.DuckDBPyConnection, schema: str, name: str) -> list[tuple[str, str, bool]]:
    rows = con.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema, name],
    ).fetchall()
    return [(r[0], r[1], r[2] == "YES") for r in rows]


def _numeric_stats(
    con: duckdb.DuckDBPyConnection, qcol: str, qtable: str
) -> tuple[Any, Any, float | None]:
    min_v, max_v, mean_v = con.execute(
        f"SELECT MIN({qcol}), MAX({qcol}), AVG({qcol}) FROM {qtable}"
    ).fetchone()
    return min_v, max_v, (float(mean_v) if mean_v is not None else None)


def _top_values(
    con: duckdb.DuckDBPyConnection, qcol: str, qtable: str
) -> list[tuple[Any, int]]:
    rows = con.execute(
        f"""
        SELECT {qcol}, COUNT(*) AS n
        FROM {qtable}
        WHERE {qcol} IS NOT NULL
        GROUP BY {qcol}
        ORDER BY n DESC, {qcol}
        LIMIT ?
        """,
        [TOP_K],
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _profile_column(
    con: duckdb.DuckDBPyConnection,
    schema: str,
    name: str,
    column: str,
    dtype: str,
    nullable: bool,
    row_count: int,
) -> ColumnProfile:
    qcol = f'"{column}"'
    qtable = f'"{schema}"."{name}"'

    null_count, distinct_count = con.execute(
        f"SELECT COUNT(*) FILTER (WHERE {qcol} IS NULL), COUNT(DISTINCT {qcol}) FROM {qtable}"
    ).fetchone()

    min_v: Any = None
    max_v: Any = None
    mean_v: float | None = None
    if _is_numeric(dtype):
        min_v, max_v, mean_v = _numeric_stats(con, qcol, qtable)

    top_values: list[tuple[Any, int]] = []
    if _is_low_cardinality(distinct_count, row_count):
        top_values = _top_values(con, qcol, qtable)

    return ColumnProfile(
        name=column,
        dtype=dtype,
        nullable=nullable,
        null_count=null_count,
        distinct_count=distinct_count,
        min_value=min_v,
        max_value=max_v,
        mean_value=mean_v,
        top_values=top_values,
    )


def profile_table(warehouse_path: Path, schema: str, name: str) -> TableProfile:
    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        cols = _columns(con, schema, name)
        if not cols:
            raise ValueError(f"table not found: {schema}.{name}")

        row_count = con.execute(f'SELECT COUNT(*) FROM "{schema}"."{name}"').fetchone()[0]

        column_profiles = [
            _profile_column(con, schema, name, col, dtype, nullable, row_count)
            for col, dtype, nullable in cols
        ]

        return TableProfile(
            schema=schema,
            name=name,
            row_count=row_count,
            columns=column_profiles,
        )
    finally:
        con.close()
