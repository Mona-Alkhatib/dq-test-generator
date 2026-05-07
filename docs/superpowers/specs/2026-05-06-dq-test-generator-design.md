# DQ Test Generator — Design Spec

**Date:** 2026-05-06
**Author:** Mona Alkhatib (with Claude Code)
**Status:** Approved (brainstorming → writing-plans)

---

## 1. Vision

**DQ Test Generator** points at a warehouse table and produces a complete dbt test suite for it. Profile the data, ask Claude to propose tests, validate the proposals, emit a ready-to-commit `schema.yml` plus a per-test rationale.

Where Lineage Oracle is a *read* tool that answers questions about a warehouse, DQ Test Generator is a *write* tool that ships code into one. Together they show the AI engineering surface for both directions of the data engineering loop.

### Example interaction

```
$ dq-gen --warehouse jaffle_shop.duckdb --table raw.orders > orders_schema.yml
$ cat orders_schema.yml
version: 2
models:
  - name: raw_orders
    columns:
      - name: id
        tests: [not_null, unique]
      - name: status
        tests:
          - not_null
          - accepted_values:
              values: [placed, shipped, completed, returned, return_pending]
      - name: order_date
        tests:
          - not_null
          - dbt_utils.accepted_range:
              max_value: "{{ run_started_at }}"
```

Plus a Markdown rationale per test:

> **`raw_orders.status` accepted_values** — observed 5 distinct values across 99 non-null rows. No new values appeared in 30 days of profile data; high confidence this is a closed enum.

---

## 2. Goals & non-goals

### Goals (v1)

1. Generate dbt tests for a single table from one CLI command.
2. Cover four built-in test types (`not_null`, `unique`, `accepted_values`, `relationships`) and the `dbt_utils.accepted_range` extension.
3. Validate every generated test against the actual schema before emitting — no broken YAML, no references to missing columns.
4. Ship an eval harness that measures real catch rate against fixture tables with deliberately-planted bad rows.
5. Produce both `schema.yml` and a per-test Markdown rationale.

### Non-goals (v1)

- Project-wide scanning / batch mode (separate v2 wrapper around the v1 atomic op).
- Custom singular SQL tests (`tests/*.sql`). Hard to evaluate; different project shape.
- Cross-table tests beyond `relationships` foreign keys.
- Interactive accept/reject UX. Not yet.
- Bring-your-own-warehouse (Snowflake, BigQuery). DuckDB only for v1.

---

## 3. Architecture

Three components in a strict pipeline. Profiling is deterministic, generation is the only LLM step, validation is deterministic.

```
warehouse + table  →  Profiler  →  TableProfile  →  Generator  →  ProposedTest[]
                                                                        ↓
                                                                   Validator
                                                                        ↓
                                                                   ValidTest[]
                                                                        ↓
                                                                     Emit  →  schema.yml + rationale.md
```

### 3.1 Profiler — deterministic SQL

Runs ~5 queries per table, packs results into a `TableProfile` Pydantic model.

| Query | Purpose |
|---|---|
| `SELECT COUNT(*) FROM table` | row count |
| `SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE ...` | declared schema |
| Per column: `SELECT COUNT(*), COUNT(DISTINCT col), COUNT(*) FILTER(WHERE col IS NULL)` | null rate, distinct count |
| Per numeric column: `SELECT MIN(col), MAX(col), AVG(col)` | range stats |
| Per low-cardinality column: `SELECT col, COUNT(*) GROUP BY col ORDER BY 2 DESC LIMIT 5` | top-5 most common values |

A column qualifies as "low-cardinality" when its distinct count is ≤ 100 **and** distinct/row ratio is ≤ 0.5. Both conditions must hold so we don't waste a top-K query on a 100-row table where every value is unique.

### 3.2 Generator — single Claude call, structured JSON

- Input: `TableProfile`
- Single Claude Sonnet 4.6 call
- System prompt instructs it to act as a dbt testing expert and to return ONLY a JSON array of test proposals
- Uses **JSON output via prefill** (`{"role": "assistant", "content": "["}`) to force structured output
- Output schema (one element per proposed test):

```json
{
  "column": "status",
  "test": "accepted_values",
  "args": {"values": ["placed", "shipped", "completed", "returned", "return_pending"]},
  "rationale": "Observed 5 distinct values..."
}
```

