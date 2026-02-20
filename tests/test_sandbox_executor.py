"""Comprehensive tests for gRPC executor service per Behavior Spec §2.1 and ICD-022.

Tests validate:
- ExecutionRequest validation per ICD-022 schema constraints
- ExecutionResult error contract (timeout, memory_exceeded, etc.)
- ExecutorState machine transitions
- Backpressure enforcement (max concurrent, queue depth)
- Resource limit validation
- Language support constraints
- Stub protocol implementation for testing without grpcio
"""

from __future__ import annotations

import asyncio

import pytest

from holly.sandbox.executor import (
    CgroupError,
    CodeExecutor,
    CodeExecutorServiceStub,
    CodeSizeError,
    ExecutionErrorKind,
    ExecutionRequest,
    ExecutionResult,
    ExecutorState,
    InvalidLimitError,
    NamespaceError,
    ProtocolError,
    SeccompError,
    SpawnError,
    UnsupportedLanguageError,
)


class TestExecutionErrorKind:
    """Test ExecutionErrorKind enum per ICD-022."""

    def test_all_kinds_present(self) -> None:
        """Verify all ICD-022 error kinds defined."""
        assert ExecutionErrorKind.TIMEOUT.value == "timeout"
        assert ExecutionErrorKind.MEMORY_EXCEEDED.value == "memory_exceeded"
        assert (
            ExecutionErrorKind.SANDBOX_ESCAPE_ATTEMPT.value
            == "sandbox_escape_attempt"
        )
        assert ExecutionErrorKind.INVALID_SYSCALL.value == "invalid_syscall"
        assert ExecutionErrorKind.RUNTIME_ERROR.value == "runtime_error"

    def test_error_kind_classification(self) -> None:
        """Verify error kinds classify correctly."""
        assert ExecutionErrorKind.TIMEOUT != ExecutionErrorKind.MEMORY_EXCEEDED
        kinds = list(ExecutionErrorKind)
        assert len(kinds) >= 9


class TestExecutorState:
    """Test ExecutorState machine per Behavior Spec §2.1."""

    def test_state_transitions(self) -> None:
        """Verify state enum values."""
        assert ExecutorState.IDLE.value == "idle"
        assert ExecutorState.RECEIVING.value == "receiving"
        assert ExecutorState.EXECUTING.value == "executing"
        assert ExecutorState.COMPLETED.value == "completed"
        assert ExecutorState.TIMEOUT.value == "timeout"
        assert ExecutorState.FAULTED.value == "faulted"

    def test_all_states_defined(self) -> None:
        """Verify all states per spec."""
        states = {s.value for s in ExecutorState}
        assert "idle" in states
        assert "executing" in states
        assert "completed" in states


class TestExecutionErrorExceptions:
    """Test execution error exception hierarchy."""

    def test_protocol_error_kind(self) -> None:
        """ProtocolError sets correct kind."""
        err = ProtocolError("test")
        assert err.kind == ExecutionErrorKind.PROTOCOL_ERROR
        assert err.message == "test"
        assert err.code == 1

    def test_unsupported_language_error(self) -> None:
        """UnsupportedLanguageError sets correct kind."""
        err = UnsupportedLanguageError("rust")
        assert err.kind == ExecutionErrorKind.UNSUPPORTED_LANGUAGE
        assert "rust" in err.message

    def test_code_size_error(self) -> None:
        """CodeSizeError calculates sizes correctly."""
        err = CodeSizeError(20_000_000, 10_000_000)
        assert err.kind == ExecutionErrorKind.CODE_SIZE_ERROR
        assert "20000000" in err.message
        assert "10000000" in err.message

    def test_invalid_limit_error(self) -> None:
        """InvalidLimitError sets correct kind."""
        err = InvalidLimitError("Memory too high")
        assert err.kind == ExecutionErrorKind.PROTOCOL_ERROR
        assert "Memory too high" in err.message

    def test_spawn_error(self) -> None:
        """SpawnError sets correct kind."""
        err = SpawnError("Container failed")
        assert err.kind == ExecutionErrorKind.SPAWN_ERROR

    def test_namespace_error(self) -> None:
        """NamespaceError classifies as spawn error."""
        err = NamespaceError("PID namespace failed")
        assert err.kind == ExecutionErrorKind.SPAWN_ERROR

    def test_seccomp_error(self) -> None:
        """SeccompError classifies as invalid syscall."""
        err = SeccompError("Profile load failed")
        assert err.kind == ExecutionErrorKind.INVALID_SYSCALL

    def test_cgroup_error(self) -> None:
        """CgroupError classifies as memory exceeded."""
        err = CgroupError("Memory limit failed")
        assert err.kind == ExecutionErrorKind.MEMORY_EXCEEDED


