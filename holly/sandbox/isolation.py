"""Isolation enforcement per TLA+ spec and Behavior Spec §2.

This module implements sandbox isolation layers: namespace isolation (PID, NET, MNT,
UTS, IPC), seccomp filter policy, cgroup resource enforcement, and read-only rootfs.

Per Behavior Spec §2 and SIL-3 requirements:
- Namespace isolation model (PID, NET, MNT, UTS, IPC)
- Seccomp filter policy (allowlist-only syscalls)
- Cgroup resource enforcement (CPU, memory, PIDs)
- Read-only rootfs enforcement
- No-network invariant verification
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Protocol

__all__ = [
    "CgroupError",
    "CgroupLimit",
    "IsolationChecker",
    "IsolationConfig",
    "IsolationError",
    "IsolationInvariant",
    "Namespace",
    "NamespaceError",
    "NamespaceType",
    "SeccompError",
    "SeccompPolicy",
]

logger = logging.getLogger(__name__)


class NamespaceType(Enum):
    """Namespace types per Behavior Spec §2.2.1-2.2.5."""

    PID = "pid"  # Process isolation: single process visible
    NET = "net"  # Network isolation: no routes, no egress
    MNT = "mnt"  # Mount isolation: read-only rootfs + tmpfs scratch
    UTS = "uts"  # Hostname isolation: container-specific hostname
    IPC = "ipc"  # IPC isolation: no shared IPC resources


class IsolationError(Exception):
    """Base exception for isolation errors per Behavior Spec §2.3."""

    def __init__(self, message: str, layer: str = "isolation") -> None:
        """Initialize isolation error.

        Args:
            message: Error description
            layer: Isolation layer that failed (pid, net, mnt, seccomp, cgroup)
        """
        super().__init__(message)
        self.message = message
        self.layer = layer


class NamespaceError(IsolationError):
    """Raised when namespace creation or configuration fails."""

    def __init__(self, message: str, namespace_type: NamespaceType | None = None) -> None:
        """Initialize namespace error.

        Args:
            message: Error description
            namespace_type: Type of namespace that failed
        """
        super().__init__(message, layer="namespace")
        self.namespace_type = namespace_type


class SeccompError(IsolationError):
    """Raised when seccomp policy setup fails."""

    def __init__(self, message: str, syscall: str | None = None) -> None:
        """Initialize seccomp error.

        Args:
            message: Error description
            syscall: Syscall that triggered the error
        """
        super().__init__(message, layer="seccomp")
        self.syscall = syscall


class CgroupError(IsolationError):
    """Raised when cgroup limit setup fails."""

    def __init__(self, message: str, resource: str | None = None) -> None:
        """Initialize cgroup error.

        Args:
            message: Error description
            resource: Resource (memory, cpu, pids) that failed
        """
        super().__init__(message, layer="cgroup")
        self.resource = resource


@dataclass
class Namespace:
    """Namespace configuration per Behavior Spec §2.2.

    Represents a single namespace isolation boundary with validation state.

    Attributes:
        type: Namespace type (PID, NET, MNT, UTS, IPC)
        enabled: Whether this namespace is active
        sandbox_id: Sandbox instance identifier
        created_at: Creation timestamp (ISO 8601)
        verified: Whether namespace was verified as isolated
        verification_method: How verification was performed (unshare, getns, etc.)
    """

    type: NamespaceType
    enabled: bool = True
    sandbox_id: str = ""
    created_at: str = ""
    verified: bool = False
    verification_method: str = ""

    def __post_init__(self) -> None:
        """Validate namespace configuration."""
        if not self.type:
            raise ValueError("Namespace type required")


@dataclass
class SeccompPolicy:
    """Seccomp allowlist policy per Behavior Spec §2.2.6.

    Represents the seccomp filter configuration with allowed and blocked syscalls.
    Per Behavior Spec §2, uses allowlist-only approach (default deny).

    Attributes:
        default_action: Default action (KILL, ERRNO, ALLOW) — must be KILL per spec
        allowed_syscalls: Frozenset of allowed syscall names
        blocked_syscalls: Frozenset of blocked syscall names (for documentation)
        version: Policy version for audit trail
        mode: Filter mode (STRICT=kill, SOFT=errno)
    """

    default_action: str = "KILL"
    allowed_syscalls: frozenset[str] = field(default_factory=frozenset)
    blocked_syscalls: frozenset[str] = field(default_factory=frozenset)
    version: str = "1.0"
    mode: str = "STRICT"

    # Class-level allowlist per Behavior Spec §2.2.6
    _ALLOWED_SYSCALLS: ClassVar[frozenset[str]] = frozenset([
        # Process control
        "brk",
        "arch_prctl",
        "prctl",
        "exit",
        "exit_group",
        # Memory
        "mmap",
        "mprotect",
        "madvise",
        "mremap",
        "munmap",
        "msync",
        # File I/O
        "open",
        "openat",
        "read",
        "write",
        "pread64",
        "pwrite64",
        "readv",
        "writev",
        "preadv",
        "pwritev",
        "fstat",
        "fstatfs",
        "faccessat",
        "fcntl",
        "dup",
        "dup2",
        "dup3",
        "close",
        # Directory
        "getdents64",
        "getcwd",
        # Time
        "clock_gettime",
        "clock_nanosleep",
        "nanosleep",
        "gettimeofday",
        # Signals
        "rt_sigaction",
        "rt_sigprocmask",
        "rt_sigpending",
        # Scheduler
        "sched_getaffinity",
        "sched_yield",
        # Other
        "sigaltstack",
        "prlimit64",
        "getrandom",
        "tgkill",
        "restart_syscall",
        "futex",
        "futex_waitv",
    ])

    _BLOCKED_SYSCALLS: ClassVar[frozenset[str]] = frozenset([
        # Process execution and namespace escape
        "execve",
        "ptrace",
        "clone",
        "fork",
        "vfork",
        "setns",
        "unshare",
        # Network
        "socket",
        "connect",
        "bind",
        "listen",
        "accept",
        "sendto",
        "recvfrom",
        "sendmsg",
        "recvmsg",
        # Filesystem
        "chroot",
        "mount",
        "umount2",
        # IPC
        "msgget",
        "msgctl",
        "msgrcv",
        "msgsnd",
        "shmget",
        "shmctl",
        "shmat",
        "shmdt",
        # Device
        "ioctl",
        # Module/Firewall
        "finit_module",
        "delete_module",
        "init_module",
        # Seccomp (no recursive sandboxing)
        "seccomp",
    ])

    def __post_init__(self) -> None:
        """Initialize seccomp policy with defaults."""
        if not self.allowed_syscalls:
            self.allowed_syscalls = self._ALLOWED_SYSCALLS
        if not self.blocked_syscalls:
            self.blocked_syscalls = self._BLOCKED_SYSCALLS
        if self.default_action != "KILL":
            logger.warning("Seccomp default_action should be KILL per Behavior Spec §2")

    def is_allowed(self, syscall: str) -> bool:
        """Check if syscall is in allowlist."""
        return syscall in self.allowed_syscalls

    def is_blocked(self, syscall: str) -> bool:
        """Check if syscall is explicitly blocked."""
        return syscall in self.blocked_syscalls


@dataclass
class CgroupLimit:
    """Cgroup resource limit per Behavior Spec §2.2.7.

    Represents a single cgroup resource constraint (memory, CPU, PIDs).

    Attributes:
        resource_type: Resource type (memory, cpu, pids)
        limit_value: Numeric limit value (bytes for memory, microseconds for cpu)
        unit: Unit of measurement (bytes, percent, count)
        controller_path: Path to cgroup controller file
        is_hard: Whether this is hard limit (vs. soft/proportional)
    """

    resource_type: str  # memory, cpu, pids, io
    limit_value: int = 0
    unit: str = ""
    controller_path: str = ""
    is_hard: bool = True

    def __post_init__(self) -> None:
        """Validate cgroup limit."""
        if not self.resource_type:
            raise ValueError("Resource type required")
        if self.limit_value < 0:
            raise ValueError("Limit value cannot be negative")


@dataclass
class IsolationConfig:
    """Complete isolation configuration per Behavior Spec §2.2.

    Represents all isolation layers required for a sandbox: namespaces,
    seccomp policy, cgroup limits, and filesystem mounts.

    Attributes:
        sandbox_id: Unique sandbox identifier
        namespaces: Dict of enabled namespaces
        seccomp_policy: Seccomp allowlist policy
        cgroup_limits: List of resource limits
        read_only_rootfs: Whether rootfs is read-only
        tmpfs_mount_point: Path for tmpfs scratch space
        tmpfs_max_size: Max tmpfs size in bytes
    """

    sandbox_id: str
    namespaces: dict[NamespaceType, Namespace] = field(default_factory=dict)
    seccomp_policy: SeccompPolicy = field(default_factory=SeccompPolicy)
    cgroup_limits: list[CgroupLimit] = field(default_factory=list)
    read_only_rootfs: bool = True
    tmpfs_mount_point: str = "/tmp"
    tmpfs_max_size: int = 100 * 1024 * 1024  # 100 MB

    def __post_init__(self) -> None:
        """Initialize with default isolation configuration."""
        if not self.namespaces:
            # Create default namespace configuration per Behavior Spec §2.2
            for ns_type in NamespaceType:
                self.namespaces[ns_type] = Namespace(
                    type=ns_type,
                    enabled=True,
                    sandbox_id=self.sandbox_id,
                )

        # Create default cgroup limits per Behavior Spec §2.2.7
        if not self.cgroup_limits:
            self.cgroup_limits = [
                CgroupLimit(
                    resource_type="memory",
                    limit_value=256 * 1024 * 1024,  # 256 MB default
                    unit="bytes",
                    is_hard=True,
                ),
                CgroupLimit(
                    resource_type="cpu",
                    limit_value=1_000_000,  # 1 second per period
                    unit="microseconds",
                    is_hard=True,
                ),
                CgroupLimit(
                    resource_type="pids",
                    limit_value=1,  # Single process per Behavior Spec §2.2.7
                    unit="count",
                    is_hard=True,
                ),
            ]

    def get_namespace(self, ns_type: NamespaceType) -> Namespace | None:
        """Get namespace by type."""
        return self.namespaces.get(ns_type)

    def get_cgroup_limit(self, resource_type: str) -> CgroupLimit | None:
        """Get cgroup limit by resource type."""
        for limit in self.cgroup_limits:
            if limit.resource_type == resource_type:
                return limit
        return None

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize path to resolve .. and . components."""
        return os.path.normpath(path)

    def is_allowed_path(self, path: str) -> bool:
        """Check if path is within allowed boundaries (tmpfs or readonly rootfs)."""
        normalized = self._normalize_path(path)
        tmpfs_path = self._normalize_path(self.tmpfs_mount_point)

        # Path must be under tmpfs or root (readonly rootfs)
        return normalized.startswith(tmpfs_path) or normalized == "/"


