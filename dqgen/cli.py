"""Typer CLI entry point.

One command: `dq-gen generate --warehouse <db> --table <schema.name>`.
Pipes schema.yml to stdout, rationale.md to stderr (so you can pipe just
the YAML into a file).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

app = typer.Typer(no_args_is_help=True)


@app.command()
def generate(
    table: str = typer.Option(..., help="Qualified table name: schema.name"),
    warehouse: Path = typer.Option(..., help="Path to the DuckDB warehouse"),
) -> None:
    """Profile a table, generate dbt tests, emit schema.yml to stdout."""
    load_dotenv()

    if "." not in table:
        typer.echo(f"--table must be qualified (schema.name), got: {table}", err=True)
        raise typer.Exit(2)
    schema, name = table.split(".", 1)

    import anthropic

    from dqgen.emit import emit_rationale, emit_schema_yaml
    from dqgen.generator import generate_proposed_tests
    from dqgen.profile import profile_table
    from dqgen.validator import validate_proposals

    typer.echo(f"Profiling {table}...", err=True)
    profile = profile_table(warehouse, schema, name)

    typer.echo("Calling Claude...", err=True)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    proposals = generate_proposed_tests(profile, client=client)

    typer.echo(f"Validating {len(proposals)} proposals...", err=True)
    valid, rejected = validate_proposals(proposals, profile)

    if rejected:
        typer.echo(f"Rejected {len(rejected)} proposal(s):", err=True)
        for r in rejected:
            typer.echo(f"  - {r.proposal.column}.{r.proposal.test}: {r.reason}", err=True)

    yaml_text = emit_schema_yaml(model_name=name, tests=valid)
    rationale_text = emit_rationale(valid)

    sys.stdout.write(yaml_text)
    sys.stderr.write("\n--- rationale ---\n")
    sys.stderr.write(rationale_text)
