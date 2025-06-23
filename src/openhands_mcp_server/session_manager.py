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
    
    def __init__(self, sessions_dir: str = "./sessions", archive_dir: str = "./archive"):
        self.sessions_dir = Path(sessions_dir)
        self.archive_dir = Path(archive_dir)
        self.sessions: Dict[str, SessionInfo] = {}
        self.docker_client = None
        
        # Create directories if they don't exist
        self.sessions_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)
        
        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            print(f"Warning: Could not connect to Docker: {e}")
            self.docker_client = None
    
    def create_session(self, repo_url: str, branch: str = "main") -> str:
        """Create a new coding session."""
        session_id = str(uuid.uuid4())
        workspace_path = self.sessions_dir / session_id
        
        try:
            # Create workspace directory
            workspace_path.mkdir(exist_ok=True)
            
            # Clone repository
            print(f"Cloning repository {repo_url}...")
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
                    print(f"Could not checkout/create branch '{branch}', using '{current_branch}'")
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
            
            print(f"Session {session_id} created successfully")
            return session_id
            
        except Exception as e:
            # Cleanup on failure
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            raise RuntimeError(f"Failed to create session: {e}")
    
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
            git_cmd = command_parts[0]
            git_args = command_parts[1:] if len(command_parts) > 1 else []
            
            # Execute the git command
            output = getattr(repo.git, git_cmd)(*git_args)
            
            return {
                "success": True,
                "output": output,
                "error": None
            }
            
        except GitCommandError as e:
            return {
                "success": False,
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
        """Start an OpenHands coding session."""
        session = self.get_session(session_id)
        
        if not self.docker_client:
            raise RuntimeError("Docker client not available")
        
        try:
            # Prepare Docker environment
            container_name = f"openhands-{session_id}"
            
            # Mount the workspace directory
            volumes = {
                str(session.workspace_path.absolute()): {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            }
            
            # Environment variables for OpenHands
            environment = {
                'WORKSPACE_BASE': '/workspace',
                'TASK_DESCRIPTION': task_description,
                'REPO_URL': session.repo_url,
                'BRANCH': session.branch
            }
            
            # Run OpenHands container
            container = self.docker_client.containers.run(
                f"docker.all-hands.dev/all-hands-ai/openhands:${OPENHANDS_VERSION}",
                command=["python", "-m", "openhands.core.main", "-t", task_description],
                name=container_name,
                volumes=volumes,
                environment=environment,
                detach=True,
                remove=True,
                auto_remove=True
            )
            
            session.container_id = container.id
            
            # Wait for container to complete and get logs
            print(f"Starting OpenHands coding session for branch: {session.branch}")
            container.wait()
            
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')
            
            # Update session status
            session.status = "completed"
            
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