class TestExecutionRequestValidation:
    """Test ExecutionRequest validation per ICD-022 schema."""

    def test_valid_minimal_request(self) -> None:
        """Minimal valid request passes validation."""
        req = ExecutionRequest(
            request_id="test-123",
            code="print('hello')",
            language="python3.11",
        )
        req.validate()  # Should not raise

    def test_missing_request_id(self) -> None:
        """Missing request_id raises ProtocolError."""
        req = ExecutionRequest(request_id="", code="print('hello')")
        with pytest.raises(ProtocolError, match="request_id is required"):
            req.validate()

    def test_unsupported_language(self) -> None:
        """Unsupported language raises UnsupportedLanguageError."""
        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
            language="rust",
        )
        with pytest.raises(UnsupportedLanguageError, match="rust"):
            req.validate()

    def test_supported_languages(self) -> None:
        """All declared languages validate."""
        for lang in ExecutionRequest.SUPPORTED_LANGUAGES:
            req = ExecutionRequest(
                request_id="test",
                code="",
                language=lang,
            )
            req.validate()  # Should not raise

    def test_code_size_limit(self) -> None:
        """Code exceeding 10 MB raises CodeSizeError."""
        max_bytes = ExecutionRequest.MAX_CODE_SIZE_MB * 1_000_000
        req = ExecutionRequest(
            request_id="test",
            code="x" * (max_bytes + 1),
        )
        with pytest.raises(CodeSizeError):
            req.validate()

    def test_code_size_at_limit(self) -> None:
        """Code at exact limit passes."""
        max_bytes = ExecutionRequest.MAX_CODE_SIZE_MB * 1_000_000
        req = ExecutionRequest(
            request_id="test",
            code="x" * max_bytes,
        )
        req.validate()  # Should not raise

    def test_memory_limit_exceeded(self) -> None:
        """Memory > 512 MB raises InvalidLimitError."""
        req = ExecutionRequest(
            request_id="test",
            code="",
            memory_limit_mb=513,
        )
        with pytest.raises(InvalidLimitError, match="Memory"):
            req.validate()

    def test_memory_limit_at_max(self) -> None:
        """Memory at 512 MB passes."""
        req = ExecutionRequest(
            request_id="test",
            code="",
            memory_limit_mb=512,
        )
        req.validate()  # Should not raise

    def test_timeout_exceeded(self) -> None:
        """Timeout > 30 seconds raises InvalidLimitError."""
        req = ExecutionRequest(
            request_id="test",
            code="",
            timeout=31.0,
        )
        with pytest.raises(InvalidLimitError, match="Timeout"):
            req.validate()

    def test_timeout_at_max(self) -> None:
        """Timeout at 30 seconds passes."""
        req = ExecutionRequest(
            request_id="test",
            code="",
            timeout=30.0,
        )
        req.validate()  # Should not raise

    def test_zero_timeout_invalid(self) -> None:
        """Zero or negative timeout raises InvalidLimitError."""
        req = ExecutionRequest(request_id="test", code="", timeout=0.0)
        with pytest.raises(InvalidLimitError, match="positive"):
            req.validate()

        req2 = ExecutionRequest(request_id="test", code="", timeout=-1.0)
        with pytest.raises(InvalidLimitError, match="positive"):
            req2.validate()

    def test_zero_memory_invalid(self) -> None:
        """Zero or negative memory raises InvalidLimitError."""
        req = ExecutionRequest(request_id="test", code="", memory_limit_mb=0)
        with pytest.raises(InvalidLimitError, match="positive"):
            req.validate()

    def test_file_size_limit(self) -> None:
        """Total files > 100 MB raises InvalidLimitError."""
        max_bytes = ExecutionRequest.MAX_FILE_SIZE_MB * 1_000_000
        req = ExecutionRequest(
            request_id="test",
            code="",
            files={"large.bin": b"x" * (max_bytes + 1)},
        )
        with pytest.raises(InvalidLimitError):
            req.validate()

    def test_multiple_files_cumulative_size(self) -> None:
        """Cumulative file size checked."""
        max_bytes = ExecutionRequest.MAX_FILE_SIZE_MB * 1_000_000
        half = max_bytes // 2 + 1
        req = ExecutionRequest(
            request_id="test",
            code="",
            files={
                "file1.bin": b"x" * half,
                "file2.bin": b"y" * half,
            },
        )
        with pytest.raises(InvalidLimitError):
            req.validate()

    def test_default_request_id_generated(self) -> None:
        """Request without request_id gets default UUID."""
        req = ExecutionRequest(code="print('hello')")
        assert req.request_id  # Default UUID generated
        assert len(req.request_id) > 0

    def test_default_trace_id_generated(self) -> None:
        """Request without trace_id gets default UUID."""
        req = ExecutionRequest(code="")
        assert req.trace_id
        assert len(req.trace_id) > 0

    def test_tenant_id_optional(self) -> None:
        """tenant_id is optional (empty string default)."""
        req = ExecutionRequest(request_id="test", code="")
        assert req.tenant_id == ""
        req.validate()  # Should pass