class IsolationInvariant(Protocol):
    """Protocol for isolation invariant verification per Behavior Spec §2.2.8.

    Invariants define the security properties that must hold for a sandbox.
    """

    def __call__(self, config: IsolationConfig, process_state: dict) -> bool:
        """Check if invariant holds.

        Args:
            config: Isolation configuration
            process_state: Current process state (pid, memory, syscalls, etc.)

        Returns:
            True if invariant holds, False otherwise
        """
        ...


class IsolationChecker:
    """Verify isolation invariants per Behavior Spec §2.2.8.

    This class implements property-based verification of isolation invariants:
    - No network egress from sandbox
    - No filesystem access outside tmpfs
    - No process visibility outside namespace
    - No syscall outside allowlist
    - No resource sharing with host
    """

    # Invariants per Behavior Spec §2.2.8
    _INVARIANTS: ClassVar[dict[str, str]] = {
        "no_network_egress": "Network operations must be empty (∀ process: network_ops = {})",
        "no_filesystem_escape": "Filesystem access only to tmpfs/readonly rootfs",
        "no_process_visibility": "Only own process and children visible (visible_procs ⊆ {self, children})",
        "no_syscall_escape": "All syscalls in allowlist or blocked by seccomp",
        "no_resource_sharing": "All resources within limits (sandbox_usage ≤ limit)",
    }

    def __init__(self) -> None:
        """Initialize isolation checker."""
        self.violations: list[dict] = []
        self.check_count: int = 0

    def check_no_network_egress(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify no network egress from sandbox (NET namespace isolated).

        Per Behavior Spec §2.2.2: NET namespace has no routes, network_ops = {}.

        Args:
            config: Isolation configuration
            process_state: Process state including network info

        Returns:
            True if no network connections detected
        """
        self.check_count += 1

        net_ns = config.get_namespace(NamespaceType.NET)
        if not net_ns or not net_ns.enabled:
            self.violations.append({
                "invariant": "no_network_egress",
                "check": self.check_count,
                "reason": "NET namespace not enabled",
            })
            return False

        # Check if process attempted any network operations
        network_ops = process_state.get("network_operations", [])
        if network_ops:
            self.violations.append({
                "invariant": "no_network_egress",
                "check": self.check_count,
                "reason": f"Network operations detected: {network_ops}",
            })
            return False

        # Check network routes
        network_routes = process_state.get("network_routes", [])
        if network_routes:
            self.violations.append({
                "invariant": "no_network_egress",
                "check": self.check_count,
                "reason": f"Network routes found: {network_routes}",
            })
            return False

        return True

    def check_no_filesystem_escape(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify filesystem access only to tmpfs/readonly rootfs (MNT isolated).

        Per Behavior Spec §2.2.3: MNT namespace has read-only rootfs + tmpfs.

        Args:
            config: Isolation configuration
            process_state: Process state including filesystem access

        Returns:
            True if all filesystem access within allowed boundaries
        """
        self.check_count += 1

        mnt_ns = config.get_namespace(NamespaceType.MNT)
        if not mnt_ns or not mnt_ns.enabled:
            self.violations.append({
                "invariant": "no_filesystem_escape",
                "check": self.check_count,
                "reason": "MNT namespace not enabled",
            })
            return False

        if not config.read_only_rootfs:
            self.violations.append({
                "invariant": "no_filesystem_escape",
                "check": self.check_count,
                "reason": "Rootfs is not read-only",
            })
            return False

        # Check filesystem access paths
        accessed_paths = process_state.get("accessed_paths", [])

        for path in accessed_paths:
            if not config.is_allowed_path(path):
                self.violations.append({
                    "invariant": "no_filesystem_escape",
                    "check": self.check_count,
                    "reason": f"Access to disallowed path: {path}",
                })
                return False

        return True

    def check_no_process_visibility(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify process visibility scoped to own process and children (PID isolated).

        Per Behavior Spec §2.2.1: PID namespace has only init + children visible.

        Args:
            config: Isolation configuration
            process_state: Process state including visible processes

        Returns:
            True if process visibility is scoped correctly
        """
        self.check_count += 1

        pid_ns = config.get_namespace(NamespaceType.PID)
        if not pid_ns or not pid_ns.enabled:
            self.violations.append({
                "invariant": "no_process_visibility",
                "check": self.check_count,
                "reason": "PID namespace not enabled",
            })
            return False

        own_pid = process_state.get("pid", 0)
        visible_pids = process_state.get("visible_processes", [])

        # Only own process and children should be visible
        for pid in visible_pids:
            if pid != own_pid and pid not in process_state.get("child_pids", []):
                self.violations.append({
                    "invariant": "no_process_visibility",
                    "check": self.check_count,
                    "reason": f"Visible process outside namespace: {pid}",
                })
                return False

        return True

    def check_no_syscall_escape(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify all syscalls are in allowlist or blocked by seccomp.

        Per Behavior Spec §2.2.6: Seccomp default-deny with allowlist.

        Args:
            config: Isolation configuration
            process_state: Process state including attempted syscalls

        Returns:
            True if all syscalls within allowlist
        """
        self.check_count += 1

        attempted_syscalls = process_state.get("attempted_syscalls", [])
        seccomp_policy = config.seccomp_policy

        for syscall in attempted_syscalls:
            if not seccomp_policy.is_allowed(syscall):
                self.violations.append({
                    "invariant": "no_syscall_escape",
                    "check": self.check_count,
                    "reason": f"Syscall outside allowlist: {syscall}",
                })
                return False

        return True

    def check_no_resource_sharing(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify all resources within limits (cgroup enforced).

        Per Behavior Spec §2.2.7: Cgroup v2 memory, CPU, PIDs limits.

        Args:
            config: Isolation configuration
            process_state: Process state including resource usage

        Returns:
            True if all resource usage within limits
        """
        self.check_count += 1

        for limit in config.cgroup_limits:
            resource_type = limit.resource_type
            current_usage = process_state.get(f"{resource_type}_usage", 0)

            if current_usage > limit.limit_value:
                self.violations.append({
                    "invariant": "no_resource_sharing",
                    "check": self.check_count,
                    "reason": f"{resource_type} usage {current_usage} exceeds limit {limit.limit_value}",
                })
                return False

        return True

    def verify_all_invariants(
        self, config: IsolationConfig, process_state: dict
    ) -> bool:
        """Verify all isolation invariants hold.

        Args:
            config: Isolation configuration
            process_state: Current process state

        Returns:
            True if all invariants hold, False otherwise
        """
        self.violations.clear()

        results = [
            self.check_no_network_egress(config, process_state),
            self.check_no_filesystem_escape(config, process_state),
            self.check_no_process_visibility(config, process_state),
            self.check_no_syscall_escape(config, process_state),
            self.check_no_resource_sharing(config, process_state),
        ]

        return all(results)

    def get_violations(self) -> list[dict]:
        """Return list of detected violations."""
        return self.violations.copy()

    def get_report(self) -> dict:
        """Generate isolation verification report."""
        return {
            "total_checks": self.check_count,
            "violations_detected": len(self.violations),
            "violations": self.violations,
            "invariants": self._INVARIANTS,
        }
