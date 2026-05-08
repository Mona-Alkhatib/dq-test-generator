import pytest
from pydantic import ValidationError

from dqgen.models import ColumnProfile, ProposedTest, TableProfile, ValidTest


def test_column_profile_basic():
    cp = ColumnProfile(
        name="user_id",
        dtype="INTEGER",
        nullable=False,
        null_count=0,
        distinct_count=100,
    )
    assert cp.name == "user_id"
    assert cp.distinct_to_row_ratio(row_count=100) == 1.0


def test_column_profile_top_values_optional():
    cp = ColumnProfile(name="x", dtype="VARCHAR", nullable=True, null_count=0, distinct_count=5)
    assert cp.top_values == []


def test_table_profile_aggregates_columns():
    tp = TableProfile(
        schema="raw",
        name="orders",
        row_count=100,
        columns=[
            ColumnProfile(name="id", dtype="INTEGER", nullable=False, null_count=0, distinct_count=100),
            ColumnProfile(name="status", dtype="VARCHAR", nullable=False, null_count=0, distinct_count=5),
        ],
    )
    assert tp.qualified_name == "raw.orders"
    assert tp.column("id").distinct_count == 100


def test_proposed_test_must_have_column_and_test():
    with pytest.raises(ValidationError):
        ProposedTest(test="not_null")  # missing column


def test_valid_test_inherits_proposed_fields():
    vt = ValidTest(column="x", test="not_null", args={}, rationale="declared NOT NULL")
    assert vt.column == "x"
