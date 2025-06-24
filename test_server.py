#!/usr/bin/env python3
"""Test script for OpenHands MCP Server."""

import asyncio
import json
import requests
from pathlib import Path

from src.openhands_mcp_server.session_manager import SessionManager


async def test_session_manager():
    """Test the session manager functionality."""
    print("Testing OpenHands MCP Server Session Manager...")
    
    # Initialize session manager with test directories
    test_dir = Path("./test_sessions")
    archive_dir = Path("./test_archive")
    
    session_manager = SessionManager(
        sessions_dir=str(test_dir),
        archive_dir=str(archive_dir)
    )
    
    session_id = None
    try:
        # Test 1: Create a session
        print("\n1. Testing session creation...")
        repo_url = "https://github.com/octocat/Hello-World.git"
        session_id = session_manager.create_session(repo_url, "main")
        print(f"Created session: {session_id}")
        
        # Test 2: Get session info
        print("\n2. Testing session info retrieval...")
        session_info = session_manager.get_session(session_id)
        print(f"Session info: {session_info.model_dump()}")
        
        # Test 3: Execute git command
        print("\n3. Testing git command execution...")
        git_result = session_manager.execute_git_command(session_id, "status")
        print(f"Git status result: {json.dumps(git_result, indent=2)}")
        
        # Test 4: List sessions
        print("\n4. Testing session listing...")
        sessions = session_manager.list_sessions()
        print(f"Active sessions: {len(sessions)}")
        
        # Test 5: Teardown session
        print("\n5. Testing session teardown...")
        teardown_result = session_manager.teardown_session(session_id, archive_changes=True)
        print(f"Teardown result: {json.dumps(teardown_result, indent=2)}")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        
        # Cleanup on failure
        try:
            if session_id is not None and session_id in session_manager.sessions:
                session_manager.teardown_session(session_id, archive_changes=False)
        except:
            pass


async def test_http_endpoint():
    print("\nTesting MCP HTTP endpoint (start_session tool)...")
    url = "http://localhost:6363/mcp"  # Use the root /mcp endpoint for JSON-RPC
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call_tool",
        "params": {
            "name": "start_session",
            "arguments": {
                "repo_url": "https://github.com/octocat/Hello-World.git",
                "branch": "main"
            }
        }
    }
    try:
        headers = {"Accept": "application/json, text/event-stream"}
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"HTTP status: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get("result", {}).get("success"):
                print("✅ HTTP tool call succeeded!")
            else:
                print("❌ HTTP tool call failed: ", data)
        else:
            print("❌ HTTP request failed")
    except Exception as e:
        print(f"❌ Exception during HTTP test: {e}")


async def test_list_tools_http():
    print("\nTesting MCP HTTP endpoint (list_tools)...")
    url = "http://localhost:6363/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "list_tools",
        "params": {}
    }
    try:
        headers = {"Accept": "application/json, text/event-stream"}
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"HTTP status: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            data = response.json()
            print("Available tools:")
            print(json.dumps(data, indent=2))
        else:
            print("❌ HTTP request failed")
    except Exception as e:
        print(f"❌ Exception during HTTP list_tools test: {e}")


async def test_mcp_client():
    print("\nTesting MCP HTTP endpoint using official MCP client...")
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    url = "http://localhost:6363/mcp"
    try:
        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # List tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print(f"Tools available via MCP client: {tool_names}")

                # 1. start_session
                print("\nTesting start_session tool...")
                start_result = await session.call_tool("start_session", {"repo_url": "https://github.com/octocat/Hello-World.git", "branch": "main"})
                print(f"start_session result: {start_result}")
                session_id = None
                # Extract session_id from result
                for content in getattr(start_result, 'content', []):
                    if hasattr(content, 'text'):
                        try:
                            data = json.loads(content.text)
                            session_id = data.get("session_id")
                        except Exception:
                            pass
                if not session_id:
                    print("❌ Could not extract session_id from start_session result!")
                    return

                # 2. code
                print("\nTesting code tool...")
                code_result = await session.call_tool("code", {"session_id": session_id, "task_description": "Print Hello World in Python"})
                print(f"code result: {code_result}")

                # 3. git
                print("\nTesting git tool...")
                git_result = await session.call_tool("git", {"session_id": session_id, "command": "status"})
                print(f"git result: {git_result}")

                # 4. teardown
                print("\nTesting teardown tool...")
                teardown_result = await session.call_tool("teardown", {"session_id": session_id, "archive_changes": True})
                print(f"teardown result: {teardown_result}")

    except Exception as e:
        print(f"❌ MCP client test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_mcp_client())
