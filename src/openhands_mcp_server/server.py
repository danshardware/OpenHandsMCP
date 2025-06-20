"""Main MCP server implementation for OpenHands."""

import asyncio
import json
import logging
from typing import Any, Dict

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    ListToolsResult,
    TextContent,
    Tool,
)
from pydantic import AnyUrl

from .session_manager import SessionManager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openhands-mcp-server")

# Initialize session manager
session_manager = SessionManager()

# Create MCP server
server = Server("openhands-mcp-server")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="start_session",
            description="Create a new OpenHands coding session with a git repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "Git repository URL to clone"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch name to checkout (optional, defaults to main)",
                        "default": "main"
                    }
                },
                "required": ["repo_url"]
            }
        ),
        Tool(
            name="code",
            description="Start a coding session with OpenHands AI agent",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from start_session"
                    },
                    "task_description": {
                        "type": "string",
                        "description": "Plain language description of the coding task"
                    }
                },
                "required": ["session_id", "task_description"]
            }
        ),
        Tool(
            name="git",
            description="Execute git commands within a session workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID from start_session"
                    },
                    "command": {
                        "type": "string",
                        "description": "Git command to execute (without 'git' prefix)"
                    }
                },
                "required": ["session_id", "command"]
            }
        ),
        Tool(
            name="teardown",
            description="Clean up a coding session, removing containers and directories",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session ID to teardown"
                    },
                    "archive_changes": {
                        "type": "boolean",
                        "description": "Whether to archive uncommitted changes (default: true)",
                        "default": True
                    }
                },
                "required": ["session_id"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]):
    """Handle tool calls."""
    try:
        if name == "start_session":
            repo_url = arguments["repo_url"]
            branch = arguments.get("branch", "main")
            
            session_id = session_manager.create_session(repo_url, branch)
            session = session_manager.get_session(session_id)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "success": True,
                        "session_id": session_id,
                        "repo_url": session.repo_url,
                        "branch": session.branch,
                        "workspace_path": str(session.workspace_path),
                        "created_at": session.created_at.isoformat()
                    }, indent=2)
                )
            ]
            
        elif name == "code":
            session_id = arguments["session_id"]
            task_description = arguments["task_description"]
            
            # Start coding session (this is async)
            logs = await session_manager.start_coding_session(session_id, task_description)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "success": True,
                        "session_id": session_id,
                        "task_description": task_description,
                        "conversation_log": logs
                    }, indent=2)
                )
            ]
            
        elif name == "git":
            session_id = arguments["session_id"]
            command = arguments["command"]
            
            result = session_manager.execute_git_command(session_id, command)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "session_id": session_id,
                        "command": f"git {command}",
                        **result
                    }, indent=2)
                )
            ]
            
        elif name == "teardown":
            session_id = arguments["session_id"]
            archive_changes = arguments.get("archive_changes", True)
            
            result = session_manager.teardown_session(session_id, archive_changes)
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "session_id": session_id,
                        **result
                    }, indent=2)
                )
            ]
            
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Unknown tool: {name}"
                    })
                )
            ]
            
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}")
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "error": str(e)
                })
            )
        ]


async def main():
    """Main entry point for the server."""
    # Server configuration can be added here
    from mcp.types import ServerCapabilities
    init_options = InitializationOptions(
        server_name="openhands-mcp-server",
        server_version="0.1.0",
        capabilities=ServerCapabilities()
    )
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            init_options
        )


if __name__ == "__main__":
    asyncio.run(main())