The generator does NOT make multiple turns or use tool calls. One profile in, one JSON list out. Simpler to test, simpler to eval, much cheaper per run.

### 3.3 Validator — deterministic sanity checks

Each proposed test passes through three checks:

1. **Column exists** — `proposal.column` is present in the profile's schema.
2. **Test name is supported** — one of `not_null`, `unique`, `accepted_values`, `relationships`, `dbt_utils.accepted_range`.
3. **Args match the test** — e.g. `accepted_values` must have a `values` list; `accepted_range` must have at least one of `min_value`/`max_value`; `relationships` must have `to` and `field`.

Failed proposals are dropped; the rationale is preserved in a separate "rejected proposals" log so users can debug LLM mistakes.

### 3.4 Emit — JSON → dbt formats

- `schema.yml` rendered via PyYAML with stable key ordering matching dbt conventions
- `rationale.md` rendered as a flat list of `column.test — rationale` lines

---

## 4. Eval strategy

The killer differentiator. Evals measure whether generated tests *actually catch real bad data*, not just whether they look plausible.

### 4.1 Fixture format

Each fixture is a directory:

```
evals/fixtures/orders/
├── clean.csv         # N valid rows
├── dirty.csv         # N+M rows: same N valid + M deliberately bad
├── manifest.json     # describes each planted defect
```

`manifest.json`:

```json
{
  "table": "orders",
  "row_count_clean": 100,
  "row_count_dirty": 105,
  "defects": [
    {"row_index": 100, "column": "id", "violation": "duplicate", "expected_test": "unique"},
    {"row_index": 101, "column": "status", "violation": "unknown_value", "expected_test": "accepted_values"},
    {"row_index": 102, "column": "amount", "violation": "negative", "expected_test": "dbt_utils.accepted_range"},
    {"row_index": 103, "column": "user_id", "violation": "null", "expected_test": "not_null"},
    {"row_index": 104, "column": "order_date", "violation": "future", "expected_test": "dbt_utils.accepted_range"}
  ]
}
```

### 4.2 Eval run for a single fixture

```
1. Load clean.csv into ephemeral DuckDB
2. dq-gen against clean → ProposedTest list
3. Run those tests against clean → expect zero failures (if any fail, false positive)
4. Load dirty.csv into ephemeral DuckDB
5. Run the same tests against dirty → record which planted defects were caught
6. Compare caught vs manifest.defects
```

### 4.3 Three metrics

| Metric | Formula | Threshold (v1) |
|---|---|---|
| **Catch rate** | rows-caught / total-planted-defects | ≥ 0.80 |
| **False-positive rate** | clean-rows-flagged / total-clean-rows | = 0.00 |
| **Test efficiency** | defects-caught / tests-generated | ≥ 0.5 |

### 4.4 Seed fixture set

3 fixture tables, derived from jaffle_shop with synthetic defects:

- **orders** — 5 defects covering uniqueness, accepted_values, range
- **customers** — 4 defects covering not_null, uniqueness, range
- **payments** — 4 defects covering relationships, accepted_values, range

Total: 13 planted defects across 3 fixtures.

### 4.5 Runner

`pytest evals/test_evals.py -v` — one parametrized case per fixture. Skips automatically if `ANTHROPIC_API_KEY` is not set.

---

## 5. Project layout

```
dq-test-generator/
├── dqgen/                       # library — single source of truth
│   ├── __init__.py
│   ├── profile.py               # TableProfile + SQL profiling
│   ├── generator.py             # Claude prompt + structured JSON parsing
│   ├── validator.py             # column/test/args sanity checks
│   ├── emit.py                  # JSON → schema.yml + rationale.md
│   ├── models.py                # Pydantic types: ColumnProfile, TableProfile, ProposedTest, ValidTest
│   └── cli.py                   # Typer CLI
├── data/
│   └── jaffle_shop/             # vendored jaffle_shop_duckdb dbt project + build script
│       ├── dbt_project/         # copied from dbt-labs/jaffle_shop_duckdb (gitignored target/)
│       └── build_warehouse.py   # produces jaffle_shop.duckdb (gitignored)
├── evals/
│   ├── fixtures/
│   │   ├── orders/{clean.csv,dirty.csv,manifest.json}
│   │   ├── customers/{...}
│   │   └── payments/{...}
│   ├── conftest.py
│   └── test_evals.py
├── tests/                       # unit tests mirror dqgen/
├── pyproject.toml               # uv + ruff + hatchling
├── .env.example
├── .gitignore
├── README.md
└── docs/
    ├── ARCHITECTURE.md
    ├── EVALS.md
    └── superpowers/
        ├── specs/2026-05-06-dq-test-generator-design.md
        └── plans/2026-05-06-dq-test-generator.md  (next)
```

