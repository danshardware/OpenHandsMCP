"""Main MCP server implementation for OpenHands."""

import asyncio
import json
import logging
import os
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
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

# Replace low-level Server with FastMCP
mcp = FastMCP("openhands-mcp-server")

# Register tools using FastMCP decorators
@mcp.tool()
def start_session(repo_url: str, branch: str = "main") -> dict:
    """Create a new OpenHands coding session with a git repository."""
    session_id = session_manager.create_session(repo_url, branch)
    session = session_manager.get_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "repo_url": session.repo_url,
        "branch": session.branch,
        "workspace_path": str(session.workspace_path),
        "created_at": session.created_at.isoformat()
    }

@mcp.tool()
async def code(session_id: str, task_description: str) -> dict:
    """Start a coding session with OpenHands AI agent. Use this tool for any commands that require executing any commands in the session workspace."""
    if not session_manager.session_exists(session_id):
        return {
            "success": False,
            "isError": True,
            "error": "Session not found",
            "session_id": session_id
        }
    logs = await session_manager.start_coding_session(session_id, task_description)
    return {
        "success": True,
        "isError": False,
        "session_id": session_id,
        "task_description": task_description,
        "text": logs
    }

@mcp.tool()
def git(session_id: str, command: str) -> dict:
    """Execute git commands within a session workspace."""
    result = session_manager.execute_git_command(session_id, command)
    return {
        "session_id": session_id,
        "command": f"git {command}",
        **result
    }

@mcp.tool()
def teardown(session_id: str, archive_changes: bool = True) -> dict:
    """Clean up a coding session, removing containers and directories."""
    result = session_manager.teardown_session(session_id, archive_changes)
    return {
        "session_id": session_id,
        **result
    }


def main():
    # Read HTTP port from environment or use default
    http_port = int(os.environ.get("MCP_HTTP_PORT", 6363))
    mcp.settings.port = http_port
    mcp.settings.host = os.environ.get("MCP_HTTP_HOST", "localhost")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
