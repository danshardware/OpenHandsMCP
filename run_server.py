#!/usr/bin/env python3
"""Launcher script for OpenHands MCP Server."""

import sys
import argparse
from pathlib import Path
import os

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="OpenHands MCP Server - AI coding environment management"
    )
    parser.add_argument(
        "--sessions-dir",
        default="./sessions",
        help="Directory to store session workspaces (default: ./sessions)"
    )
    parser.add_argument(
        "--archive-dir", 
        default="./archive",
        help="Directory to archive uncommitted changes (default: ./archive)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="What host to bind to (default: localhost)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=6363,
        help="Port to run the server on (default: 6363)"
    )
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    # Set up logging level
    import logging
    logging.basicConfig(level=getattr(logging, args.log_level))
    from src.openhands_mcp_server.server import main
    
    os.environ["MCP_HTTP_HOST"] = args.host
    os.environ["MCP_HTTP_PORT"] = str(args.port)
    
    print(f"Starting OpenHands MCP Server...")
    print(f"Sessions directory: {args.sessions_dir}")
    print(f"Archive directory: {args.archive_dir}")
    print(f"Log level: {args.log_level}")
    print("Connect via stdio or configure your MCP client to use this server.")
    print("Press Ctrl+C to stop the server.")
    
    try:
        main()
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)
