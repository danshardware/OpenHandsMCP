# OpenHands MCP Server

A Model Context Protocol (MCP) server that provides tools for managing OpenHands coding environments. This server allows you to create isolated coding sessions, execute git operations, and manage Docker containers for AI-powered coding assistance.

## Features

- **Session Management**: Create and manage isolated coding sessions
- **Git Integration**: Clone repositories, checkout branches, and execute git commands
- **Docker Integration**: Spin up OpenHands containers for AI coding assistance
- **Environment Isolation**: Each session gets its own workspace directory
- **Cleanup**: Automatic teardown with optional archiving of uncommitted changes

## Tools

### start_session
Creates a new coding session with a specified git repository and branch.

**Parameters:**
- `repo_url` (string): Git repository URL to clone
- `branch` (string, optional): Branch name to checkout (defaults to main/master)

**Returns:** Session ID for use with other tools

### code
Initiates a coding session with OpenHands AI agent.

**Parameters:**
- `session_id` (string): Session ID from start_session
- `task_description` (string): Plain language description of the coding task

**Returns:** Conversation log from the AI coding agent

### git
Executes git commands within a session's workspace.

**Parameters:**
- `session_id` (string): Session ID from start_session
- `command` (string): Git command to execute (without 'git' prefix)

**Returns:** Command output and status

### teardown
Cleans up a coding session, removing containers and directories.

**Parameters:**
- `session_id` (string): Session ID to teardown
- `archive_changes` (boolean, optional): Whether to archive uncommitted changes

**Returns:** Cleanup status and archive location if applicable

## Installation

1. Clone this repository
2. Install dependencies: `pip install -e .`
3. Make sure Docker is running
4. Run the server: `openhands-mcp-server`

## Requirements

- Python 3.8+
- Docker
- Git
- OpenHands Docker image

## Configuration

The server uses the following default settings:
- Sessions directory: `./sessions`
- Archive directory: `./archive`
- OpenHands Docker image: `ghcr.io/all-hands-ai/openhands:main`

These can be configured via environment variables or configuration file.
