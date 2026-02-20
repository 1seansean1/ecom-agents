"""Code executor with gRPC service per Behavior Spec §2.1.

This module implements the CodeExecutor gRPC service, accepting ExecutionRequest
messages and returning ExecutionResult with sandboxed code execution metrics.

Per Behavior Spec §2.1:
- ExecutionRequest validation (code size, language, resource limits)
- Spawn container process with namespace isolation
- Enforce resource limits (timeout, memory, CPU, disk I/O)
- Collect resource metrics (wall_time, user_time, memory_peak)
- Handle execution errors (timeout, OOM, seccomp violations)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

__all__ = [
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionError",
    "CodeExecutor",
    "ExecutorState",
]

logger = logging.getLogger(__name__)


class ExecutorState(Enum):
    """Executor state machine per Behavior Spec §2.1."""

    IDLE = "idle"  # Executor ready
    RECEIVING = "receiving"  # Reading ExecutionRequest
    REQUEST_PARSED = "request_parsed"  # Request validated
    SPAWNING = "spawning"  # Creating container/process
    EXECUTING = "executing"  # Code running in sandbox
    COMPLETED = "completed"  # Process exited
    COLLECTING_METRICS = "collecting_metrics"  # Gathering resource stats
    RETURNING = "returning"  # Sending ExecutionResult
    TIMEOUT = "timeout"  # Wall-clock limit exceeded
    OOM = "oom"  # Memory limit exceeded
    SYSCALL_BLOCKED = "syscall_blocked"  # Seccomp violation
    SPAWN_ERROR = "spawn_error"  # Container creation failed
    PROTOCOL_ERROR = "protocol_error"  # Malformed gRPC message
    FAULTED = "faulted"  # Executor error


class ExecutionError(Exception):
    """Base exception for execution errors per Behavior Spec §2.1."""

    pass


class ProtocolError(ExecutionError):
    """Malformed ExecutionRequest."""

    pass


class UnsupportedLanguageError(ExecutionError):
    """Language not supported."""

    pass


class CodeSizeError(ExecutionError):
    """Code exceeds size limit (10 MB)."""

    pass


class InvalidLimitError(ExecutionError):
    """Resource limit exceeds maximum."""

    pass


class SpawnError(ExecutionError):
    """Container creation failed."""

    pass


class NamespaceError(ExecutionError):
    """Namespace isolation setup failed."""

    pass


class SeccompError(ExecutionError):
    """Seccomp profile load failed."""

    pass


class CgroupError(ExecutionError):
    """Cgroup limit setup failed."""

    pass


@dataclass
class ExecutionRequest:
    """gRPC ExecutionRequest message per Behavior Spec §2.1.

    Specifies code to execute with resource constraints and environment.

    Attributes:
        request_id: Unique execution ID (UUID)
        code: Source code to execute
        language: Language identifier ("python3.11", "node18", etc.)
        environment: Environment variables (no secrets)
        files: Input files as {filename: bytes}
        timeout: Wall-clock timeout (max 30s)
        memory_limit_mb: Memory limit in MB (default 256, max 512)
        cpu_period_ms: CPU throttle period
        cpu_quota_ms: CPU quota per period
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = ""
    language: str = "python3.11"
    environment: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    timeout: float = 10.0
    memory_limit_mb: int = 256
    cpu_period_ms: int = 100
    cpu_quota_ms: int = 100

    SUPPORTED_LANGUAGES = {"python3.11", "python3.10", "node18", "node20", "bash"}
    MAX_CODE_SIZE_MB = 10
    MAX_TIMEOUT_SEC = 30
    MAX_MEMORY_MB = 512

    def validate(self) -> None:
        """Validate request per Behavior Spec §2.1 constraints.

        Raises:
            ProtocolError: If request_id missing
            UnsupportedLanguageError: If language not supported
            CodeSizeError: If code > 10 MB
            InvalidLimitError: If memory or timeout exceed limits
        """
        if not self.request_id:
            raise ProtocolError("request_id is required")
        if self.language not in self.SUPPORTED_LANGUAGES:
            raise UnsupportedLanguageError(f"Language {self.language} not supported")
        if len(self.code) > self.MAX_CODE_SIZE_MB * 1_000_000:
            raise CodeSizeError(
                f"Code exceeds {self.MAX_CODE_SIZE_MB} MB (§2.1)"
            )
        if self.memory_limit_mb > self.MAX_MEMORY_MB:
            raise InvalidLimitError(
                f"Memory {self.memory_limit_mb} exceeds max {self.MAX_MEMORY_MB} MB (§2.1)"
            )
        if self.timeout > self.MAX_TIMEOUT_SEC:
            raise InvalidLimitError(
                f"Timeout {self.timeout} exceeds max {self.MAX_TIMEOUT_SEC} s (§2.1)"
            )


