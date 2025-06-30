# OpenHands MCP Server

A Model Context Protocol (MCP) server that provides tools for managing OpenHands coding environments. This server allows you to create isolated coding sessions, execute git operations, and manage Docker containers for AI-powered coding assistance.

## Features

- **Session Management**: Create and manage isolated coding sessions
- **Git Integration**: Clone repositories, checkout branches, and execute git commands
- **Docker Integration**: Spin up OpenHands containers for AI coding assistance (multiple concurrent tasks per session)
- **Secrets Injection**: Securely inject secrets into session containers via environment variables
- **Environment Isolation**: Each session gets its own workspace directory
- **Cleanup**: Automatic teardown with optional archiving of uncommitted changes
- **Session Listing & Status**: List all sessions and monitor coding task containers

## MCP Tools

### start_session
Creates a new coding session with a specified git repository and branch.

**Parameters:**
- `repo_url` (string): Git repository URL to clone
- `branch` (string, optional): Branch name to checkout (defaults to main/master)

**Returns:** Session ID for use with other tools

### code
Initiates a coding session with the OpenHands AI agent. Supports multiple concurrent coding tasks (containers) per session.

**Parameters:**
- `session_id` (string): Session ID from start_session
- `task_description` (string): Plain language description of the coding task

**Returns:** Container ID and status

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

### list_sessions
Lists all active sessions and their metadata.

**Returns:** Dictionary of session IDs and session info

### get_coding_task_status
Returns status and logs for all coding task containers in a session.

**Parameters:**
- `session_id` (string): Session ID

**Returns:** List of containers with status, logs, and metadata

### cleanup_coding_tasks
Stops and removes all coding task containers for a session.

**Parameters:**
- `session_id` (string): Session ID

**Returns:** Status for each container

## Environment Variables

You can configure the server using the following environment variables:

- `OPENHANDS_VERSION`: OpenHands version (default: `0.45`)
- `OPENHANDS_SANDBOX_VERSION`: Sandbox runtime image (default: uses `OPENHANDS_VERSION`)
- `OPENHANDS_VER`: OpenHands version for container images (default: `0.45`)
- `OPENHANDS_MAX_TASKS`: Maximum concurrent coding tasks (containers) per session (default: `3`)
- `DOCKER_HOST`: Docker socket/host override
- `XDG_RUNTIME_DIR`: Used for Podman socket detection
- `OPENHANDS_SECRET_*`: Any environment variable prefixed with this will be injected as a secret into the session container (e.g., `OPENHANDS_SECRET_GITHUB_TOKEN`)

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
- OpenHands Docker image: `docker.all-hands.dev/all-hands-ai/openhands:<version>`

These can be configured via environment variables as described above.
