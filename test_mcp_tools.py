#!/usr/bin/env python3
"""Test MCP tools functionality."""

import asyncio
import json
import sys
from pathlib import Path
from mcp.types import TextContent

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.openhands_mcp_server.server import handle_list_tools, handle_call_tool


async def test_mcp_tools():
    """Test the MCP tools functionality."""
    print("Testing OpenHands MCP Tools...")
    
    try:
        # Test 1: List tools
        print("\n1. Testing list_tools...")
        tools_list = await handle_list_tools()  # This returns list[Tool] directly
        print(f"Found {len(tools_list)} tools:")
        for tool in tools_list:  # Iterate directly over the list
            print(f"  - {tool.name}: {tool.description}")
          # Test 2: Test start_session tool
        print("\n2. Testing start_session tool...")
        session_result = await handle_call_tool(
            name="start_session",
            arguments={
                "repo_url": "https://github.com/octocat/Hello-World.git",
                "branch": "main"
            }
        )
        
        # Convert result to list and get first content item
        result_list = list(session_result)
        if result_list and isinstance(result_list[0], TextContent):
            session_data = json.loads(result_list[0].text)
            if session_data.get("success"):
                session_id = session_data["session_id"]
                print(f"✅ Session created: {session_id}")
            else:
                print(f"❌ start_session failed: {session_data}")
                return
        else:
            print("❌ Unexpected result format from start_session")
            return

        print("\n✅ All MCP tool tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ MCP tool test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())
