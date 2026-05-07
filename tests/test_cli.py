"""Test CLI commands with Click."""

from click.testing import CliRunner
from cli.main import cli


def test_upload_command_help():
    """Test upload command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["upload", "--help"])
    assert result.exit_code == 0
    assert "upload" in result.output


def test_upload_requires_pdf():
    """Test upload requires a PDF argument."""
    runner = CliRunner()
    result = runner.invoke(cli, ["upload", "--type", "CC"])
    assert result.exit_code == 2


def test_batch_command_help():
    """Test batch command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["batch", "--help"])
    assert result.exit_code == 0
    assert "batch" in result.output


def test_validate_command_help():
    """Test validate command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--help"])
    assert result.exit_code == 0
    assert "validate" in result.output
