"""Integration tests for holly.engine.lanes module."""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from holly.engine.lanes import (
    Task,
    TaskEnqueueRequest,
    ScheduledTask,
    ScheduledTaskRequest,
    SubagentTask,
    SubagentSpawnRequest,
    LanePolicy,
    MainLane,
    CronLane,
    SubagentLane,
    LaneManager,
    LaneType,
)


@pytest.fixture
def policy() -> LanePolicy:
    """Create a test policy."""
    return LanePolicy(
        max_queue_depth=20,
        max_concurrency=10,
        backpressure_timeout=5.0,
    )


class TestMainLaneIntegration:
    """Integration tests for MainLane."""

    @pytest.mark.asyncio
    async def test_concurrent_task_enqueue(self, policy: LanePolicy) -> None:
        """Test concurrent enqueue to main lane."""
        lane = MainLane("tenant-001", policy)
        
        tasks = [
            Task(
                task_id=uuid4(),
                goal={"desc": f"task_{i}"},
                user_id=f"user_{i}",
                tenant_id="tenant-001",
                idempotency_key=f"key_{i}",
                resource_budget={},
                mcp_tools=[],
                context={},
            )
            for i in range(5)
        ]
        
        requests = [
            TaskEnqueueRequest(task=task, priority=i % 10)
            for i, task in enumerate(tasks)
        ]
        
        # Enqueue all concurrently
        results = await asyncio.gather(
            *[lane.enqueue_task(req) for req in requests]
        )
        
        assert len(results) == 5
        assert all(results[i] == tasks[i].task_id for i in range(5))

    @pytest.mark.asyncio
    async def test_priority_order_under_load(self, policy: LanePolicy) -> None:
        """Test priority ordering with multiple tasks."""
        lane = MainLane("tenant-001", policy)
        
        # Enqueue in mixed priority order
        priorities = [2, 8, 3, 9, 1]
        task_ids = []
        
        for i, priority in enumerate(priorities):
            task = Task(
                task_id=uuid4(),
                goal={"priority": priority},
                user_id=f"user_{i}",
                tenant_id="tenant-001",
                idempotency_key=f"key_{i}",
                resource_budget={},
                mcp_tools=[],
                context={},
            )
            task_ids.append((task.task_id, priority))
            await lane.enqueue_task(TaskEnqueueRequest(task=task, priority=priority))
        
        # Dequeue and verify priority order
        dequeued_tasks = []
        for _ in range(5):
            task = await asyncio.wait_for(lane.dequeue_next_task(), timeout=1.0)
            dequeued_tasks.append((task.task_id, task.goal.get("priority")))
        
        # Should be in descending priority order
        priorities_dequeued = [p for _, p in dequeued_tasks]
        assert priorities_dequeued == sorted(priorities_dequeued, reverse=True)


class TestCronLaneIntegration:
    """Integration tests for CronLane."""

    @pytest.mark.asyncio
    async def test_scheduled_task_lifecycle(self, policy: LanePolicy) -> None:
        """Test full lifecycle of scheduled tasks."""
        lane = CronLane("tenant-001", policy)
        
        now = datetime.now(timezone.utc)
        
        # Schedule multiple tasks at different times
        sched_times = [
            now + timedelta(hours=1),
            now + timedelta(minutes=30),
            now + timedelta(hours=2),
            now + timedelta(minutes=15),
        ]
        
        scheduled_ids = []
        for i, sched_time in enumerate(sched_times):
            sched_task = ScheduledTask(
                task=Task(
                    task_id=uuid4(),
                    goal={"time": sched_time.isoformat()},
                    user_id="user",
                    tenant_id="tenant-001",
                    idempotency_key=f"sched_key_{i}",
                    resource_budget={},
                    mcp_tools=[],
                    context={},
                ),
                scheduled_time=sched_time,
            )
            schedule_id = await lane.schedule_task(
                ScheduledTaskRequest(scheduled_task=sched_task)
            )
            scheduled_ids.append((schedule_id, sched_time))
        
        # Verify they're ordered
        next_time = lane.get_next_execution_time()
        assert next_time == min(st[1] for st in scheduled_ids)

    @pytest.mark.asyncio
    async def test_evaluate_many_due_tasks(self, policy: LanePolicy) -> None:
        """Test evaluation with many due tasks."""
        lane = CronLane("tenant-001", policy)
        
        now = datetime.now(timezone.utc)
        
        # Schedule 10 tasks all due in the past
        for i in range(10):
            sched_task = ScheduledTask(
                task=Task(
                    task_id=uuid4(),
                    goal={},
                    user_id="user",
                    tenant_id="tenant-001",
                    idempotency_key=f"due_key_{i}",
                    resource_budget={},
                    mcp_tools=[],
                    context={},
                ),
                scheduled_time=now - timedelta(seconds=i),
            )
            await lane.schedule_task(
                ScheduledTaskRequest(scheduled_task=sched_task)
            )
        
        # Evaluate
        due = await lane.evaluate_due_tasks()
        assert len(due) == 10


