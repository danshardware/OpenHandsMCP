"""Session management for OpenHands MCP server."""

import asyncio
import os
import shutil
import stat
import tempfile
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
    container_id: Optional[str] = None
    created_at: datetime
    status: str = "active"


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
    
    async def start_coding_session(self, session_id: str, task_description: str) -> str:
        """Start an OpenHands coding session"""
        session = self.get_session(session_id)

        if not self.docker_client:
            raise RuntimeError("Docker client not available")

        try:
            container_name = f"openhands-app-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            user_home = str(Path.home())
            # Try to get podman/docker socket path (Linux/WSL/Podman Desktop)
            xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            podman_sock = None
            if xdg_runtime_dir:
                podman_sock = os.path.join(xdg_runtime_dir, "podman/podman.sock")
            else:
                # Fallback for Windows/Mac: use default Docker socket
                podman_sock = os.environ.get("DOCKER_HOST", "/var/run/docker.sock")

            openhands_ver = os.environ.get("OPENHANDS_VER", "0.45")
            runtime_image = f"docker.all-hands.dev/all-hands-ai/runtime:{openhands_ver}-nikolaik"
            openhands_image = f"docker.all-hands.dev/all-hands-ai/openhands:{openhands_ver}"

            volumes = {
                str(session.workspace_path.absolute()): {'bind': '/workspace', 'mode': 'rw'},
                podman_sock: {'bind': '/var/run/docker.sock', 'mode': 'rw'},
                os.path.join(user_home, ".openhands"): {'bind': '/.openhands', 'mode': 'rw'},
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

            extra_hosts = {'host.docker.internal': 'host-gateway'}

            command = [
                "python", "-m", "openhands.core.main", "-t", task_description
            ]

            logger.info(f"Starting OpenHands coding session on container: {container_name}")
            try:
                logger.debug(
                    f"Starting container.\n"
                    f"Image: {openhands_image}\n"
                    f"Command: {command}\n"
                    f"Name: {container_name}\n"
                    f"Volumes: {volumes}\n"
                    f"Environment: {environment}\n"
                    f"Extra hosts: {extra_hosts}\n"
                )
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
            except Exception as e:
                logger.error(
                    f"Failed to start container.\n"
                    f"Image: {openhands_image}\n"
                    f"Command: {command}\n"
                    f"Name: {container_name}\n"
                    f"Volumes: {volumes}\n"
                    f"Environment: {environment}\n"
                    f"Extra hosts: {extra_hosts}\n"
                    f"Error: {e}"
                )
                raise

            session.container_id = container.id
            logger.debug(f"Container {container_name} ({container.id}) started successfully and is '{container.status}'")
            await asyncio.sleep(1)  # Give Docker a moment to stabilize the container state
            container.reload()  # Ensure we have the latest status
            if container.status == 'running':
                logger.info(f"waiting for container: {container_name} ({container.id}) to finish...")
                container.wait()
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')
            logger.info(f"Container {container_name} ({container.id}) finished")
            logger.debug(f"Container {container_name} ({container.id}) logs:\n{logs}")
            
            # check the exit code
            exit_code = container.attrs['State']['ExitCode']
            container.remove()
            if exit_code != 0:
                logger.warning(f"Container {container_name} ({container.id}) exited with code {exit_code}")
                session.status = "failed"
                raise RuntimeError(f"Container exited with code {exit_code}. Logs:\n{logs}")
            session.status = "ok"
            return logs

        except DockerException as e:
            session.status = "failed"
            raise RuntimeError(f"Docker error during coding session: {e}")
        except Exception as e:
            session.status = "failed"
            raise RuntimeError(f"Failed to start coding session: {e}")
    
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
