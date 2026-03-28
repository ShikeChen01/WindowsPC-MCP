"""Entry point for the WindowsMCP Custom server."""

import click
from fastmcp import FastMCP
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Initialize and clean up server components."""
    yield


mcp = FastMCP(
    name="windowsmcp-custom",
    instructions=(
        "WindowsMCP Custom provides tools to interact with a confined virtual display. "
        "The agent operates on a dedicated virtual screen and cannot interact with the "
        "user's physical screens. Use CreateScreen to set up the agent display first."
    ),
    lifespan=lifespan,
)


@click.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--host", default="localhost", type=str)
@click.option("--port", default=8000, type=int)
def main(transport: str, host: str, port: int):
    """Start the WindowsMCP Custom server."""
    mcp.run(transport=transport, host=host, port=port, show_banner=False)


if __name__ == "__main__":
    main()
