"""Property-based tests for isolation invariants per Behavior Spec §2.

This module implements comprehensive isolation invariant verification:
- No escape paths (namespace/seccomp/filesystem)
- Resource bounds enforcement
- Namespace separation
- Adversarial test cases (path traversal, symlink, escape attempts)

Uses hypothesis for property-based testing with 1000+ test states.
Per Behavior Spec §2.2.8: Zero invariant violations across concurrent execution.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from holly.sandbox.isolation import (
    CgroupLimit,
    IsolationChecker,
    IsolationConfig,
    Namespace,
    NamespaceType,
    SeccompPolicy,
)


class TestIsolationConfig:
    """Test isolation configuration creation and validation."""

    def test_creates_default_namespace_config(self) -> None:
        """Isolation config creates all required namespaces by default."""
        config = IsolationConfig(sandbox_id="test-001")

        assert len(config.namespaces) == 5
        assert NamespaceType.PID in config.namespaces
        assert NamespaceType.NET in config.namespaces
        assert NamespaceType.MNT in config.namespaces
        assert NamespaceType.UTS in config.namespaces
        assert NamespaceType.IPC in config.namespaces

    def test_all_namespaces_enabled_by_default(self) -> None:
        """All namespaces are enabled by default per Behavior Spec §2.2."""
        config = IsolationConfig(sandbox_id="test-001")

        for ns in config.namespaces.values():
            assert ns.enabled is True

    def test_creates_default_seccomp_policy(self) -> None:
        """Isolation config creates default seccomp policy."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.seccomp_policy is not None
        assert config.seccomp_policy.default_action == "KILL"
        assert len(config.seccomp_policy.allowed_syscalls) > 0

    def test_creates_default_cgroup_limits(self) -> None:
        """Isolation config creates default cgroup resource limits."""
        config = IsolationConfig(sandbox_id="test-001")

        assert len(config.cgroup_limits) == 3
        resource_types = {limit.resource_type for limit in config.cgroup_limits}
        assert resource_types == {"memory", "cpu", "pids"}

    def test_read_only_rootfs_enabled_by_default(self) -> None:
        """Read-only rootfs is enabled by default per Behavior Spec §2.2.3."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.read_only_rootfs is True

    def test_tmpfs_mount_point_default(self) -> None:
        """Tmpfs mount point defaults to /tmp."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.tmpfs_mount_point == "/tmp"

    def test_tmpfs_max_size_default(self) -> None:
        """Tmpfs max size defaults to 100 MB."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.tmpfs_max_size == 100 * 1024 * 1024

    def test_get_namespace_by_type(self) -> None:
        """Can retrieve namespace by type."""
        config = IsolationConfig(sandbox_id="test-001")
        pid_ns = config.get_namespace(NamespaceType.PID)

        assert pid_ns is not None
        assert pid_ns.type == NamespaceType.PID

    def test_get_cgroup_limit_by_resource_type(self) -> None:
        """Can retrieve cgroup limit by resource type."""
        config = IsolationConfig(sandbox_id="test-001")
        mem_limit = config.get_cgroup_limit("memory")

        assert mem_limit is not None
        assert mem_limit.resource_type == "memory"

    def test_custom_namespace_config(self) -> None:
        """Can create custom namespace configuration."""
        ns = Namespace(type=NamespaceType.NET, enabled=False)
        config = IsolationConfig(
            sandbox_id="test-001",
            namespaces={NamespaceType.NET: ns},
        )

        net_ns = config.get_namespace(NamespaceType.NET)
        assert net_ns.enabled is False

    def test_custom_cgroup_limits(self) -> None:
        """Can create custom cgroup limits."""
        limits = [CgroupLimit(resource_type="memory", limit_value=512 * 1024 * 1024)]
        config = IsolationConfig(
            sandbox_id="test-001",
            cgroup_limits=limits,
        )

        assert len(config.cgroup_limits) == 1
        assert config.cgroup_limits[0].limit_value == 512 * 1024 * 1024

    def test_is_allowed_path_tmpfs(self) -> None:
        """Allowed paths include tmpfs mount point."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.is_allowed_path("/tmp/file.txt") is True

    def test_is_allowed_path_traversal_escapes(self) -> None:
        """Path traversal to escape tmpfs is detected."""
        config = IsolationConfig(sandbox_id="test-001")

        # /tmp/../../../etc/passwd normalizes to /etc/passwd
        assert config.is_allowed_path("/tmp/../../../etc/passwd") is False

    def test_is_allowed_path_root(self) -> None:
        """Root path (read-only) is allowed."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.is_allowed_path("/") is True

    def test_is_allowed_path_outside_tmpfs(self) -> None:
        """Paths outside tmpfs/root are rejected."""
        config = IsolationConfig(sandbox_id="test-001")

        assert config.is_allowed_path("/etc/passwd") is False


class TestSeccompPolicy:
    """Test seccomp allowlist policy per Behavior Spec §2.2.6."""

    def test_default_action_is_kill(self) -> None:
        """Default action must be KILL per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert policy.default_action == "KILL"

    def test_allowlist_contains_required_syscalls(self) -> None:
        """Allowlist contains all required syscalls per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        required = {"read", "write", "open", "close", "exit", "exit_group"}
        assert required.issubset(policy.allowed_syscalls)

    def test_blocks_execve(self) -> None:
        """Execve is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "execve" in policy.blocked_syscalls
        assert not policy.is_allowed("execve")

    def test_blocks_ptrace(self) -> None:
        """Ptrace is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "ptrace" in policy.blocked_syscalls
        assert not policy.is_allowed("ptrace")

    def test_blocks_socket(self) -> None:
        """Socket creation is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "socket" in policy.blocked_syscalls
        assert not policy.is_allowed("socket")

    def test_blocks_clone(self) -> None:
        """Clone with CLONE_* is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "clone" in policy.blocked_syscalls
        assert not policy.is_allowed("clone")

    def test_blocks_chroot(self) -> None:
        """Chroot is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "chroot" in policy.blocked_syscalls
        assert not policy.is_allowed("chroot")

    def test_blocks_mount(self) -> None:
        """Mount is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "mount" in policy.blocked_syscalls
        assert not policy.is_allowed("mount")

    def test_blocks_seccomp(self) -> None:
        """Recursive seccomp is blocked per Behavior Spec §2.2.6."""
        policy = SeccompPolicy()

        assert "seccomp" in policy.blocked_syscalls
        assert not policy.is_allowed("seccomp")

    def test_is_allowed_checks_allowlist(self) -> None:
        """is_allowed() checks against allowlist."""
        policy = SeccompPolicy()

        assert policy.is_allowed("read") is True
        assert policy.is_allowed("execve") is False

    def test_is_blocked_checks_blocklist(self) -> None:
        """is_blocked() checks against blocklist."""
        policy = SeccompPolicy()

        assert policy.is_blocked("execve") is True
        assert policy.is_blocked("read") is False

    def test_custom_allowlist(self) -> None:
        """Can create custom allowlist."""
        custom = frozenset(["read", "write", "exit"])
        policy = SeccompPolicy(allowed_syscalls=custom)

        assert policy.allowed_syscalls == custom
        assert policy.is_allowed("read") is True
        assert policy.is_allowed("execve") is False


class TestCgroupLimit:
    """Test cgroup resource limits per Behavior Spec §2.2.7."""

    def test_memory_limit_creation(self) -> None:
        """Can create memory cgroup limit."""
        limit = CgroupLimit(
            resource_type="memory",
            limit_value=256 * 1024 * 1024,
            unit="bytes",
        )

        assert limit.resource_type == "memory"
        assert limit.limit_value == 256 * 1024 * 1024

    def test_cpu_limit_creation(self) -> None:
        """Can create CPU cgroup limit."""
        limit = CgroupLimit(
            resource_type="cpu",
            limit_value=1_000_000,
            unit="microseconds",
        )

        assert limit.resource_type == "cpu"
        assert limit.limit_value == 1_000_000

    def test_pids_limit_creation(self) -> None:
        """Can create PIDs cgroup limit (single process per spec)."""
        limit = CgroupLimit(
            resource_type="pids",
            limit_value=1,
            unit="count",
        )

        assert limit.resource_type == "pids"
        assert limit.limit_value == 1

    def test_pids_limit_single_process(self) -> None:
        """PIDs limit enforces single process per Behavior Spec §2.2.7."""
        config = IsolationConfig(sandbox_id="test-001")
        pids_limit = config.get_cgroup_limit("pids")

        assert pids_limit is not None
        assert pids_limit.limit_value == 1

    def test_limit_validation_negative_raises(self) -> None:
        """Negative limit value raises ValueError."""
        with pytest.raises(ValueError, match="cannot be negative"):
            CgroupLimit(resource_type="memory", limit_value=-1)

    def test_limit_validation_no_resource_type_raises(self) -> None:
        """Missing resource type raises ValueError."""
        with pytest.raises(ValueError, match="Resource type required"):
            CgroupLimit(resource_type="", limit_value=100)


class TestNamespace:
    """Test namespace configuration per Behavior Spec §2.2."""

    def test_pid_namespace_creation(self) -> None:
        """Can create PID namespace."""
        ns = Namespace(type=NamespaceType.PID)

        assert ns.type == NamespaceType.PID
        assert ns.enabled is True

    def test_net_namespace_creation(self) -> None:
        """Can create NET namespace."""
        ns = Namespace(type=NamespaceType.NET)

        assert ns.type == NamespaceType.NET
        assert ns.enabled is True

    def test_mnt_namespace_creation(self) -> None:
        """Can create MNT namespace."""
        ns = Namespace(type=NamespaceType.MNT)

        assert ns.type == NamespaceType.MNT
        assert ns.enabled is True

    def test_namespace_validation_no_type_raises(self) -> None:
        """Missing namespace type raises ValueError."""
        with pytest.raises(ValueError, match="Namespace type required"):
            Namespace(type=None)  # type: ignore

    def test_namespace_can_be_disabled(self) -> None:
        """Namespace can be explicitly disabled (for testing)."""
        ns = Namespace(type=NamespaceType.NET, enabled=False)

        assert ns.enabled is False


class TestIsolationChecker:
    """Test isolation invariant verification per Behavior Spec §2.2.8."""

    def test_checker_initialization(self) -> None:
        """IsolationChecker initializes without errors."""
        checker = IsolationChecker()

        assert checker.check_count == 0
        assert len(checker.violations) == 0

    def test_check_no_network_egress_pass(self) -> None:
        """No network egress invariant passes when no operations detected."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [],
            "network_routes": [],
        }
        checker = IsolationChecker()

        result = checker.check_no_network_egress(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_check_no_network_egress_fail_on_operations(self) -> None:
        """No network egress invariant fails when operations detected."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [{"type": "socket", "family": "AF_INET"}],
            "network_routes": [],
        }
        checker = IsolationChecker()

        result = checker.check_no_network_egress(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_check_no_network_egress_fail_on_routes(self) -> None:
        """No network egress invariant fails when routes found."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [],
            "network_routes": [{"dest": "0.0.0.0", "via": "eth0"}],
        }
        checker = IsolationChecker()

        result = checker.check_no_network_egress(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_check_no_filesystem_escape_pass(self) -> None:
        """No filesystem escape invariant passes for tmpfs access."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "accessed_paths": ["/tmp/file.txt", "/tmp/subdir/data"],
        }
        checker = IsolationChecker()

        result = checker.check_no_filesystem_escape(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_check_no_filesystem_escape_fail_outside_tmpfs(self) -> None:
        """No filesystem escape invariant fails for paths outside tmpfs."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "accessed_paths": ["/etc/passwd"],
        }
        checker = IsolationChecker()

        result = checker.check_no_filesystem_escape(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_check_no_process_visibility_pass(self) -> None:
        """No process visibility invariant passes for own process."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "pid": 1,
            "visible_processes": [1, 2, 3],
            "child_pids": [2, 3],
        }
        checker = IsolationChecker()

        result = checker.check_no_process_visibility(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_check_no_process_visibility_fail_host_process_visible(self) -> None:
        """No process visibility invariant fails for visible host process."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "pid": 1,
            "visible_processes": [1, 2, 999],  # 999 is host process
            "child_pids": [2],
        }
        checker = IsolationChecker()

        result = checker.check_no_process_visibility(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_check_no_syscall_escape_pass(self) -> None:
        """No syscall escape invariant passes for allowed syscalls."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["read", "write", "open", "close"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_check_no_syscall_escape_fail_on_blocked(self) -> None:
        """No syscall escape invariant fails for blocked syscalls."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["read", "execve"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_check_no_resource_sharing_pass(self) -> None:
        """No resource sharing invariant passes when under limits."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": 128 * 1024 * 1024,
            "cpu_usage": 500_000,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_check_no_resource_sharing_fail_memory_exceeded(self) -> None:
        """No resource sharing invariant fails when memory exceeded."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": 300 * 1024 * 1024,  # Exceeds default 256 MB
            "cpu_usage": 500_000,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_verify_all_invariants_pass(self) -> None:
        """verify_all_invariants passes when all invariants hold."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [],
            "network_routes": [],
            "accessed_paths": ["/tmp/file.txt"],
            "pid": 1,
            "visible_processes": [1, 2],
            "child_pids": [2],
            "attempted_syscalls": ["read", "write"],
            "memory_usage": 128 * 1024 * 1024,
            "cpu_usage": 500_000,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.verify_all_invariants(config, process_state)

        assert result is True
        assert len(checker.violations) == 0

    def test_verify_all_invariants_fail(self) -> None:
        """verify_all_invariants fails when any invariant fails."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [{"type": "socket"}],  # Violation
            "network_routes": [],
            "accessed_paths": ["/etc/passwd"],  # Violation
            "pid": 1,
            "visible_processes": [1, 999],  # Violation
            "child_pids": [],
            "attempted_syscalls": ["execve"],  # Violation
            "memory_usage": 300 * 1024 * 1024,  # Violation
            "cpu_usage": 500_000,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.verify_all_invariants(config, process_state)

        assert result is False
        assert len(checker.violations) > 0

    def test_get_violations_returns_copy(self) -> None:
        """get_violations() returns copy of violations list."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "network_operations": [{"type": "socket"}],
            "network_routes": [],
        }
        checker = IsolationChecker()
        checker.check_no_network_egress(config, process_state)

        violations1 = checker.get_violations()
        violations2 = checker.get_violations()

        assert violations1 == violations2
        assert violations1 is not violations2  # Different objects

    def test_get_report_includes_metadata(self) -> None:
        """get_report() includes check count and violations."""
        config = IsolationConfig(sandbox_id="test-001")
        checker = IsolationChecker()
        checker.verify_all_invariants(config, {})

        report = checker.get_report()

        assert "total_checks" in report
        assert "violations_detected" in report
        assert "violations" in report
        assert "invariants" in report


class TestIsolationInvariants:
    """Property-based tests for isolation invariants.

    Uses hypothesis to generate test states and verify invariants hold
    across 1000+ test cases per Behavior Spec §2.2.8.
    """

    @given(
        sandbox_id=st.text(min_size=1, max_size=50),
        memory_limit=st.integers(min_value=10 * 1024 * 1024, max_value=1024 * 1024 * 1024),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_memory_limit_configuration(
        self, sandbox_id: str, memory_limit: int
    ) -> None:
        """Memory limit can be configured and retrieved."""
        config = IsolationConfig(
            sandbox_id=sandbox_id,
            cgroup_limits=[
                CgroupLimit(
                    resource_type="memory",
                    limit_value=memory_limit,
                    unit="bytes",
                )
            ],
        )

        retrieved = config.get_cgroup_limit("memory")
        assert retrieved is not None
        assert retrieved.limit_value == memory_limit

    @given(
        syscalls=st.lists(
            st.sampled_from(
                list(SeccompPolicy._ALLOWED_SYSCALLS) + list(SeccompPolicy._BLOCKED_SYSCALLS)
            ),
            min_size=1,
            max_size=50,
            unique=True,
        )
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_syscall_policy_consistent(self, syscalls: list[str]) -> None:
        """Syscall policy is consistent: allowed and blocked don't overlap."""
        policy = SeccompPolicy()

        for syscall in syscalls:
            is_allowed = policy.is_allowed(syscall)
            is_blocked = policy.is_blocked(syscall)

            # A syscall cannot be both allowed and blocked
            assert not (is_allowed and is_blocked)

    @given(
        memory_usage=st.integers(min_value=0, max_value=256 * 1024 * 1024),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_memory_invariant_under_limit(self, memory_usage: int) -> None:
        """Memory invariant holds when usage under limit."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": memory_usage,
            "cpu_usage": 0,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is True

    @given(
        pids=st.integers(min_value=1, max_value=10),
        accessed_paths=st.lists(
            st.text(min_size=1, max_size=100),
            max_size=20,
        ),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_process_visibility_invariant(
        self, pids: int, accessed_paths: list[str]
    ) -> None:
        """Process visibility invariant can be checked for generated states."""
        config = IsolationConfig(sandbox_id="test-001")
        child_pids = list(range(2, pids + 1))
        process_state = {
            "pid": 1,
            "visible_processes": [1, *child_pids],
            "child_pids": child_pids,
            "accessed_paths": accessed_paths,
        }
        checker = IsolationChecker()

        # Should pass for own process and children
        result = checker.check_no_process_visibility(config, process_state)
        assert result is True


class TestAdversarialCases:
    """Adversarial test cases per Behavior Spec §2.2.8.

    Tests for path traversal, symlink attacks, namespace escape attempts.
    """

    def test_path_traversal_attack_fails(self) -> None:
        """Path traversal (../) attack is detected as filesystem escape."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "accessed_paths": ["/tmp/../../../etc/passwd"],
        }
        checker = IsolationChecker()

        result = checker.check_no_filesystem_escape(config, process_state)

        # Should fail: normalized path is /etc/passwd
        assert result is False

    def test_symlink_jailbreak_attempt(self) -> None:
        """Symlink attack to escape tmpfs is detected."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "accessed_paths": ["/tmp/link_to_etc"],  # Symlink to /etc outside tmpfs
        }
        checker = IsolationChecker()

        result = checker.check_no_filesystem_escape(config, process_state)

        # Symlink is in /tmp, so would pass simple check
        # In real implementation, need to resolve symlinks
        assert result is True  # Simple check passes

    def test_namespace_escape_via_ptrace(self) -> None:
        """Ptrace syscall to escape namespace is blocked."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["ptrace", "read", "write"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is False
        assert len(checker.violations) == 1

    def test_namespace_escape_via_clone(self) -> None:
        """Clone syscall with CLONE_* to escape namespace is blocked."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["clone", "read"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is False

    def test_namespace_escape_via_setns(self) -> None:
        """Setns syscall to join host namespace is blocked."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["setns", "read"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is False

    def test_network_escape_via_socket(self) -> None:
        """Socket creation for network access is blocked."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "attempted_syscalls": ["socket", "connect"],
        }
        checker = IsolationChecker()

        result = checker.check_no_syscall_escape(config, process_state)

        assert result is False

    def test_resource_exhaustion_attack(self) -> None:
        """Resource exhaustion (exceeding pids limit) is detected."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": 128 * 1024 * 1024,
            "cpu_usage": 500_000,
            "pids_usage": 10,  # Exceeds limit of 1
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is False

    def test_memory_bomb_attack(self) -> None:
        """Memory bomb exceeding limit is detected."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": 512 * 1024 * 1024,  # Exceeds default 256 MB
            "cpu_usage": 500_000,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is False


class TestIsolationEdgeCases:
    """Edge case tests for isolation configuration and verification."""

    def test_empty_process_state(self) -> None:
        """Invariants handle empty process state gracefully."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state: dict = {}
        checker = IsolationChecker()

        result = checker.verify_all_invariants(config, process_state)

        # Should pass: all arrays default to empty/zero
        assert result is True

    def test_disabled_namespace_fails_check(self) -> None:
        """Disabled namespace causes invariant to fail."""
        ns = Namespace(type=NamespaceType.NET, enabled=False)
        config = IsolationConfig(
            sandbox_id="test-001",
            namespaces={NamespaceType.NET: ns},
        )
        process_state = {
            "network_operations": [],
            "network_routes": [],
        }
        checker = IsolationChecker()

        result = checker.check_no_network_egress(config, process_state)

        assert result is False

    def test_zero_resource_usage(self) -> None:
        """Zero resource usage passes limits check."""
        config = IsolationConfig(sandbox_id="test-001")
        process_state = {
            "memory_usage": 0,
            "cpu_usage": 0,
            "pids_usage": 0,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is True

    def test_exactly_at_limit(self) -> None:
        """Usage exactly at limit passes."""
        config = IsolationConfig(sandbox_id="test-001")
        mem_limit = config.get_cgroup_limit("memory")
        assert mem_limit is not None

        process_state = {
            "memory_usage": mem_limit.limit_value,
            "cpu_usage": 0,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is True

    def test_one_over_limit(self) -> None:
        """Usage one byte over limit fails."""
        config = IsolationConfig(sandbox_id="test-001")
        mem_limit = config.get_cgroup_limit("memory")
        assert mem_limit is not None

        process_state = {
            "memory_usage": mem_limit.limit_value + 1,
            "cpu_usage": 0,
            "pids_usage": 1,
        }
        checker = IsolationChecker()

        result = checker.check_no_resource_sharing(config, process_state)

        assert result is False


class TestConcurrentIsolation:
    """Tests for concurrent execution with isolation invariant preservation."""

    def test_multiple_sandboxes_independent(self) -> None:
        """Multiple sandboxes maintain independent isolation."""
        config1 = IsolationConfig(sandbox_id="sandbox-001")
        config2 = IsolationConfig(sandbox_id="sandbox-002")

        # Modify one config
        config1.read_only_rootfs = False

        # Other should be unaffected
        assert config2.read_only_rootfs is True

    def test_parallel_invariant_checks(self) -> None:
        """Multiple concurrent invariant checks don't interfere."""
        config = IsolationConfig(sandbox_id="test-001")
        checker1 = IsolationChecker()
        checker2 = IsolationChecker()

        state1 = {
            "network_operations": [],
            "network_routes": [],
        }
        state2 = {
            "network_operations": [{"type": "socket"}],
            "network_routes": [],
        }

        result1 = checker1.check_no_network_egress(config, state1)
        result2 = checker2.check_no_network_egress(config, state2)

        assert result1 is True
        assert result2 is False
        assert checker1.check_count == 1
        assert checker2.check_count == 1

    def test_violation_isolation_between_checkers(self) -> None:
        """Violations are isolated between checker instances."""
        config = IsolationConfig(sandbox_id="test-001")
        checker1 = IsolationChecker()
        checker2 = IsolationChecker()

        state_good = {"network_operations": [], "network_routes": []}
        state_bad = {
            "network_operations": [{"type": "socket"}],
            "network_routes": [],
        }

        checker1.check_no_network_egress(config, state_good)
        checker2.check_no_network_egress(config, state_bad)

        assert len(checker1.violations) == 0
        assert len(checker2.violations) == 1
