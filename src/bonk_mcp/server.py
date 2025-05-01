import asyncio

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Import the tools
from bonk_mcp.tools import token_launcher_tool, token_buyer_tool, birdeye_trending_tokens_tool, birdeye_top_traders_tool

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}

server = Server("bonk-mcp")


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        return notes[name]
    raise ValueError(f"Note not found: {name}")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        token_launcher_tool.get_tool_definition(),
        token_buyer_tool.get_tool_definition(),
        birdeye_trending_tokens_tool.get_tool_definition(),
        birdeye_top_traders_tool.get_tool_definition()
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if name == "launch-token":
        if not arguments:
            raise ValueError("Missing arguments for launch-token")
        # Execute the token launcher tool
        return await token_launcher_tool.execute(arguments)
    elif name == "buy-token":
        if not arguments:
            raise ValueError("Missing arguments for buy-token")
        # Execute the token buyer tool
        return await token_buyer_tool.execute(arguments)
    elif name == "birdeye-trending-tokens":
        # Execute the BirdEye trending tokens tool (no parameters needed)
        return await birdeye_trending_tokens_tool.execute({})
    elif name == "birdeye-top-traders":
        # Execute the BirdEye top traders tool
        return await birdeye_top_traders_tool.execute(arguments or {})
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="bonk-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
