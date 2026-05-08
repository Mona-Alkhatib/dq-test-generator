import duckdb
import pytest

from dqgen.profile import profile_table


@pytest.fixture
def warehouse(tmp_path):
    db = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA raw")
    con.execute(
        """
        CREATE TABLE raw.orders (
            id INTEGER NOT NULL,
            user_id INTEGER,
            status VARCHAR,
            amount DOUBLE
        )
        """
    )
    con.executemany(
        "INSERT INTO raw.orders VALUES (?, ?, ?, ?)",
        [
            (1, 10, "placed", 100.0),
            (2, 11, "placed", 50.0),
            (3, 12, "shipped", 200.0),
            (4, 13, "completed", 300.0),
            (5, None, "completed", 75.0),
        ],
    )
    con.close()
    return db


def test_profile_table_records_row_count(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    assert p.row_count == 5


def test_profile_table_lists_columns(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    names = {c.name for c in p.columns}
    assert names == {"id", "user_id", "status", "amount"}


def test_profile_table_records_null_counts(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    user = p.column("user_id")
    assert user.null_count == 1
    id_col = p.column("id")
    assert id_col.null_count == 0


def test_profile_table_records_distinct_counts(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    assert p.column("status").distinct_count == 3
    assert p.column("id").distinct_count == 5


def test_profile_table_records_numeric_minmax(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    amount = p.column("amount")
    assert amount.min_value == 50.0
    assert amount.max_value == 300.0


def test_profile_table_records_top_values_for_low_cardinality(warehouse):
    p = profile_table(warehouse, "raw", "orders")
    status = p.column("status")
    # status has 3 distinct values across 5 rows: ratio = 3/5 = 0.6 > 0.5 → does NOT qualify.
    assert status.top_values == []


def test_profile_table_returns_top_values_when_truly_low_cardinality(tmp_path):
    db = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA s")
    con.execute("CREATE TABLE s.t (x VARCHAR)")
    # 100 rows, 3 distinct values → ratio 0.03, qualifies as low-cardinality.
    rows = [("a",)] * 60 + [("b",)] * 30 + [("c",)] * 10
    con.executemany("INSERT INTO s.t VALUES (?)", rows)
    con.close()

    p = profile_table(db, "s", "t")
    x = p.column("x")
    top = dict(x.top_values)
    assert top == {"a": 60, "b": 30, "c": 10}


def test_profile_table_unknown_table_raises(warehouse):
    with pytest.raises(ValueError, match="not found"):
        profile_table(warehouse, "raw", "nope")