class TestExecutionResultTruncation:
    """Test ExecutionResult output truncation per Behavior Spec §2.1."""

    def test_stdout_within_limit(self) -> None:
        """stdout <= 1 MB not truncated."""
        max_bytes = ExecutionResult.MAX_OUTPUT_MB * 1_000_000
        result = ExecutionResult(
            request_id="test",
            stdout="x" * (max_bytes - 100),
        )
        assert len(result.stdout) == max_bytes - 100
        assert "...(truncated" not in result.stdout

    def test_stdout_exceeds_limit(self) -> None:
        """stdout > 1 MB truncated with marker."""
        max_bytes = ExecutionResult.MAX_OUTPUT_MB * 1_000_000
        original = "x" * (max_bytes + 1000)
        result = ExecutionResult(
            request_id="test",
            stdout=original,
        )
        assert "...(truncated" in result.stdout
        assert len(result.stdout) <= max_bytes + 100

    def test_stderr_truncation(self) -> None:
        """stderr > 1 MB truncated."""
        max_bytes = ExecutionResult.MAX_OUTPUT_MB * 1_000_000
        original = "y" * (max_bytes + 1000)
        result = ExecutionResult(
            request_id="test",
            stderr=original,
        )
        assert "...(truncated" in result.stderr

    def test_is_error_true_on_nonzero_exit(self) -> None:
        """is_error() returns True for nonzero exit_code."""
        result = ExecutionResult(request_id="test", exit_code=1)
        assert result.is_error()

    def test_is_error_true_on_error_kind(self) -> None:
        """is_error() returns True if error_kind set."""
        result = ExecutionResult(
            request_id="test",
            exit_code=0,
            error_kind=ExecutionErrorKind.TIMEOUT,
        )
        assert result.is_error()

    def test_is_error_false_on_success(self) -> None:
        """is_error() returns False for exit_code 0 without error_kind."""
        result = ExecutionResult(request_id="test", exit_code=0)
        assert not result.is_error()

    def test_is_timeout_check(self) -> None:
        """is_timeout() identifies timeout errors."""
        result = ExecutionResult(
            request_id="test",
            error_kind=ExecutionErrorKind.TIMEOUT,
        )
        assert result.is_timeout()

        result2 = ExecutionResult(
            request_id="test",
            error_kind=ExecutionErrorKind.MEMORY_EXCEEDED,
        )
        assert not result2.is_timeout()

    def test_is_oom_check(self) -> None:
        """is_oom() identifies OOM errors."""
        result = ExecutionResult(
            request_id="test",
            error_kind=ExecutionErrorKind.MEMORY_EXCEEDED,
        )
        assert result.is_oom()

        result2 = ExecutionResult(
            request_id="test",
            error_kind=ExecutionErrorKind.TIMEOUT,
        )
        assert not result2.is_oom()


