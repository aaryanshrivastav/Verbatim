"""Docker runtime abstraction for the Remediation Executor."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol


class RuntimeErrorBase(Exception):
    """Base class for runtime execution failures."""


class ContainerNotFoundError(RuntimeErrorBase):
    """Raised when a container lookup fails."""


@dataclass
class ContainerInfo:
    """Minimal container state returned by the runtime adapter."""

    name: str
    status: str


class DockerRuntime(Protocol):
    """Protocol implemented by real and fake runtimes."""

    def inspect_container(self, container_name: str) -> ContainerInfo:
        """Return current status for a container."""

    def restart_container(self, container_name: str, timeout_seconds: int) -> str:
        """Restart a container and return a status string."""

    def start_container(self, container_name: str) -> str:
        """Start a stopped container and return a status string."""

    def unpause_container(self, container_name: str) -> str:
        """Unpause a paused container and return a status string."""

    def kill_container(self, container_name: str) -> str:
        """Force-kill a container and return a status string."""

    def scale_service(self, compose_service_name: str, replicas: int) -> str:
        """Scale a compose service to the desired replica count."""

    def get_replica_count(self, compose_service_name: str) -> int:
        """Return current number of running replicas for a compose service."""


class SubprocessDockerRuntime:
    """Runs Docker actions through subprocess calls."""

    def __init__(
        self,
        compose_file: str | Path = "docker-compose.yml",
        docker_timeout_seconds: int = 15,
    ) -> None:
        self.compose_file = str(compose_file)
        self.docker_timeout_seconds = docker_timeout_seconds

    def inspect_container(self, container_name: str) -> ContainerInfo:
        status = self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}",
                container_name,
            ]
        ).strip()
        if not status:
            raise ContainerNotFoundError(f"container not found: {container_name}")
        return ContainerInfo(name=container_name, status=status)

    def restart_container(self, container_name: str, timeout_seconds: int) -> str:
        self._run(["docker", "container", "restart", "-t", str(timeout_seconds), container_name])
        return "container restarting"

    def start_container(self, container_name: str) -> str:
        self._run(["docker", "container", "start", container_name])
        return "container started"

    def unpause_container(self, container_name: str) -> str:
        self._run(["docker", "container", "unpause", container_name])
        return "container unpaused"

    def kill_container(self, container_name: str) -> str:
        self._run(["docker", "container", "kill", container_name])
        return "container killed"

    def scale_service(self, compose_service_name: str, replicas: int) -> str:
        self._run(
            [
                "docker",
                "compose",
                "-f",
                self.compose_file,
                "up",
                "-d",
                "--scale",
                f"{compose_service_name}={replicas}",
                "--no-recreate",
            ]
        )
        return f"service scaled to {replicas} replicas"

    def get_replica_count(self, compose_service_name: str) -> int:
        output = self._run(
            [
                "docker",
                "compose",
                "-f",
                self.compose_file,
                "ps",
                "--format",
                "json",
            ]
        )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeErrorBase("unable to parse docker compose ps output") from exc

        if isinstance(payload, dict):
            payload = [payload]
        return sum(1 for item in payload if item.get("Service") == compose_service_name)

    def _run(self, command: List[str]) -> str:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.docker_timeout_seconds,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            if "No such container" in stderr or "No such object" in stderr:
                raise ContainerNotFoundError(stderr)
            raise RuntimeErrorBase(stderr or "docker command failed")
        return completed.stdout


class FakeDockerRuntime:
    """In-memory Docker runtime used by the executor tests."""

    def __init__(
        self,
        containers: Optional[Dict[str, str]] = None,
        replica_counts: Optional[Dict[str, int]] = None,
    ) -> None:
        self.containers = dict(containers or {})
        self.replica_counts = dict(replica_counts or {})
        self.calls: List[tuple[str, str, Optional[int]]] = []

    def inspect_container(self, container_name: str) -> ContainerInfo:
        if container_name not in self.containers:
            raise ContainerNotFoundError(f"container not found: {container_name}")
        return ContainerInfo(name=container_name, status=self.containers[container_name])

    def restart_container(self, container_name: str, timeout_seconds: int) -> str:
        self.calls.append(("restart", container_name, timeout_seconds))
        self.containers[container_name] = "running"
        return "container restarting"

    def start_container(self, container_name: str) -> str:
        self.calls.append(("start", container_name, None))
        self.containers[container_name] = "running"
        return "container started"

    def unpause_container(self, container_name: str) -> str:
        self.calls.append(("unpause", container_name, None))
        self.containers[container_name] = "running"
        return "container unpaused"

    def kill_container(self, container_name: str) -> str:
        self.calls.append(("kill", container_name, None))
        self.containers[container_name] = "exited"
        return "container killed"

    def scale_service(self, compose_service_name: str, replicas: int) -> str:
        self.calls.append(("scale", compose_service_name, replicas))
        self.replica_counts[compose_service_name] = replicas
        return f"service scaled to {replicas} replicas"

    def get_replica_count(self, compose_service_name: str) -> int:
        return self.replica_counts.get(compose_service_name, 1)
