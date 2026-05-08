# Eval Harness

The eval harness is what turns DQ Test Generator from a *demo that produces plausible YAML* into a *system that catches real bugs*. Each fixture is a known-bad-rows experiment.

## Why this approach

Most LLM-output evals score "did the answer look correct?" — substring matches, BLEU, an LLM judge. That's fine for free-form text; it's the wrong tool for code generation where there's a ground truth (does the test actually catch the bad row?). We can run the generated SQL and observe whether it fires on the planted defects.

This eval design also exposes failure modes one at a time:
- **Low catch rate** → the generator is missing real defects (under-testing)
- **False positives** → the generator is flagging clean data (over-testing)
- **Low test efficiency** → the generator is producing noise

## Fixture layout

```
evals/fixtures/<table>/
├── clean.csv         # N valid rows
├── dirty.csv         # same N + M deliberately bad rows
└── manifest.json     # describes each planted defect
```

`manifest.json`:

```json
{
  "table": "orders",
  "row_count_clean": 10,
  "row_count_dirty": 15,
  "defects": [
    {
      "row_index": 11,
      "column": "id",
      "violation": "duplicate",
      "expected_test": "unique"
    }
  ]
}
```

## Eval flow

For each fixture:

```
1. Load clean.csv → ephemeral DuckDB → profile → Claude → validator → tests
2. Run those tests against clean.csv (DuckDB SQL)
   → Expect zero failures. Any failure = false positive.
3. Run the same tests against dirty.csv
   → For each manifest.defects entry, check whether a matching
     (column, expected_test) caught at least one row.
4. Assert: catch_rate >= 0.80 AND false_positives == 0
```

## Metrics

| Metric | Definition | v1 Threshold |
|---|---|---|
| **Catch rate** | caught defects / planted defects | ≥ 0.80 |
| **False-positive rate** | clean rows flagged / clean rows | = 0.00 |
| **Test efficiency** | caught defects / tests generated | ≥ 0.5 (computed from logs, not asserted) |

## How to run

```bash
# All fixtures
uv run pytest evals/ -v

# Just one fixture
uv run pytest evals/test_evals.py -v -k orders
```

The harness is auto-skipped when `ANTHROPIC_API_KEY` is not set so unit-test runs don't burn API tokens.

## Adding a fixture

1. Create `evals/fixtures/<name>/clean.csv` with a representative happy-path table.
2. Copy it to `dirty.csv` and append rows that violate specific test types.
3. Author `manifest.json` describing each violation: which row, which column, which test type *should* catch it.
4. Run `uv run pytest evals/test_evals.py -v -k <name>` and iterate on either the fixture or the system prompt until the thresholds hold.

## What v1 doesn't measure

- **Latency / token cost per case** — worth adding once we have a baseline.
- **Consistency across runs** — Claude's output is non-zero variance; we may want N runs per fixture and aggregate.
- **Cross-table tests (`relationships`)** — fixtures are single-table; relationships are skipped in eval scoring.
- **Long-tail violations** — the 13 planted defects cover the obvious test types. Adversarial cases (Unicode edge cases, date timezone bugs, very large cardinalities) are v2.

## Future work

- Run each fixture N=3 times, report mean catch rate + variance.
- Track eval scores in a JSON history file and plot per-commit.
- Wire CI to run the full suite on push to `main`.
- Generate fixtures programmatically by mutating real warehouse tables.