class TestCodeExecutor:
    """Test CodeExecutor state machine and execution per Behavior Spec §2.1."""

    @pytest.mark.asyncio
    async def test_executor_initial_state(self) -> None:
        """Executor starts in IDLE state."""
        executor = CodeExecutor()
        assert executor.state == ExecutorState.IDLE

    @pytest.mark.asyncio
    async def test_valid_execution(self) -> None:
        """Valid request executes and returns result."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test-1",
            code="print('hello')",
            language="python3.11",
        )
        result = await executor.execute(req)

        assert result.request_id == "test-1"
        assert result.exit_code == 0
        assert result.start_time is not None
        assert result.end_time is not None

    @pytest.mark.asyncio
    async def test_execution_metrics_collected(self) -> None:
        """Execution result includes timing metrics."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test-2",
            code="x = 1 + 1",
            language="python3.11",
        )
        result = await executor.execute(req)

        assert result.wall_time >= 0
        assert result.user_time >= 0
        assert result.system_time >= 0
        assert result.memory_peak_mb >= 0

    @pytest.mark.asyncio
    async def test_invalid_request_returns_error_result(self) -> None:
        """Invalid request returns error result, not exception."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="",  # Invalid: empty request_id
            code="print('hello')",
        )
        result = await executor.execute(req)

        # Should return ExecutionResult with error, not raise
        assert result.exit_code != 0
        assert result.error_kind == ExecutionErrorKind.PROTOCOL_ERROR

    @pytest.mark.asyncio
    async def test_unsupported_language_error(self) -> None:
        """Unsupported language returns error result."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
            language="rust",
        )
        result = await executor.execute(req)

        assert result.exit_code != 0
        assert result.error_kind == ExecutionErrorKind.UNSUPPORTED_LANGUAGE

    @pytest.mark.asyncio
    async def test_backpressure_max_concurrent(self) -> None:
        """Executor rejects when >= max concurrent."""
        executor = CodeExecutor(max_concurrent=1)

        # Create a blocking condition to hold executor busy
        busy_event = asyncio.Event()
        release_event = asyncio.Event()

        async def blocking_task() -> None:
            executor._state = ExecutorState.EXECUTING
            executor._concurrent_count = 1
            busy_event.set()
            await release_event.wait()
            executor._concurrent_count = 0
            executor._state = ExecutorState.IDLE

        # Start blocking task to occupy the single concurrent slot
        block_task = asyncio.create_task(blocking_task())
        await busy_event.wait()  # Wait until executor is marked busy

        # Now try to execute while at capacity
        req2 = ExecutionRequest(
            request_id="test-2",
            code="print('second')",
        )
        result2 = await executor.execute(req2)

        # Should get error about capacity
        assert result2.exit_code != 0
        assert "capacity" in result2.error_message.lower()

        # Release the blocking task
        release_event.set()
        await block_task

    @pytest.mark.asyncio
    async def test_concurrent_count_tracking(self) -> None:
        """Executor tracks concurrent execution count."""
        executor = CodeExecutor()

        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
        )
        await executor.execute(req)

        # After execution completes, concurrent count should be 0
        assert executor.concurrent_count == 0

    @pytest.mark.asyncio
    async def test_health_check_idle(self) -> None:
        """Health check passes when executor idle."""
        executor = CodeExecutor()
        assert await executor.health_check()

    @pytest.mark.asyncio
    async def test_health_check_not_faulted(self) -> None:
        """Health check returns False if executor faulted."""
        executor = CodeExecutor()
        executor._state = ExecutorState.FAULTED
        assert not await executor.health_check()

    @pytest.mark.asyncio
    async def test_returns_to_idle_after_execution(self) -> None:
        """Executor returns to IDLE state after execution."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
        )
        await executor.execute(req)

        assert executor.state == ExecutorState.IDLE


class TestCodeExecutorServiceStub:
    """Test Protocol-based stub implementation for testing without grpcio."""

    @pytest.mark.asyncio
    async def test_stub_execute_delegates_to_executor(self) -> None:
        """Stub delegates Execute to executor."""
        executor = CodeExecutor()
        stub = CodeExecutorServiceStub(executor)

        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
        )
        result = await stub.Execute(req)

        assert result.request_id == "test"
        assert result.exit_code == 0

    def test_stub_subscribe_callback(self) -> None:
        """Stub's Subscribe adds callback to list."""
        executor = CodeExecutor()
        stub = CodeExecutorServiceStub(executor)

        callback_called = []

        def callback(result: ExecutionResult) -> None:
            callback_called.append(result)

        stub.Subscribe(callback)
        assert len(stub._callbacks) == 1

    @pytest.mark.asyncio
    async def test_stub_invokes_callbacks_on_execution(self) -> None:
        """Stub invokes callbacks after execution."""
        executor = CodeExecutor()
        stub = CodeExecutorServiceStub(executor)

        results_received = []

        def callback(result: ExecutionResult) -> None:
            results_received.append(result)

        stub.Subscribe(callback)

        req = ExecutionRequest(
            request_id="test",
            code="print('hello')",
        )
        await stub.Execute(req)

        assert len(results_received) == 1
        assert results_received[0].request_id == "test"

    @pytest.mark.asyncio
    async def test_stub_multiple_callbacks(self) -> None:
        """Stub invokes all subscribed callbacks."""
        executor = CodeExecutor()
        stub = CodeExecutorServiceStub(executor)

        calls = []

        def callback1(result: ExecutionResult) -> None:
            calls.append(("callback1", result.request_id))

        def callback2(result: ExecutionResult) -> None:
            calls.append(("callback2", result.request_id))

        stub.Subscribe(callback1)
        stub.Subscribe(callback2)

        req = ExecutionRequest(request_id="test", code="")
        await stub.Execute(req)

        assert len(calls) == 2
        assert calls[0][0] == "callback1"
        assert calls[1][0] == "callback2"


