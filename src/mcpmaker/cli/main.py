import typer

from mcpmaker.cli.bridge import bridge
from mcpmaker.cli.connect import connect
from mcpmaker.cli.doctor import doctor
from mcpmaker.cli.serve import serve

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_show_locals=False)


@app.callback()
def main() -> None:
    """Turn your FastAPI app into an MCP server and connect it to every AI client."""


app.command()(connect)
app.command()(doctor)
app.command()(bridge)
app.command()(serve)
