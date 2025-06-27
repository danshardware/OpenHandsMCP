"""Session management for OpenHands MCP server."""

import os
import shutil
import stat
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import docker
import git
from docker.errors import DockerException
from git.exc import GitCommandError
from pydantic import BaseModel

import logging
# Set up logging
logger = logging.getLogger("openhands-mcp-server")

OPENHANDS_VERSION = os.environ.get("OPENHANDS_VERSION", "0.45")
OPENHANDS_SANDBOX_VERSION = os.environ.get("OPENHANDS_SANDBOX_VERSION", f"docker.all-hands.dev/all-hands-ai/runtime:${OPENHANDS_VERSION}-nikolaik")

class SessionInfo(BaseModel):
    """Information about a coding session."""
    
    session_id: str
    repo_url: str
    branch: str
    workspace_path: Path
    # Track multiple coding task containers per session
    coding_task_containers: list = []  # List of dicts: [{"id": str, "status": str, "created_at": datetime}]
    created_at: datetime
    status: str = "active"
    # Deprecated: container_id (for backward compatibility, can be removed later)
    container_id: Optional[str] = None


class SessionManager:
    """Manages OpenHands coding sessions."""
    
    def import_existing_session(self, session_id: str):
        """Import an existing session from the sessions directory, updating or creating the SessionInfo."""
        session_path = self.sessions_dir / session_id
        if not session_path.exists() or not session_path.is_dir():
            logger.warning(f"Session directory {session_path} does not exist.")
            return
        try:
            repo = git.Repo(session_path)
            branch = repo.active_branch.name
            repo_url = next(repo.remote().urls)
        except Exception as e:
            logger.error(f"Failed to import session {session_id}: {e}")
            return
        created_at = datetime.fromtimestamp(session_path.stat().st_mtime)
        session_info = SessionInfo(
            session_id=session_id,
            repo_url=repo_url,
            branch=branch,
            workspace_path=session_path,
            created_at=created_at
        )
        self.sessions[session_id] = session_info
        logger.info(f"Imported session {session_id} from {session_path}")

    def _import_all_existing_sessions(self):
        """Scan the sessions directory and import all valid session folders."""
        for entry in self.sessions_dir.iterdir():
            if entry.is_dir():
                try:
                    uuid.UUID(entry.name)
                    self.import_existing_session(entry.name)
                except ValueError:
                    continue

    def _get_docker_host(self):
        # 1. Use DOCKER_HOST if set
        docker_host = os.environ.get("DOCKER_HOST")
        if docker_host:
            return docker_host
        # 2. Try default Unix sockets in order
        candidates = [
            "/var/run/docker.sock",
            "/var/run/podman.sock",
        ]
        xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime_dir:
            candidates.append(os.path.join(xdg_runtime_dir, "podman/podman.sock"))
        for sock in candidates:
            if os.path.exists(sock) and os.access(sock, os.W_OK):
                logger.debug(f"Using Docker socket: {sock}")
                return f"unix://{sock}"
        logger.warning("No valid Docker socket found. Using default settings.")
        return None

    def __init__(self, sessions_dir: str = "./sessions", archive_dir: str = "./archive"):
        self.sessions_dir = Path(sessions_dir)
        self.archive_dir = Path(archive_dir)
        self.sessions: Dict[str, SessionInfo] = {}
        self.docker_client = None
        
        # Create directories if they don't exist
        self.sessions_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)
        
        # Initialize Docker client with robust socket detection
        try:
            docker_host = self._get_docker_host()
            if docker_host:
                # Temporarily override DOCKER_HOST for docker.from_env
                old_docker_host = os.environ.get("DOCKER_HOST")
                os.environ["DOCKER_HOST"] = docker_host
                try:
                    self.docker_client = docker.from_env()
                finally:
                    # Restore previous DOCKER_HOST if it was not set
                    if old_docker_host is None:
                        del os.environ["DOCKER_HOST"]
                    else:
                        os.environ["DOCKER_HOST"] = old_docker_host
            else:
                self.docker_client = docker.from_env()
        except DockerException as e:
            logger.warning(f"Could not connect to Docker: {e}")
            self.docker_client = None
        try:
            self._import_all_existing_sessions()
            logger.info(f"Imported {len(self.sessions)} existing sessions from {self.sessions_dir}")
        except Exception as e:
            logger.warning(f"Failed to import existing sessions: {e}")
            # Continue without existing sessions if import fails
            self.sessions = {}
            
    def _prepare_secrets_for_session(self, workspace_path: Path) -> Optional[str]:
        """Prepare secrets file in workspace for sandbox container access."""
        secrets_file = workspace_path / ".openhands_secrets"
        
        # Collect secrets from host environment (prefixed for security)
        secrets = {}
        for key, value in os.environ.items():
            if key.startswith('OPENHANDS_SECRET_'):
                # Strip prefix: OPENHANDS_SECRET_GITHUB_TOKEN -> GITHUB_TOKEN
                secret_name = key[17:]  # Remove 'OPENHANDS_SECRET_' prefix
                secrets[secret_name] = value
        
        if secrets:
            # Write secrets as shell exports for easy sourcing
            with open(secrets_file, 'w') as f:
                f.write("#!/bin/bash\n")
                f.write("# Auto-generated secrets file - DO NOT COMMIT\n")
                for key, value in secrets.items():
                    # Escape single quotes in values
                    escaped_value = value.replace("'", "'\"'\"'")
                    f.write(f"export {key}='{escaped_value}'\n")
            
            # Restrict file permissions (owner read-only)
            os.chmod(secrets_file, 0o600)
            
            # Also create .gitignore entry to prevent committing secrets
            gitignore_path = workspace_path / ".gitignore"
            gitignore_entry = ".openhands_secrets\n"
            
            if gitignore_path.exists():
                with open(gitignore_path, 'r') as f:
                    content = f.read()
                if gitignore_entry.strip() not in content:
                    with open(gitignore_path, 'a') as f:
                        f.write(gitignore_entry)
            else:
                with open(gitignore_path, 'w') as f:
                    f.write(gitignore_entry)
            
            logger.info(f"Prepared {len(secrets)} secrets for workspace")
            return str(secrets_file)
        
        return None
    
    def create_session(self, repo_url: str, branch: str = "main") -> str:
        """Create a new coding session."""
        session_id = str(uuid.uuid4())
        workspace_path = self.sessions_dir / session_id
        
        try:
            # Create workspace directory
            workspace_path.mkdir(exist_ok=True)
            
            # Clone repository
            logger.info(f"Cloning repository {repo_url}...")
            repo = git.Repo.clone_from(repo_url, workspace_path)
            
            # Checkout branch
            try:
                repo.git.checkout(branch)
            except GitCommandError:
                # Branch might not exist, try to create it
                try:
                    repo.git.checkout("-b", branch)
                except GitCommandError:
                    # If that fails, stick with current branch
                    current_branch = repo.active_branch.name
                    logger.warning(f"Could not checkout/create branch '{branch}', using '{current_branch}'")
                    branch = current_branch
            
            # Create session info
            session_info = SessionInfo(
                session_id=session_id,
                repo_url=repo_url,
                branch=branch,
                workspace_path=workspace_path,
                created_at=datetime.now()
            )
            
            self.sessions[session_id] = session_info
            
            logger.info(f"Session {session_id} created successfully")
            return session_id
            
        except Exception as e:
            # Cleanup on failure
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            raise RuntimeError(f"Failed to create session: {e}")
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session with the given session_id exists."""
        return session_id in self.sessions
    
    def get_session(self, session_id: str) -> SessionInfo:
        """Get session information."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        return self.sessions[session_id]
    
    def execute_git_command(self, session_id: str, command: str) -> dict:
        """Execute a git command in the session workspace."""
        session = self.get_session(session_id)
        
        try:
            repo = git.Repo(session.workspace_path)
            
            # Use getattr to call git commands dynamically
            command_parts = command.split()
            if command_parts[0] == "git":
                command_parts = command_parts[1:]
            
            allowed_commands = ["add", "commit", "push", "pull", "status", "checkout", "branch", "log", "diff"]
            if command_parts[0] not in allowed_commands:
                raise ValueError(f"Command '{command_parts[0]}' is not allowed in this context. Allowed commands: {', '.join(allowed_commands)}")
            git_cmd = command_parts[0]
            git_args = command_parts[1:] if len(command_parts) > 1 else []
            
            # Execute the git command
            output = getattr(repo.git, git_cmd)(*git_args)
            
            logger.debug(f"Executed git command '{command}' in session {session_id}: {output}")
            
            # Update the session status
            self.import_existing_session(session_id)
            
            return {
                "success": True,
                "isError": False,
                "output": output,
                "error": None
            }
            
        except GitCommandError as e:
            return {
                "success": False,
                "isError": True,
                "output": e.stdout if e.stdout else "",
                "error": e.stderr if e.stderr else str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
    
    async def start_coding_session(self, session_id: str, task_description: str) -> dict:
        """Start an OpenHands coding session (asynchronous, tracks multiple containers)."""
        session = self.get_session(session_id)

        # Limit concurrent coding task containers per session
        max_tasks = int(os.environ.get("OPENHANDS_MAX_TASKS", 3))
        
        # Remove finished containers from tracking
        if self.docker_client:
            still_running = []
            for c in session.coding_task_containers:
                try:
                    container = self.docker_client.containers.get(c["id"])
                    container.reload()
                    if container.status in ("created", "running", "paused"):
                        still_running.append(c)
                except Exception:
                    continue
            session.coding_task_containers = still_running
        if len(session.coding_task_containers) >= max_tasks:
            return {"isError": True, "error": f"Max coding tasks ({max_tasks}) already running for this session."}

        if not self.docker_client:
            return {"isError": True, "error": "Docker client not available"}

        try:
            # Prepare secrets file in workspace
            secrets_file = self._prepare_secrets_for_session(session.workspace_path)
            
            container_name = f"openhands-app-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            user_home = str(Path.home())
            xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            podman_sock = os.path.join(xdg_runtime_dir, "podman/podman.sock") if xdg_runtime_dir else os.environ.get("DOCKER_HOST", "/var/run/docker.sock")
            openhands_ver = os.environ.get("OPENHANDS_VER", "0.45")
            runtime_image = f"docker.all-hands.dev/all-hands-ai/runtime:{openhands_ver}-nikolaik"
            openhands_image = f"docker.all-hands.dev/all-hands-ai/openhands:{openhands_ver}"
            volumes = {
                str(session.workspace_path.absolute()):{'bind': '/workspace', 'mode': 'rw'},
                podman_sock:{'bind': '/var/run/docker.sock', 'mode': 'rw'},
                os.path.join(user_home, ".openhands"):{'bind': '/.openhands', 'mode': 'rw'},
            }
            environment = {
                'SANDBOX_RUNTIME_CONTAINER_IMAGE': runtime_image,
                'SANDBOX_VOLUMES': f"{session.workspace_path.absolute()}:/workspace",
                'LLM_API_KEY': 'ollama',
                'LLM_MODEL': 'ollama/devstral:latest',
                'LOG_ALL_EVENTS': 'true',
                'LLM_BASE_URL': 'http://host.docker.internal:11434',
                'WORKSPACE_BASE': '/workspace',
                'TASK_DESCRIPTION': task_description,
                'REPO_URL': session.repo_url,
                'BRANCH': session.branch
            }
            
            # Add secrets configuration if secrets file exists
            if secrets_file:
                environment['OPENHANDS_SECRETS_FILE'] = '/workspace/.openhands_secrets'
                # Tell OpenHands to source secrets in sandbox initialization
                environment['SANDBOX_USER_DATA_FOLDER'] = '/workspace'
                # Add startup command to source secrets
                startup_cmd = f"[ -f /workspace/.openhands_secrets ] && source /workspace/.openhands_secrets; "
                environment['SANDBOX_STARTUP_CMD'] = startup_cmd
            
            extra_hosts = {'host.docker.internal': 'host-gateway'}
            command = ["python", "-m", "openhands.core.main", "-t", task_description]
            
            logger.info(f"Starting OpenHands coding session on container: {container_name}")
            if secrets_file:
                logger.info(f"Secrets file prepared at: {secrets_file}")
            
            container = self.docker_client.containers.run(
                openhands_image,
                command=command,
                name=container_name,
                volumes=volumes,
                environment=environment,
                extra_hosts=extra_hosts,
                detach=True,
                auto_remove=False
            )
            # Track the new container
            session.coding_task_containers.append({
                "id": container.id,
                "name": container_name,
                "created_at": datetime.now(),
                "status": "created",
                "task_description": task_description
            })
            logger.debug(f"Container {container_name} ({container.id}) started successfully.")
            return {"isError": False, "container": container.id}
        except Exception as e:
            logger.error(f"Failed to start coding task container: {e}")
            return {"isError": True, "error": str(e)}
    
    def teardown_session(self, session_id: str, archive_changes: bool = True) -> dict:
        """Teardown a coding session."""
        if session_id not in self.sessions:
            return {"success": False, "error": f"Session {session_id} not found"}
        
        session = self.sessions[session_id]
        result = {"success": True, "archived": False, "archive_path": None}
        
        try:
            # Stop and remove container if running
            if session.container_id and self.docker_client:
                try:
                    container = self.docker_client.containers.get(session.container_id)
                    container.stop()
                    container.remove()
                except DockerException:
                    # Container might already be stopped/removed
                    pass
            
            # Check for uncommitted changes
            if archive_changes and session.workspace_path.exists():
                try:
                    repo = git.Repo(session.workspace_path)
                    if repo.is_dirty() or repo.untracked_files:
                        # Archive the changes
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        archive_name = f"{session_id}_{timestamp}"
                        archive_path = self.archive_dir / archive_name
                        
                        shutil.copytree(session.workspace_path, archive_path)
                        result["archived"] = True
                        result["archive_path"] = str(archive_path)
                except Exception as e:
                    print(f"Warning: Could not check for uncommitted changes: {e}")
            
            # Remove workspace directory with retry for Windows file locking
            if session.workspace_path.exists():
                try:
                    shutil.rmtree(session.workspace_path)
                except PermissionError:
                    # On Windows, sometimes files are locked, try to force remove
                    def handle_remove_readonly(func, path, exc):
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    
                    shutil.rmtree(session.workspace_path, onerror=handle_remove_readonly)
            
            # Remove session from manager
            del self.sessions[session_id]
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_sessions(self) -> Dict[str, SessionInfo]:
        """List all active sessions."""
        return self.sessions.copy()
    
    def get_coding_task_status(self, session_id: str) -> dict:
        """Return status and logs for all coding task containers in a session."""
        session = self.get_session(session_id)
        results = []
        if not self.docker_client:
            return {"isError": True, "error": "Docker client not available"}
        for c in session.coding_task_containers:
            try:
                container = self.docker_client.containers.get(c["id"])
                container.reload()
                status = container.status
                try:
                    logs = container.logs(stdout=True, stderr=True, tail=1000).decode('utf-8')
                except Exception:
                    logs = ""
                results.append({
                    "id": c["id"],
                    "name": c.get("name"),
                    "status": status,
                    "created_at": str(c.get("created_at")),
                    "task_description": c.get("task_description"),
                    "logs": logs
                })
            except Exception as e:
                results.append({
                    "id": c["id"],
                    "name": c.get("name"),
                    "status": "unknown",
                    "created_at": str(c.get("created_at")),
                    "task_description": c.get("task_description"),
                    "logs": "",
                    "error": str(e)
                })
        return {"isError": False, "tasks": results}
    
    def cleanup_coding_tasks(self, session_id: str) -> dict:
        """Stop and remove all coding task containers for a session."""
        session = self.get_session(session_id)
        if not self.docker_client:
            return {"isError": True, "error": "Docker client not available"}
        results = []
        for c in session.coding_task_containers:
            try:
                container = self.docker_client.containers.get(c["id"])
                container.stop()
                container.remove()
                results.append({"id": c["id"], "status": "removed"})
            except Exception as e:
                results.append({"id": c["id"], "status": "error", "error": str(e)})
        session.coding_task_containers = []
        return {"isError": False, "results": results}
