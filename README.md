# DQ Test Generator

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Sonnet%204.6-D97757?logo=anthropic&logoColor=white)
![dbt](https://img.shields.io/badge/dbt-Compatible-FF694A?logo=dbt&logoColor=white)
![Data Quality](https://img.shields.io/badge/Data-Quality-2ea44f)
![Structured Gen](https://img.shields.io/badge/Structured-Generation-8A2BE2)

CLI tool that profiles a DuckDB warehouse table and asks Claude to propose dbt tests, then validates and emits a ready-to-commit `schema.yml` plus a per-test rationale.

> *"Point me at `raw.orders` and tell me which tests catch real bad rows."*

## What it does

1. **Profiles** the table: runs ~5 deterministic SQL queries to capture row count, null rates, distinct counts, numeric ranges, top values for low-cardinality columns.
2. **Asks Claude** for proposed dbt tests in a single call. Claude receives the profile and returns a JSON array of test proposals with rationales.
3. **Validates** every proposal: column must exist, test name must be supported, args must be well-formed. Bad proposals are dropped (and printed) so the YAML is never broken.
4. **Emits** a `schema.yml` to stdout and a `rationale.md` to stderr.

Supported test types:
- `not_null`, `unique`, `accepted_values`, `relationships` (built-in)
- `dbt_utils.accepted_range` (numeric ranges)

## Before → After

**Before** (typical hand-written stub for `raw.orders`):

```yaml
version: 2
models:
  - name: raw_orders
    columns:
      - name: id
      - name: user_id
      - name: status
      - name: amount
```

**After** (`dq-gen generate --table main.raw_orders > raw_orders_schema.yml`):

```yaml
version: 2
models:
  - name: raw_orders
    columns:
      - name: id
        tests:
          - not_null
          - unique
      - name: user_id
        tests:
          - not_null
          - relationships:
              to: ref('stg_users')
              field: id
      - name: status
        tests:
          - not_null
          - accepted_values:
              values: ['pending', 'shipped', 'returned', 'refunded']
      - name: amount
        tests:
          - not_null
          - dbt_utils.accepted_range:
              min_value: 0
              max_value: 10000
```

Every generated test comes with a rationale grounded in the profile (e.g. *"amount ranged 0.50 to 4,832.10 across 1.2M rows; accepted_range prevents future negatives or clearly-broken magnitudes"*).

## Pairs with dbt-sentinel

[dbt-sentinel](https://github.com/Mona-Alkhatib/dbt-sentinel) flags **missing** tests during PR review. This tool **writes** those tests from the warehouse profile. Use them together:

1. Sentinel catches `models/marts/fct_orders.sql` shipping without `unique` on the primary key.
2. Run `dq-gen generate --table main.fct_orders` to propose the full test block.
3. Paste the block into `schema.yml`, commit, re-review clean.

## Quickstart

```bash
# 1. Install
uv sync

# 2. Configure API key
cp .env.example .env
# Edit .env to add ANTHROPIC_API_KEY

# 3. Build the demo warehouse
cd data/jaffle_shop/dbt_project
dbt seed --profiles-dir . && dbt run --profiles-dir .
cd ../../..

# 4. Generate tests for one table
uv run dq-gen generate \
  --warehouse data/jaffle_shop/dbt_project/jaffle_shop.duckdb \
  --table main.raw_orders \
  > raw_orders_schema.yml
```

## Eval results

The eval harness loads each fixture into an ephemeral DuckDB, runs the full pipeline, and asserts:

- **Catch rate ≥ 0.80**: fraction of planted defects caught
- **False positives = 0**: generated tests must pass on clean data

```bash
uv run pytest evals/ -v
```

(Skipped automatically when `ANTHROPIC_API_KEY` is not set.)

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): the three-component pipeline + design choices
- [`docs/EVALS.md`](docs/EVALS.md): eval harness format, metrics, fixture authoring
- [`docs/superpowers/specs/2026-05-06-dq-test-generator-design.md`](docs/superpowers/specs/2026-05-06-dq-test-generator-design.md): full spec
- [`docs/superpowers/plans/2026-05-06-dq-test-generator.md`](docs/superpowers/plans/2026-05-06-dq-test-generator.md): implementation plan

## Tech stack

- **LLM:** Claude Sonnet 4.6 (Anthropic SDK, single-turn JSON via assistant prefill)
- **Profiling / runtime:** DuckDB
- **Types:** Pydantic v2
- **YAML:** PyYAML
- **CLI:** Typer
- **Tests:** pytest

---

**Part of my Data + AI Reliability suite:**
[lineage-oracle](https://github.com/Mona-Alkhatib/lineage-oracle) · [dbt-sentinel](https://github.com/Mona-Alkhatib/dbt-sentinel) · [dq-test-generator](https://github.com/Mona-Alkhatib/dq-test-generator) · [dq-watchdog](https://github.com/Mona-Alkhatib/dq-watchdog)

If DQ Test Generator saved you a schema.yml headache, please give it a ⭐.
