"""One-time setup: produce data/jaffle_shop/dbt_project/jaffle_shop.duckdb.

Run manually after cloning the repo:
    cd data/jaffle_shop/dbt_project
    dbt seed --profiles-dir .
    dbt run --profiles-dir .

The resulting jaffle_shop.duckdb is git-ignored.
"""
import subprocess
from pathlib import Path

PROJECT = Path(__file__).parent / "dbt_project"


def main():
    subprocess.run(["dbt", "seed", "--profiles-dir", "."], cwd=PROJECT, check=True)
    subprocess.run(["dbt", "run", "--profiles-dir", "."], cwd=PROJECT, check=True)


if __name__ == "__main__":
    main()
