# DQ Test Generator

CLI tool that profiles a DuckDB warehouse table and asks Claude to propose dbt tests, then validates and emits a ready-to-commit `schema.yml` plus a per-test rationale.

> *"Point me at `raw.orders` and tell me which tests catch real bad rows."*

## What it does

1. **Profiles** the table — runs ~5 deterministic SQL queries to capture row count, null rates, distinct counts, numeric ranges, top values for low-cardinality columns.
2. **Asks Claude** for proposed dbt tests in a single call. Claude receives the profile and returns a JSON array of test proposals with rationales.
3. **Validates** every proposal — column must exist, test name must be supported, args must be well-formed. Bad proposals are dropped (and printed) so the YAML is never broken.
4. **Emits** a `schema.yml` to stdout and a `rationale.md` to stderr.

Supported test types:
- `not_null`, `unique`, `accepted_values`, `relationships` (built-in)
- `dbt_utils.accepted_range` (numeric ranges)

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

The eval harness loads each fixture into an ephemeral DuckDB, runs the
full pipeline, and asserts:

- **Catch rate ≥ 0.80** — fraction of planted defects caught
- **False positives = 0** — generated tests must pass on clean data

```bash
uv run pytest evals/ -v
```

(Skipped automatically when `ANTHROPIC_API_KEY` is not set.)

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the three-component pipeline + design choices
- [`docs/EVALS.md`](docs/EVALS.md) — eval harness format, metrics, fixture authoring
- [`docs/superpowers/specs/2026-05-06-dq-test-generator-design.md`](docs/superpowers/specs/2026-05-06-dq-test-generator-design.md) — full spec
- [`docs/superpowers/plans/2026-05-06-dq-test-generator.md`](docs/superpowers/plans/2026-05-06-dq-test-generator.md) — implementation plan

## Tech stack

- **LLM:** Claude Sonnet 4.6 (Anthropic SDK, single-turn JSON via assistant prefill)
- **Profiling / runtime:** DuckDB
- **Types:** Pydantic v2
- **YAML:** PyYAML
- **CLI:** Typer
- **Tests:** pytest
