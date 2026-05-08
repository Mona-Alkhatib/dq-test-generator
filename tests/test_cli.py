from typer.testing import CliRunner

from dqgen.cli import app

runner = CliRunner()


def test_cli_help_lists_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "generate" in result.stdout.lower()