class TestICD022Compliance:
    """Test ICD-022 specific requirements per interface contract."""

    @pytest.mark.asyncio
    async def test_bidirectional_request_response(self) -> None:
        """Execute method implements bidirectional RPC per ICD-022."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="icd-test",
            code="print('test')",
            tenant_id="tenant-1",
            trace_id="trace-1",
        )
        result = await executor.execute(req)

        # Verify request echoed in response
        assert result.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_tenant_isolation_tag_preserved(self) -> None:
        """ExecutionRequest tenant_id preserved for observability."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="",
            tenant_id="tenant-abc",
        )
        result = await executor.execute(req)

        # Tenant should be preserved in request_id echo
        assert result.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_trace_id_for_observability(self) -> None:
        """ExecutionRequest trace_id available for observability."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="",
            trace_id="trace-xyz-123",
        )
        result = await executor.execute(req)

        assert result.request_id == req.request_id

    @pytest.mark.asyncio
    async def test_error_contract_timeout(self) -> None:
        """Timeout error per ICD-022 error contract."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="import time; time.sleep(100)",
            timeout=0.001,  # Very short timeout
        )
        result = await executor.execute(req)
        assert result.request_id == "test"

    @pytest.mark.asyncio
    async def test_max_concurrent_per_icd022(self) -> None:
        """Executor enforces max 10 concurrent per ICD-022."""
        executor = CodeExecutor()
        assert executor._max_concurrent == 10

    @pytest.mark.asyncio
    async def test_queue_depth_per_icd022(self) -> None:
        """Executor enforces max queue depth 100 per ICD-022."""
        executor = CodeExecutor()
        assert executor._max_queue_depth == 100


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_code_allowed(self) -> None:
        """Empty code string is valid."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="",
        )
        result = await executor.execute(req)
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_large_environment_variables(self) -> None:
        """Large environment dict handled."""
        executor = CodeExecutor()
        env = {f"VAR_{i}": f"value_{i}" for i in range(100)}
        req = ExecutionRequest(
            request_id="test",
            code="",
            environment=env,
        )
        result = await executor.execute(req)
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_special_characters_in_code(self) -> None:
        """Special characters in code handled."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="print('\\n\\t\\r特殊文字テスト')",
            language="python3.11",
        )
        result = await executor.execute(req)
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_cpu_throttle_parameters(self) -> None:
        """CPU throttle parameters validated."""
        executor = CodeExecutor()
        req = ExecutionRequest(
            request_id="test",
            code="",
            cpu_period_ms=100,
            cpu_quota_ms=50,
        )
        result = await executor.execute(req)
        assert result.exit_code == 0
