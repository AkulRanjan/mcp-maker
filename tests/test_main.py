from mcpmaker.cli.main import app


def test_typer_never_shows_locals_on_crash():
    assert app.pretty_exceptions_show_locals is False