**Responsibility split:**

- `profile.py` — deterministic, no LLM
- `generator.py` — only file that talks to Claude
- `validator.py` — deterministic, no I/O beyond the profile object
- `emit.py` — pure formatting, no logic
- `cli.py` — orchestrates the four above

---

## 6. Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Matches Lineage Oracle's stack |
| LLM | Claude Sonnet 4.6 (Anthropic SDK) | Smart enough, cheap enough for evals |
| LLM pattern | Single-turn JSON via assistant prefill | Deterministic, debuggable, no tool-use ceremony |
| Profiling | DuckDB SQL | Fits the demo warehouse natively |
| Schema validation | Pydantic v2 | Strong types throughout the pipeline |
| YAML emission | PyYAML | Standard, stable |
| CLI | Typer | Same as Lineage Oracle |
| Test framework | pytest | Same |
| Package mgr | uv | Same |
| Lint/format | ruff | Same |
| Build backend | hatchling | Same — entry point packaging |

No tool-use loop. No agent. No vector store. No graph.

---

## 7. Error handling

- **Table not found / empty:** profile returns a zero-row profile; generator emits `not_null` on declared NOT-NULL columns and stops with a warning. Never crashes.
- **Claude returns malformed JSON:** wrap parsing in `pydantic.ValidationError`. On failure, log the raw response and exit with a clear message. Never emit partial / broken YAML.
- **Validator rejects every proposed test:** print the rejection log + the raw proposals so the user can see what Claude tried.
- **API failures (Claude):** rely on the Anthropic SDK's built-in retries; surface a clean error after exhaustion.
- **DuckDB errors during profiling:** propagate with the offending column / SQL.

---

## 8. Testing strategy

### 8.1 Unit tests (`tests/`)

- `test_profile.py` — fixture DuckDBs of varying shapes; assert profile values match.
- `test_generator.py` — mocked Anthropic client returning canned JSON responses; assert parsing handles well-formed and malformed cases.
- `test_validator.py` — table-driven: feed the validator a list of `(proposal, profile, expected_pass)` cases.
- `test_emit.py` — JSON → YAML round-trip; key ordering; idempotency.
- `test_cli.py` — Typer test client, `--help` and basic command shape.

Target ≥ 90% line coverage on `dqgen/` (excluding `cli.py`'s glue).

### 8.2 Integration test

End-to-end on a single fixture table with a mocked Claude client returning a known-good JSON list. Exercises the full pipeline path without touching the live API.

### 8.3 Eval harness (`evals/`)

The fixture-driven catch-rate / false-positive evals described in §4. Skipped automatically when `ANTHROPIC_API_KEY` is not configured.

---

## 9. Open questions / future work

- **Bring-your-own-warehouse:** v2 abstraction over DuckDB / Snowflake / BigQuery / Postgres.
- **Project-wide scan:** v2 wrapper that loops the v1 atomic op across every model in a dbt project, with `git diff` of changes.
- **Interactive review mode:** v2 TUI that lets users accept / reject / edit each proposed test.
- **Cross-table relationships inference:** v2 — currently we only emit `relationships` if it's obvious from naming; a future version could profile foreign-key candidates.
- **Custom singular SQL tests:** v2 — generates `tests/*.sql` files for business rules (orders.amount = sum of payments.amount).
- **Cardinality / range drift alerts:** v3 — diff today's profile against last week's, flag drifts.

---

## 10. Success criteria for v1

The project is "shippable to portfolio" when:

1. `uv sync && dq-gen --warehouse data/jaffle_shop/dbt_project/jaffle_shop.duckdb --table main.raw_orders` produces a valid `schema.yml` from a fresh clone.
2. Every test in the emitted YAML references a real column and uses a supported test type (validator never bypassed).
3. `pytest evals/ -v` passes all 3 fixtures with catch rate ≥ 0.80 and zero false positives.
4. README walks through quickstart, architecture, evals.
5. Repo deployed to https://github.com/Mona-Alkhatib/dq-test-generator.