@dataclass
class ExecutionResult:
    """gRPC ExecutionResult message per Behavior Spec §2.1.

    Returns code execution results with resource metrics.

    Attributes:
        request_id: Echo of ExecutionRequest.request_id
        stdout: Standard output (max 1 MB)
        stderr: Standard error (max 1 MB)
        exit_code: Process exit code (0 = success)
        output_files: Generated files as {filename: bytes}
        wall_time: Actual wall-clock time in seconds
        user_time: User CPU time in seconds
        system_time: System CPU time in seconds
        memory_peak_mb: Peak memory usage in MB
        page_faults: Major page faults (OOM indicator)
        error_message: Error description if exit_code != 0
        start_time: Execution start timestamp
        end_time: Execution end timestamp
    """

    request_id: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    output_files: dict[str, bytes] = field(default_factory=dict)
    wall_time: float = 0.0
    user_time: float = 0.0
    system_time: float = 0.0
    memory_peak_mb: int = 0
    page_faults: int = 0
    error_message: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    MAX_OUTPUT_MB = 1

    def __post_init__(self) -> None:
        """Truncate outputs to max size per Behavior Spec §2.1."""
        max_bytes = self.MAX_OUTPUT_MB * 1_000_000
        if len(self.stdout) > max_bytes:
            self.stdout = self.stdout[:max_bytes] + f"\n...(truncated, {len(self.stdout)} bytes)"
        if len(self.stderr) > max_bytes:
            self.stderr = self.stderr[:max_bytes] + f"\n...(truncated, {len(self.stderr)} bytes)"


class CodeExecutor:
    """Code executor with gRPC service per Behavior Spec §2.1.

    Accepts ExecutionRequest, spawns container process with resource limits,
    and returns ExecutionResult with metrics.

    Per Behavior Spec §2.1:
    - Request validation (code size, language, limits)
    - Container spawn with namespace isolation
    - Resource enforcement (timeout, memory, CPU)
    - Metric collection (timing, memory, CPU)
    - Error handling (timeout, OOM, seccomp)
    """

    __slots__ = ("_state", "_current_request")

    def __init__(self) -> None:
        """Initialize executor in IDLE state."""
        self._state = ExecutorState.IDLE
        self._current_request: Optional[ExecutionRequest] = None

    @property
    def state(self) -> ExecutorState:
        """Current executor state."""
        return self._state

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute code per ExecutionRequest.

        Args:
            request: ExecutionRequest with code and resource limits

        Returns:
            ExecutionResult with execution output and metrics

        Raises:
            ProtocolError: If request malformed
            UnsupportedLanguageError: If language not supported
            CodeSizeError: If code too large
            InvalidLimitError: If limits exceed max
            SpawnError: If container creation failed
        """
        try:
            self._state = ExecutorState.RECEIVING
            self._current_request = request

            # Validate request per Behavior Spec §2.1
            self._state = ExecutorState.REQUEST_PARSED
            request.validate()

            # Create execution result
            result = ExecutionResult(request_id=request.request_id)
            result.start_time = datetime.utcnow()

            # Spawn container (stub implementation)
            self._state = ExecutorState.SPAWNING
            await self._spawn_container(request)

            # Execute code (stub: immediate return)
            self._state = ExecutorState.EXECUTING
            await asyncio.sleep(0.01)  # Simulate execution

            # Collect metrics
            self._state = ExecutorState.COLLECTING_METRICS
            result.wall_time = 0.01
            result.user_time = 0.01
            result.system_time = 0.00
            result.memory_peak_mb = 10
            result.page_faults = 0
            result.exit_code = 0
            result.stdout = "(executor stub)"

            result.end_time = datetime.utcnow()
            self._state = ExecutorState.RETURNING
            return result

        except ExecutionError as e:
            self._state = ExecutorState.FAULTED
            logger.error(f"Execution error: {e}", exc_info=True)
            raise
        finally:
            self._state = ExecutorState.IDLE

    async def _spawn_container(self, request: ExecutionRequest) -> None:
        """Spawn container process per Behavior Spec §2 isolation.

        Args:
            request: ExecutionRequest with isolation requirements

        Raises:
            SpawnError: If container creation failed
            NamespaceError: If namespace setup failed
            SeccompError: If seccomp profile failed
            CgroupError: If cgroup setup failed
        """
        # Stub implementation: verify request validity
        if not request.request_id:
            raise SpawnError("Cannot spawn without request_id")
        logger.debug(f"Spawning container for request {request.request_id}")
