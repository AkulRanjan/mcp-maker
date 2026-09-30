import typer

from mcpmaker.cli.connect import connect
from mcpmaker.cli.doctor import doctor

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Turn your FastAPI app into an MCP server and connect it to every AI client."""


app.command()(connect)
app.command()(doctor)
