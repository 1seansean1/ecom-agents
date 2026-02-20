"""Unit tests for holly.engine.lanes module."""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

from holly.engine.lanes import (
    Task,
    TaskEnqueueRequest,
    ScheduledTask,
    ScheduledTaskRequest,
    SubagentTask,
    SubagentSpawnRequest,
    LanePolicy,
    Lane,
    MainLane,
    CronLane,
    SubagentLane,
    LaneManager,
    LaneType,
    LaneError,
    QueueFullError,
    InvalidScheduleError,
    AgentSpawnError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_id() -> str:
    """Create a test tenant ID."""
    return "tenant-test-001"


@pytest.fixture
def policy() -> LanePolicy:
    """Create a test policy."""
    return LanePolicy(
        max_queue_depth=10,
        max_concurrency=5,
        backpressure_timeout=5.0,
    )


@pytest.fixture
def task(tenant_id: str) -> Task:
    """Create a test task."""
    return Task(
        task_id=uuid4(),
        goal={"description": "test goal"},
        user_id="user-001",
        tenant_id=tenant_id,
        idempotency_key=str(uuid4()),
        resource_budget={"cpu": 1, "memory": 512},
        mcp_tools=["tool1", "tool2"],
        context={"key": "value"},
        trace_id=str(uuid4()),
    )


@pytest.fixture
def scheduled_task(tenant_id: str) -> ScheduledTask:
    """Create a scheduled task."""
    now = datetime.now(timezone.utc)
    scheduled_time = now + timedelta(hours=1)
    return ScheduledTask(
        task=Task(
            task_id=uuid4(),
            goal={"description": "scheduled goal"},
            user_id="user-002",
            tenant_id=tenant_id,
            idempotency_key=str(uuid4()),
            resource_budget={"cpu": 1, "memory": 512},
            mcp_tools=[],
            context={},
        ),
        scheduled_time=scheduled_time,
        recurrence=None,
        max_retries=3,
    )


@pytest.fixture
def subagent_task(tenant_id: str) -> SubagentTask:
    """Create a subagent task."""
    return SubagentTask(
        agent_binding={"agent_id": "agent-001", "type": "researcher"},
        goals=[{"description": "research goal"}],
        parent_execution_id=uuid4(),
        user_id="user-003",
        tenant_id=tenant_id,
        message_queue="queue-handle-001",
        trace_id=str(uuid4()),
    )


# ---------------------------------------------------------------------------
# Task Tests
# ---------------------------------------------------------------------------


class TestTask:
    """Tests for Task class."""

    def test_task_creation(self, task: Task) -> None:
        """Test task creation."""
        assert task.task_id is not None
        assert task.tenant_id == "tenant-test-001"
        assert task.user_id == "user-001"

    def test_task_is_expired_false(self, task: Task) -> None:
        """Test is_expired returns False when no deadline."""
        assert not task.is_expired()

    def test_task_is_expired_future_deadline(self, task: Task) -> None:
        """Test is_expired returns False for future deadline."""
        task.deadline = datetime.now(timezone.utc) + timedelta(hours=1)
        assert not task.is_expired()

    def test_task_is_expired_past_deadline(self, task: Task) -> None:
        """Test is_expired returns True for past deadline."""
        task.deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        assert task.is_expired()

    def test_task_is_expired_now_deadline(self, task: Task) -> None:
        """Test is_expired behavior at exactly now."""
        task.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert task.is_expired()


class TestScheduledTask:
    """Tests for ScheduledTask class."""

    def test_scheduled_task_creation(self, scheduled_task: ScheduledTask) -> None:
        """Test scheduled task creation."""
        assert scheduled_task.schedule_id is not None
        assert scheduled_task.task is not None

    def test_is_due_past_time(self, scheduled_task: ScheduledTask) -> None:
        """Test is_due returns True for past scheduled time."""
        scheduled_task.scheduled_time = datetime.now(timezone.utc) - timedelta(
            hours=1
        )
        assert scheduled_task.is_due()

    def test_is_due_future_time(self, scheduled_task: ScheduledTask) -> None:
        """Test is_due returns False for future scheduled time."""
        scheduled_task.scheduled_time = datetime.now(timezone.utc) + timedelta(
            hours=1
        )
        assert not scheduled_task.is_due()

    def test_is_due_with_custom_now(self, scheduled_task: ScheduledTask) -> None:
        """Test is_due with custom now parameter."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        scheduled_task.scheduled_time = base_time
        
        now_before = base_time - timedelta(hours=1)
        assert not scheduled_task.is_due(now_before)
        
        now_after = base_time + timedelta(hours=1)
        assert scheduled_task.is_due(now_after)


class TestSubagentTask:
    """Tests for SubagentTask class."""

    def test_subagent_task_creation(self, subagent_task: SubagentTask) -> None:
        """Test subagent task creation."""
        assert subagent_task.subagent_execution_id is not None
        assert subagent_task.parent_execution_id is not None
        assert subagent_task.tenant_id == "tenant-test-001"

    def test_subagent_task_is_expired_false(
        self, subagent_task: SubagentTask
    ) -> None:
        """Test is_expired returns False when no deadline."""
        assert not subagent_task.is_expired()

    def test_subagent_task_is_expired_true(
        self, subagent_task: SubagentTask
    ) -> None:
        """Test is_expired returns True for past deadline."""
        subagent_task.deadline = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        assert subagent_task.is_expired()


# ---------------------------------------------------------------------------
# MainLane Tests
# ---------------------------------------------------------------------------


class TestMainLane:
    """Tests for MainLane class."""

    @pytest.mark.asyncio
    async def test_main_lane_creation(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test MainLane creation."""
        lane = MainLane(tenant_id, policy)
        assert lane.lane_type == LaneType.MAIN
        assert lane.tenant_id == tenant_id
        assert len(lane.priority_queue) == 11

    @pytest.mark.asyncio
    async def test_enqueue_task_success(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test successful task enqueue."""
        lane = MainLane(tenant_id, policy)
        request = TaskEnqueueRequest(task=task, priority=5)
        task_id = await lane.enqueue_task(request)
        assert task_id == task.task_id

    @pytest.mark.asyncio
    async def test_enqueue_task_expired(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test enqueue raises for expired task."""
        lane = MainLane(tenant_id, policy)
        task.deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        request = TaskEnqueueRequest(task=task, priority=5)
        with pytest.raises(LaneError):
            await lane.enqueue_task(request)

    @pytest.mark.asyncio
    async def test_enqueue_task_idempotent(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test idempotent task returns same task_id."""
        lane = MainLane(tenant_id, policy)
        request1 = TaskEnqueueRequest(task=task, priority=5)
        request2 = TaskEnqueueRequest(task=task, priority=7)
        
        id1 = await lane.enqueue_task(request1)
        id2 = await lane.enqueue_task(request2)
        
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_enqueue_task_queue_full(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test enqueue raises when queue full."""
        policy.max_queue_depth = 2
        lane = MainLane(tenant_id, policy)
        
        task1 = Task(
            task_id=uuid4(),
            goal={},
            user_id="u1",
            tenant_id=tenant_id,
            idempotency_key="key1",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        task2 = Task(
            task_id=uuid4(),
            goal={},
            user_id="u2",
            tenant_id=tenant_id,
            idempotency_key="key2",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        task3 = Task(
            task_id=uuid4(),
            goal={},
            user_id="u3",
            tenant_id=tenant_id,
            idempotency_key="key3",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        
        await lane.enqueue_task(TaskEnqueueRequest(task=task1, priority=5))
        await lane.enqueue_task(TaskEnqueueRequest(task=task2, priority=5))
        
        with pytest.raises(QueueFullError):
            await lane.enqueue_task(TaskEnqueueRequest(task=task3, priority=5))

    @pytest.mark.asyncio
    async def test_dequeue_respects_priority(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test dequeue returns highest priority first."""
        lane = MainLane(tenant_id, policy)
        
        task_low = Task(
            task_id=uuid4(),
            goal={},
            user_id="u1",
            tenant_id=tenant_id,
            idempotency_key="key_low",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        task_high = Task(
            task_id=uuid4(),
            goal={},
            user_id="u2",
            tenant_id=tenant_id,
            idempotency_key="key_high",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        
        await lane.enqueue_task(TaskEnqueueRequest(task=task_low, priority=2))
        await lane.enqueue_task(TaskEnqueueRequest(task=task_high, priority=9))
        
        next_task = await asyncio.wait_for(
            lane.dequeue_next_task(), timeout=1.0
        )
        assert next_task.task_id == task_high.task_id

    @pytest.mark.asyncio
    async def test_is_full(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test is_full detection."""
        policy.max_queue_depth = 1
        lane = MainLane(tenant_id, policy)
        
        assert not await lane.is_full()
        await lane.enqueue_task(TaskEnqueueRequest(task=task, priority=5))
        assert await lane.is_full()


# ---------------------------------------------------------------------------
# CronLane Tests
# ---------------------------------------------------------------------------


class TestCronLane:
    """Tests for CronLane class."""

    @pytest.mark.asyncio
    async def test_cron_lane_creation(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test CronLane creation."""
        lane = CronLane(tenant_id, policy)
        assert lane.lane_type == LaneType.CRON
        assert len(lane.schedule_map) == 0

    @pytest.mark.asyncio
    async def test_schedule_task_success(
        self,
        tenant_id: str,
        scheduled_task: ScheduledTask,
        policy: LanePolicy,
    ) -> None:
        """Test successful task scheduling."""
        lane = CronLane(tenant_id, policy)
        request = ScheduledTaskRequest(scheduled_task=scheduled_task)
        schedule_id = await lane.schedule_task(request)
        assert schedule_id == scheduled_task.schedule_id
        assert schedule_id in lane.schedule_map

    @pytest.mark.asyncio
    async def test_schedule_task_past_time(
        self,
        tenant_id: str,
        scheduled_task: ScheduledTask,
        policy: LanePolicy,
    ) -> None:
        """Test schedule raises for past time."""
        lane = CronLane(tenant_id, policy)
        scheduled_task.scheduled_time = datetime.now(timezone.utc) - timedelta(
            hours=1
        )
        request = ScheduledTaskRequest(scheduled_task=scheduled_task)
        with pytest.raises(InvalidScheduleError):
            await lane.schedule_task(request)

    @pytest.mark.asyncio
    async def test_schedule_task_queue_full(
        self,
        tenant_id: str,
        policy: LanePolicy,
    ) -> None:
        """Test schedule raises when full."""
        policy.max_queue_depth = 1
        lane = CronLane(tenant_id, policy)
        
        now = datetime.now(timezone.utc)
        
        sched1 = ScheduledTask(
            task=Task(
                task_id=uuid4(),
                goal={},
                user_id="u1",
                tenant_id=tenant_id,
                idempotency_key="key1",
                resource_budget={},
                mcp_tools=[],
                context={},
            ),
            scheduled_time=now + timedelta(hours=1),
        )
        sched2 = ScheduledTask(
            task=Task(
                task_id=uuid4(),
                goal={},
                user_id="u2",
                tenant_id=tenant_id,
                idempotency_key="key2",
                resource_budget={},
                mcp_tools=[],
                context={},
            ),
            scheduled_time=now + timedelta(hours=2),
        )
        
        await lane.schedule_task(ScheduledTaskRequest(scheduled_task=sched1))
        with pytest.raises(QueueFullError):
            await lane.schedule_task(ScheduledTaskRequest(scheduled_task=sched2))

    @pytest.mark.asyncio
    async def test_evaluate_due_tasks_none(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test evaluate returns empty when no due tasks."""
        lane = CronLane(tenant_id, policy)
        due = await lane.evaluate_due_tasks()
        assert due == []

    @pytest.mark.asyncio
    async def test_evaluate_due_tasks_some(
        self,
        tenant_id: str,
        policy: LanePolicy,
    ) -> None:
        """Test evaluate returns due tasks."""
        lane = CronLane(tenant_id, policy)
        
        now = datetime.now(timezone.utc)
        
        due_sched = ScheduledTask(
            task=Task(
                task_id=uuid4(),
                goal={},
                user_id="u1",
                tenant_id=tenant_id,
                idempotency_key="key_due",
                resource_budget={},
                mcp_tools=[],
                context={},
            ),
            scheduled_time=now - timedelta(minutes=1),
        )
        future_sched = ScheduledTask(
            task=Task(
                task_id=uuid4(),
                goal={},
                user_id="u2",
                tenant_id=tenant_id,
                idempotency_key="key_future",
                resource_budget={},
                mcp_tools=[],
                context={},
            ),
            scheduled_time=now + timedelta(hours=1),
        )
        
        await lane.schedule_task(ScheduledTaskRequest(scheduled_task=due_sched))
        await lane.schedule_task(
            ScheduledTaskRequest(scheduled_task=future_sched)
        )
        
        due = await lane.evaluate_due_tasks()
        assert len(due) == 1
        assert due[0].schedule_id == due_sched.schedule_id

    @pytest.mark.asyncio
    async def test_get_next_execution_time(
        self,
        tenant_id: str,
        scheduled_task: ScheduledTask,
        policy: LanePolicy,
    ) -> None:
        """Test get_next_execution_time."""
        lane = CronLane(tenant_id, policy)
        assert lane.get_next_execution_time() is None
        
        await lane.schedule_task(ScheduledTaskRequest(scheduled_task=scheduled_task))
        next_time = lane.get_next_execution_time()
        assert next_time == scheduled_task.scheduled_time


# ---------------------------------------------------------------------------
# SubagentLane Tests
# ---------------------------------------------------------------------------


class TestSubagentLane:
    """Tests for SubagentLane class."""

    @pytest.mark.asyncio
    async def test_subagent_lane_creation(
        self, tenant_id: str, policy: LanePolicy
    ) -> None:
        """Test SubagentLane creation."""
        lane = SubagentLane(tenant_id, policy)
        assert lane.lane_type == LaneType.SUBAGENT
        assert lane.concurrent_count == 0

    @pytest.mark.asyncio
    async def test_spawn_subagent_success(
        self, tenant_id: str, subagent_task: SubagentTask, policy: LanePolicy
    ) -> None:
        """Test successful subagent spawn."""
        lane = SubagentLane(tenant_id, policy)
        request = SubagentSpawnRequest(subagent_task=subagent_task, priority=5)
        exec_id = await lane.spawn_subagent(request)
        assert exec_id == subagent_task.subagent_execution_id
        assert lane.concurrent_count == 1

    @pytest.mark.asyncio
    async def test_spawn_subagent_expired(
        self, tenant_id: str, subagent_task: SubagentTask, policy: LanePolicy
    ) -> None:
        """Test spawn raises for expired task."""
        lane = SubagentLane(tenant_id, policy)
        subagent_task.deadline = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        request = SubagentSpawnRequest(subagent_task=subagent_task, priority=5)
        with pytest.raises(LaneError):
            await lane.spawn_subagent(request)

    @pytest.mark.asyncio
    async def test_mark_complete(
        self, tenant_id: str, subagent_task: SubagentTask, policy: LanePolicy
    ) -> None:
        """Test mark_complete decrements counter."""
        lane = SubagentLane(tenant_id, policy)
        await lane.spawn_subagent(SubagentSpawnRequest(subagent_task=subagent_task))
        assert lane.concurrent_count == 1
        
        await lane.mark_complete(subagent_task.subagent_execution_id)
        assert lane.concurrent_count == 0

    @pytest.mark.asyncio
    async def test_get_concurrency_percentage(
        self, tenant_id: str, subagent_task: SubagentTask, policy: LanePolicy
    ) -> None:
        """Test concurrency percentage calculation."""
        lane = SubagentLane(tenant_id, policy)
        assert lane.get_concurrency_percentage() == 0.0
        
        await lane.spawn_subagent(SubagentSpawnRequest(subagent_task=subagent_task))
        percent = lane.get_concurrency_percentage()
        assert 0 < percent < 100


# ---------------------------------------------------------------------------
# LaneManager Tests
# ---------------------------------------------------------------------------


class TestLaneManager:
    """Tests for LaneManager class."""

    @pytest.mark.asyncio
    async def test_lane_manager_creation(self, policy: LanePolicy) -> None:
        """Test LaneManager creation."""
        manager = LaneManager(policy)
        assert manager.policy == policy

    @pytest.mark.asyncio
    async def test_enqueue_main_task(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test enqueue via manager."""
        manager = LaneManager(policy)
        request = TaskEnqueueRequest(task=task, priority=5)
        task_id = await manager.enqueue_main_task(request)
        assert task_id == task.task_id

    @pytest.mark.asyncio
    async def test_schedule_cron_task(
        self,
        tenant_id: str,
        scheduled_task: ScheduledTask,
        policy: LanePolicy,
    ) -> None:
        """Test schedule via manager."""
        manager = LaneManager(policy)
        request = ScheduledTaskRequest(scheduled_task=scheduled_task)
        schedule_id = await manager.schedule_cron_task(request)
        assert schedule_id == scheduled_task.schedule_id

    @pytest.mark.asyncio
    async def test_spawn_subagent(
        self, tenant_id: str, subagent_task: SubagentTask, policy: LanePolicy
    ) -> None:
        """Test spawn via manager."""
        manager = LaneManager(policy)
        request = SubagentSpawnRequest(subagent_task=subagent_task, priority=5)
        exec_id = await manager.spawn_subagent(request)
        assert exec_id == subagent_task.subagent_execution_id

    @pytest.mark.asyncio
    async def test_get_lane(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test get_lane retrieval."""
        manager = LaneManager(policy)
        
        # Lane doesn't exist yet
        lane = manager.get_lane(tenant_id, LaneType.MAIN)
        assert lane is None
        
        # Create it
        await manager.enqueue_main_task(TaskEnqueueRequest(task=task, priority=5))
        
        # Now it exists
        lane = manager.get_lane(tenant_id, LaneType.MAIN)
        assert lane is not None
        assert isinstance(lane, MainLane)

    @pytest.mark.asyncio
    async def test_get_lane_stats(
        self, tenant_id: str, task: Task, policy: LanePolicy
    ) -> None:
        """Test lane statistics."""
        manager = LaneManager(policy)
        await manager.enqueue_main_task(TaskEnqueueRequest(task=task, priority=5))
        
        stats = manager.get_lane_stats(tenant_id)
        assert "main" in stats
        assert "queue_size" in stats["main"]
        assert "queue_depth_percent" in stats["main"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
