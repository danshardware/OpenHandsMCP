#!/usr/bin/env python3
"""Simple validation script for the OpenHands MCP Server."""

import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    print("🔍 Validating OpenHands MCP Server...")
    
    try:
        # Test 1: Import session manager
        print("1. Testing SessionManager import...")
        from src.openhands_mcp_server.session_manager import SessionManager
        print("   ✅ SessionManager imported successfully")
        
        # Test 2: Import server components
        print("2. Testing MCP server imports...")
        from src.openhands_mcp_server.server import server, handle_list_tools, handle_call_tool
        print("   ✅ MCP server components imported successfully")
        
        # Test 3: Test basic SessionManager functionality
        print("3. Testing SessionManager initialization...")
        sm = SessionManager(sessions_dir="./test_validation", archive_dir="./test_validation_archive")
        print("   ✅ SessionManager initialized successfully")
        
        # Test 4: Test tool listing
        print("4. Testing tool definitions...")
        import asyncio
        async def test_tools():
            tools = await handle_list_tools()
            return len(tools)
        
        tool_count = asyncio.run(test_tools())
        print(f"   ✅ Found {tool_count} MCP tools")
        
        print("\n🎉 All validation tests passed!")
        print("\nYour OpenHands MCP Server is ready to use!")
        print("\nTo start the server, run:")
        print("   python run_server.py")
        print("\nTo test with a real session, run:")
        print("   python test_server.py")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
