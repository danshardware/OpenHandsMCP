#!/usr/bin/env python3
"""Test script for OpenHands MCP Server."""

import asyncio
import json
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


if __name__ == "__main__":
    asyncio.run(test_session_manager())