class TestSubagentLaneIntegration:
    """Integration tests for SubagentLane."""

    @pytest.mark.asyncio
    async def test_concurrent_agent_spawns(self, policy: LanePolicy) -> None:
        """Test concurrent subagent spawns."""
        lane = SubagentLane("tenant-001", policy)
        
        spawn_requests = []
        for i in range(5):
            subagent_task = SubagentTask(
                agent_binding={"agent_id": f"agent_{i}"},
                goals=[{"goal": f"goal_{i}"}],
                parent_execution_id=uuid4(),
                user_id="user",
                tenant_id="tenant-001",
                message_queue=f"queue_{i}",
            )
            spawn_requests.append(
                SubagentSpawnRequest(subagent_task=subagent_task, priority=5)
            )
        
        # Spawn all concurrently
        results = await asyncio.gather(
            *[lane.spawn_subagent(req) for req in spawn_requests]
        )
        
        assert len(results) == 5
        assert lane.concurrent_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_task_lifecycle(self, policy: LanePolicy) -> None:
        """Test concurrent spawn and complete."""
        lane = SubagentLane("tenant-001", policy)
        
        # Spawn several tasks
        exec_ids = []
        for i in range(3):
            subagent_task = SubagentTask(
                agent_binding={"agent_id": f"agent_{i}"},
                goals=[],
                parent_execution_id=uuid4(),
                user_id="user",
                tenant_id="tenant-001",
                message_queue=f"queue_{i}",
            )
            exec_id = await lane.spawn_subagent(
                SubagentSpawnRequest(subagent_task=subagent_task, priority=5)
            )
            exec_ids.append(exec_id)
        
        assert lane.concurrent_count == 3
        
        # Complete them
        for exec_id in exec_ids:
            await lane.mark_complete(exec_id)
        
        assert lane.concurrent_count == 0


class TestLaneManagerIntegration:
    """Integration tests for LaneManager."""

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, policy: LanePolicy) -> None:
        """Test that tenants are properly isolated."""
        manager = LaneManager(policy)
        
        # Enqueue to different tenants
        for tenant_id in ["tenant-001", "tenant-002"]:
            task = Task(
                task_id=uuid4(),
                goal={"tenant": tenant_id},
                user_id="user",
                tenant_id=tenant_id,
                idempotency_key=f"key_{tenant_id}",
                resource_budget={},
                mcp_tools=[],
                context={},
            )
            await manager.enqueue_main_task(
                TaskEnqueueRequest(task=task, priority=5)
            )
        
        # Get lanes
        lane1 = manager.get_lane("tenant-001", LaneType.MAIN)
        lane2 = manager.get_lane("tenant-002", LaneType.MAIN)
        
        assert lane1 is not None
        assert lane2 is not None
        assert lane1 != lane2

    @pytest.mark.asyncio
    async def test_multi_lane_operations(self, policy: LanePolicy) -> None:
        """Test operations across multiple lane types."""
        manager = LaneManager(policy)
        tenant_id = "tenant-001"
        now = datetime.now(timezone.utc)
        
        # Enqueue main task
        main_task = Task(
            task_id=uuid4(),
            goal={},
            user_id="user",
            tenant_id=tenant_id,
            idempotency_key="key_main",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        main_id = await manager.enqueue_main_task(
            TaskEnqueueRequest(task=main_task, priority=5)
        )
        
        # Schedule cron task
        cron_task = Task(
            task_id=uuid4(),
            goal={},
            user_id="user",
            tenant_id=tenant_id,
            idempotency_key="key_cron",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        sched = ScheduledTask(
            task=cron_task,
            scheduled_time=now + timedelta(hours=1),
        )
        cron_id = await manager.schedule_cron_task(
            ScheduledTaskRequest(scheduled_task=sched)
        )
        
        # Spawn subagent
        subagent = SubagentTask(
            agent_binding={},
            goals=[],
            parent_execution_id=uuid4(),
            user_id="user",
            tenant_id=tenant_id,
            message_queue="queue",
        )
        agent_id = await manager.spawn_subagent(
            SubagentSpawnRequest(subagent_task=subagent, priority=5)
        )
        
        # Verify all lanes exist
        assert manager.get_lane(tenant_id, LaneType.MAIN) is not None
        assert manager.get_lane(tenant_id, LaneType.CRON) is not None
        assert manager.get_lane(tenant_id, LaneType.SUBAGENT) is not None

    @pytest.mark.asyncio
    async def test_lane_statistics(self, policy: LanePolicy) -> None:
        """Test lane statistics collection."""
        manager = LaneManager(policy)
        tenant_id = "tenant-001"
        
        # No stats for non-existent tenant
        stats = manager.get_lane_stats(tenant_id)
        assert stats == {}
        
        # Add tasks
        task = Task(
            task_id=uuid4(),
            goal={},
            user_id="user",
            tenant_id=tenant_id,
            idempotency_key="key",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        await manager.enqueue_main_task(
            TaskEnqueueRequest(task=task, priority=5)
        )
        
        # Get stats
        stats = manager.get_lane_stats(tenant_id)
        assert "main" in stats
        assert stats["main"]["queue_size"] == 1


class TestCrossLaneInteractions:
    """Integration tests for interactions between lanes."""

    @pytest.mark.asyncio
    async def test_lane_policy_enforces_depth(self, policy: LanePolicy) -> None:
        """Test policy enforcement across lanes."""
        policy.max_queue_depth = 5
        manager = LaneManager(policy)
        tenant_id = "tenant-001"
        
        # Fill main lane
        for i in range(5):
            task = Task(
                task_id=uuid4(),
                goal={},
                user_id="user",
                tenant_id=tenant_id,
                idempotency_key=f"key_{i}",
                resource_budget={},
                mcp_tools=[],
                context={},
            )
            await manager.enqueue_main_task(
                TaskEnqueueRequest(task=task, priority=5)
            )
        
        # Next enqueue should fail
        from holly.engine.lanes import QueueFullError
        task_overflow = Task(
            task_id=uuid4(),
            goal={},
            user_id="user",
            tenant_id=tenant_id,
            idempotency_key="key_overflow",
            resource_budget={},
            mcp_tools=[],
            context={},
        )
        with pytest.raises(QueueFullError):
            await manager.enqueue_main_task(
                TaskEnqueueRequest(task=task_overflow, priority=5)
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
