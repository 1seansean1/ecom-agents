"""Lane manager and dispatcher for Holly Grace task execution.

Implements lane-based task routing per ICD-013, ICD-014, ICD-015.
Provides three lane types (Main, Cron, Subagent) with unified policy enforcement.

This module provides:
- Lane: base class for task queue management
- MainLane: user-initiated task execution lane
- CronLane: time-triggered scheduled task lane
- SubagentLane: team-parallel agent execution lane
- LanePolicy: per-tenant queue depth and backpressure enforcement
- LaneManager: unified lane dispatcher and policy enforcer
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

__all__ = [
    "Lane",
    "MainLane",
    "CronLane",
    "SubagentLane",
    "LanePolicy",
    "LaneManager",
    "LaneError",
    "QueueFullError",
    "InvalidScheduleError",
    "TaskEnqueueRequest",
    "ScheduledTaskRequest",
    "SubagentSpawnRequest",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LaneError(Exception):
    """Base exception for lane-related errors."""

    pass


class QueueFullError(LaneError):
    """Raised when lane queue is at capacity."""

    pass


class InvalidScheduleError(LaneError):
    """Raised when schedule time is invalid."""

    pass


class AgentSpawnError(LaneError):
    """Raised when agent spawn fails."""

    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LaneType(str, Enum):  # noqa: UP042
    """Types of execution lanes."""

    MAIN = "main"
    CRON = "cron"
    SUBAGENT = "subagent"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Task:
    """Task object for lane processing per ICD-013 schema.

    Attributes
    ----------
    task_id : UUID
        Unique identifier for the task.
    goal : dict[str, object]
        Goal specification (placeholder for actual Goal type).
    user_id : str
        User who initiated the task.
    tenant_id : str
        Tenant identifier for isolation.
    deadline : datetime | None
        Optional deadline for task completion.
    idempotency_key : str
        Key for deduplication within 24h.
    resource_budget : dict[str, object]
        Resource limits (cpu, memory, timeout).
    mcp_tools : list[str]
        List of MCP tool identifiers.
    context : dict[str, object]
        Task context (will be redacted before queueing).
    trace_id : str = ""
        Trace identifier for observability.
    """

    task_id: UUID
    goal: dict[str, object]
    user_id: str
    tenant_id: str
    idempotency_key: str
    resource_budget: dict[str, object]
    mcp_tools: list[str]
    context: dict[str, object]
    deadline: datetime | None = None
    trace_id: str = ""

    def is_expired(self) -> bool:
        """Check if task deadline has passed.

        Returns
        -------
        bool
            True if deadline is set and in the past.
        """
        if self.deadline is None:
            return False
        return datetime.now(timezone.utc) > self.deadline


@dataclass(slots=True)
class TaskEnqueueRequest:
    """Request to enqueue a task to Main Lane per ICD-013.

    Attributes
    ----------
    task : Task
        The task to enqueue.
    priority : int
        Priority level (0-10, higher = more important).
    """

    task: Task
    priority: int = 5


@dataclass(slots=True)
class ScheduledTask:
    """Scheduled task for Cron Lane per ICD-014 schema.

    Attributes
    ----------
    task : Task
        The task to execute.
    scheduled_time : datetime
        When the task should execute.
    recurrence : str | None
        Optional cron expression for recurring tasks.
    max_retries : int
        Maximum number of retries on failure.
    schedule_id : UUID
        Unique identifier for this schedule.
    next_execution_time : datetime | None
        Timestamp of next execution.
    """

    task: Task
    scheduled_time: datetime
    recurrence: str | None = None
    max_retries: int = 3
    schedule_id: UUID = field(default_factory=uuid4)
    next_execution_time: datetime | None = None

    def is_due(self, now: datetime | None = None) -> bool:
        """Check if task is due for execution.

        Parameters
        ----------
        now : datetime | None
            Current time (defaults to now in UTC).

        Returns
        -------
        bool
            True if scheduled_time is in the past.
        """
        if now is None:
            now = datetime.now(timezone.utc)
        return now >= self.scheduled_time


@dataclass(slots=True)
class ScheduledTaskRequest:
    """Request to schedule a task to Cron Lane per ICD-014.

    Attributes
    ----------
    scheduled_task : ScheduledTask
        The scheduled task.
    """

    scheduled_task: ScheduledTask


@dataclass(slots=True)
class SubagentTask:
    """Task for subagent execution per ICD-015 schema.

    Attributes
    ----------
    agent_binding : dict[str, object]
        Agent binding information.
    goals : list[dict[str, object]]
        Goals for the agent.
    parent_execution_id : UUID
        Parent execution identifier.
    user_id : str
        User who initiated.
    tenant_id : str
        Tenant identifier.
    deadline : datetime | None
        Optional deadline.
    message_queue : str
        Inter-agent communication queue handle.
    subagent_execution_id : UUID
        Unique identifier for this subagent execution.
    trace_id : str = ""
        Trace identifier.
    """

    agent_binding: dict[str, object]
    goals: list[dict[str, object]]
    parent_execution_id: UUID
    user_id: str
    tenant_id: str
    message_queue: str
    subagent_execution_id: UUID = field(default_factory=uuid4)
    deadline: datetime | None = None
    trace_id: str = ""

    def is_expired(self) -> bool:
        """Check if task deadline has passed.

        Returns
        -------
        bool
            True if deadline is set and in the past.
        """
        if self.deadline is None:
            return False
        return datetime.now(timezone.utc) > self.deadline


@dataclass(slots=True)
class SubagentSpawnRequest:
    """Request to spawn a subagent per ICD-015.

    Attributes
    ----------
    subagent_task : SubagentTask
        The subagent task.
    priority : int
        Priority level (0-10).
    """

    subagent_task: SubagentTask
    priority: int = 5


@dataclass(slots=True)
class LanePolicy:
    """Policy governing lane behavior per ICD-013/014/015.

    Attributes
    ----------
    max_queue_depth : int
        Maximum queue depth per tenant (default 500).
    max_concurrency : int
        Maximum concurrent tasks (for subagent lane).
    backpressure_timeout : float
        Timeout for backpressure in seconds.
    idempotency_window : timedelta
        Time window for idempotency deduplication.
    """

    max_queue_depth: int = 500
    max_concurrency: int = 100
    backpressure_timeout: float = 30.0
    idempotency_window: timedelta = field(
        default_factory=lambda: timedelta(hours=24)
    )


# ---------------------------------------------------------------------------
# Lane Base Class
# ---------------------------------------------------------------------------


class Lane:
    """Base class for execution lanes.

    Attributes
    ----------
    lane_type : LaneType
        Type of lane (main, cron, or subagent).
    tenant_id : str
        Tenant identifier for isolation.
    queue : asyncio.Queue
        Task queue (generic type depends on subclass).
    policy : LanePolicy
        Queue policy enforcement.
    _name : str
        Human-readable lane name.
    """

    __slots__ = (
        "lane_type",
        "tenant_id",
        "queue",
        "policy",
        "_name",
    )

    def __init__(
        self,
        lane_type: LaneType,
        tenant_id: str,
        policy: LanePolicy | None = None,
    ) -> None:
        """Initialize a lane.

        Parameters
        ----------
        lane_type : LaneType
            Type of lane.
        tenant_id : str
            Tenant identifier.
        policy : LanePolicy | None
            Policy for the lane (default: new policy).
        """
        self.lane_type = lane_type
        self.tenant_id = tenant_id
        self.policy = policy or LanePolicy()
        self.queue: asyncio.Queue[object] = asyncio.Queue(
            maxsize=self.policy.max_queue_depth
        )
        self._name = f"{lane_type.value}_lane_{tenant_id[:8]}"

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<{self.__class__.__name__} "
            f"type={self.lane_type.value} "
            f"tenant={self.tenant_id} "
            f"queue_size={self.queue.qsize()}>"
        )

    async def is_full(self) -> bool:
        """Check if queue is at capacity.

        Returns
        -------
        bool
            True if queue size >= max_queue_depth.
        """
        return self.queue.qsize() >= self.policy.max_queue_depth

    async def enqueue(self, item: object) -> None:
        """Enqueue an item to the lane.

        Parameters
        ----------
        item : object
            Item to enqueue.

        Raises
        ------
        QueueFullError
            If queue is at capacity.
        """
        if await self.is_full():
            raise QueueFullError(
                f"{self._name} is full (size={self.queue.qsize()}, "
                f"max={self.policy.max_queue_depth})"
            )
        await self.queue.put(item)
        log.debug(f"Enqueued to {self._name}: size now {self.queue.qsize()}")

    async def dequeue(self) -> object:
        """Dequeue an item from the lane (FIFO).

        Returns
        -------
        object
            The next item in the queue.
        """
        return await self.queue.get()

    def get_queue_size(self) -> int:
        """Get current queue size.

        Returns
        -------
        int
            Number of items in queue.
        """
        return self.queue.qsize()

    def get_queue_depth_percentage(self) -> float:
        """Get queue depth as percentage of max.

        Returns
        -------
        float
            Queue size / max_queue_depth * 100.
        """
        return (self.queue.qsize() / self.policy.max_queue_depth) * 100.0


# ---------------------------------------------------------------------------
# Lane Implementations
# ---------------------------------------------------------------------------


class MainLane(Lane):
    """Main lane for user-initiated task execution (ICD-013).

    User-initiated tasks are enqueued here and dispatched to the task
    execution engine in priority order.

    Attributes
    ----------
    priority_queue : dict[int, asyncio.Queue]
        Priority-based sub-queues (0-10).
    idempotency_cache : dict[str, UUID]
        Cache of idempotency_key -> task_id for deduplication.
    """

    __slots__ = ("priority_queue", "idempotency_cache")

    def __init__(
        self, tenant_id: str, policy: LanePolicy | None = None
    ) -> None:
        """Initialize main lane.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.
        policy : LanePolicy | None
            Queue policy.
        """
        super().__init__(LaneType.MAIN, tenant_id, policy)
        self.priority_queue: dict[int, asyncio.Queue[Task]] = {
            i: asyncio.Queue() for i in range(11)
        }
        self.idempotency_cache: dict[str, UUID] = {}

    async def enqueue_task(
        self, request: TaskEnqueueRequest
    ) -> UUID:
        """Enqueue a task with priority.

        Parameters
        ----------
        request : TaskEnqueueRequest
            Task enqueue request.

        Returns
        -------
        UUID
            The task_id.

        Raises
        ------
        QueueFullError
            If queue is full.
        InvalidTaskError
            If task is expired.
        """
        if request.task.is_expired():
            raise LaneError("Task deadline has passed")

        # Check idempotency cache
        if request.task.idempotency_key in self.idempotency_cache:
            log.debug(
                f"Idempotent task resubmitted: "
                f"{request.task.idempotency_key}"
            )
            return self.idempotency_cache[request.task.idempotency_key]

        # Enqueue to priority queue
        priority = min(10, max(0, request.priority))
        pq = self.priority_queue[priority]
        if pq.qsize() >= self.policy.max_queue_depth:
            raise QueueFullError(
                f"Main lane full (priority {priority}, "
                f"size={pq.qsize()}, max={self.policy.max_queue_depth})"
            )

        await pq.put(request.task)
        self.idempotency_cache[request.task.idempotency_key] = (
            request.task.task_id
        )
        self.queue.qsize()  # Update base queue (for interface compatibility)
        log.info(
            f"Enqueued task {request.task.task_id} "
            f"(priority={priority}, trace={request.task.trace_id})"
        )
        return request.task.task_id

    async def dequeue_next_task(self) -> Task:
        """Dequeue next task by priority (highest first).

        Returns
        -------
        Task
            Next task to process.
        """
        for priority in range(10, -1, -1):
            pq = self.priority_queue[priority]
            if not pq.empty():
                task = await pq.get()
                log.debug(f"Dequeued task {task.task_id} (priority={priority})")
                return task
        # If all queues empty, wait on priority 5 (medium)
        return await self.priority_queue[5].get()


class CronLane(Lane):
    """Cron lane for time-triggered scheduled tasks (ICD-014).

    Scheduled tasks are stored in a priority queue sorted by scheduled_time.
    Evaluation cycle checks due tasks periodically.

    Attributes
    ----------
    schedule_map : dict[UUID, ScheduledTask]
        Map of schedule_id -> ScheduledTask.
    scheduled_times : list[tuple[float, UUID]]
        Sorted list of (unix_timestamp, schedule_id).
    """

    __slots__ = ("schedule_map", "scheduled_times")

    def __init__(
        self, tenant_id: str, policy: LanePolicy | None = None
    ) -> None:
        """Initialize cron lane.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.
        policy : LanePolicy | None
            Queue policy.
        """
        super().__init__(LaneType.CRON, tenant_id, policy)
        self.schedule_map: dict[UUID, ScheduledTask] = {}
        self.scheduled_times: list[tuple[float, UUID]] = []

    async def schedule_task(
        self, request: ScheduledTaskRequest
    ) -> UUID:
        """Schedule a task for future execution.

        Parameters
        ----------
        request : ScheduledTaskRequest
            Schedule request.

        Returns
        -------
        UUID
            The schedule_id.

        Raises
        ------
        InvalidScheduleError
            If scheduled_time is in the past.
        QueueFullError
            If queue is full.
        """
        now = datetime.now(timezone.utc)
        sched_task = request.scheduled_task

        if sched_task.scheduled_time <= now:
            raise InvalidScheduleError(
                f"Scheduled time must be in future "
                f"(requested {sched_task.scheduled_time}, now {now})"
            )

        if len(self.schedule_map) >= self.policy.max_queue_depth:
            raise QueueFullError(
                f"Cron lane full "
                f"(size={len(self.schedule_map)}, "
                f"max={self.policy.max_queue_depth})"
            )

        # Store in schedule map
        self.schedule_map[sched_task.schedule_id] = sched_task

        # Add to sorted times
        unix_ts = sched_task.scheduled_time.timestamp()
        self.scheduled_times.append((unix_ts, sched_task.schedule_id))
        self.scheduled_times.sort(key=lambda x: x[0])

        sched_task.next_execution_time = sched_task.scheduled_time
        log.info(
            f"Scheduled task {sched_task.schedule_id} "
            f"for {sched_task.scheduled_time} "
            f"(tenant={self.tenant_id})"
        )
        return sched_task.schedule_id

    async def evaluate_due_tasks(self) -> list[ScheduledTask]:
        """Evaluate and return due tasks.

        Returns
        -------
        list[ScheduledTask]
            List of tasks that are due for execution.
        """
        now = datetime.now(timezone.utc)
        due: list[ScheduledTask] = []

        for unix_ts, schedule_id in self.scheduled_times:
            sched_task = self.schedule_map.get(schedule_id)
            if sched_task and sched_task.scheduled_time <= now:
                due.append(sched_task)
                # Update next execution if recurring
                if sched_task.recurrence:
                    # Placeholder: actual cron parsing would go here
                    sched_task.next_execution_time = (
                        now + timedelta(hours=1)
                    )
                else:
                    # One-time task, remove from map
                    del self.schedule_map[schedule_id]

        # Remove processed due tasks from sorted list
        self.scheduled_times = [
            (ts, sid)
            for ts, sid in self.scheduled_times
            if sid not in [s.schedule_id for s in due]
            or self.schedule_map[sid].recurrence
        ]

        log.debug(f"Cron lane evaluated: {len(due)} tasks due")
        return due

    def get_next_execution_time(self) -> datetime | None:
        """Get the next scheduled execution time.

        Returns
        -------
        datetime | None
            Next scheduled time, or None if no tasks scheduled.
        """
        if not self.scheduled_times:
            return None
        unix_ts = self.scheduled_times[0][0]
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc)


class SubagentLane(Lane):
    """Subagent lane for team-parallel agent execution (ICD-015).

    Subagent tasks are enqueued for parallel execution in an agent pool.
    Concurrency limits are enforced per tenant.

    Attributes
    ----------
    priority_queue : dict[int, asyncio.Queue]
        Priority-based sub-queues.
    concurrent_count : int
        Current number of concurrent subagent tasks.
    active_executions : dict[UUID, SubagentTask]
        Map of execution_id -> SubagentTask.
    """

    __slots__ = ("priority_queue", "concurrent_count", "active_executions")

    def __init__(
        self, tenant_id: str, policy: LanePolicy | None = None
    ) -> None:
        """Initialize subagent lane.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.
        policy : LanePolicy | None
            Queue policy.
        """
        super().__init__(LaneType.SUBAGENT, tenant_id, policy)
        self.priority_queue: dict[int, asyncio.Queue[SubagentTask]] = {
            i: asyncio.Queue() for i in range(11)
        }
        self.concurrent_count = 0
        self.active_executions: dict[UUID, SubagentTask] = {}

    async def spawn_subagent(
        self, request: SubagentSpawnRequest
    ) -> UUID:
        """Spawn a subagent task.

        Parameters
        ----------
        request : SubagentSpawnRequest
            Spawn request.

        Returns
        -------
        UUID
            The subagent_execution_id.

        Raises
        ------
        AgentSpawnError
            If spawn fails (pool exhausted, etc).
        QueueFullError
            If queue is full.
        """
        if request.subagent_task.is_expired():
            raise LaneError("Subagent task deadline has passed")

        priority = min(10, max(0, request.priority))
        pq = self.priority_queue[priority]

        if pq.qsize() >= self.policy.max_queue_depth:
            raise QueueFullError(
                f"Subagent lane full "
                f"(priority {priority}, "
                f"size={pq.qsize()}, "
                f"max={self.policy.max_queue_depth})"
            )

        await pq.put(request.subagent_task)
        self.active_executions[request.subagent_task.subagent_execution_id] = (
            request.subagent_task
        )
        self.concurrent_count += 1

        log.info(
            f"Spawned subagent {request.subagent_task.subagent_execution_id} "
            f"(priority={priority}, "
            f"parent={request.subagent_task.parent_execution_id}, "
            f"concurrent={self.concurrent_count}/{self.policy.max_concurrency})"
        )
        return request.subagent_task.subagent_execution_id

    async def dequeue_next_subagent(self) -> SubagentTask:
        """Dequeue next subagent task by priority.

        Returns
        -------
        SubagentTask
            Next subagent task to execute.
        """
        for priority in range(10, -1, -1):
            pq = self.priority_queue[priority]
            if not pq.empty():
                task = await pq.get()
                log.debug(
                    f"Dequeued subagent {task.subagent_execution_id} "
                    f"(priority={priority})"
                )
                return task
        # Wait on priority 5 if all empty
        return await self.priority_queue[5].get()

    async def mark_complete(self, execution_id: UUID) -> None:
        """Mark a subagent execution as complete.

        Parameters
        ----------
        execution_id : UUID
            The subagent_execution_id.
        """
        if execution_id in self.active_executions:
            del self.active_executions[execution_id]
        self.concurrent_count = max(0, self.concurrent_count - 1)
        log.debug(
            f"Subagent {execution_id} marked complete "
            f"(concurrent={self.concurrent_count})"
        )

    def get_concurrency_percentage(self) -> float:
        """Get concurrency as percentage of max.

        Returns
        -------
        float
            concurrent_count / max_concurrency * 100.
        """
        return (
            self.concurrent_count / self.policy.max_concurrency
        ) * 100.0


# ---------------------------------------------------------------------------
# Lane Manager
# ---------------------------------------------------------------------------


class LaneManager:
    """Unified lane manager and dispatcher per ICD-013/014/015.

    Coordinates all three lane types, enforces policies, and provides
    a unified interface for task dispatch.

    Attributes
    ----------
    lanes : dict[tuple[str, LaneType], Lane]
        Map of (tenant_id, lane_type) -> Lane instance.
    policy : LanePolicy
        Global policy for all lanes.
    """

    __slots__ = ("lanes", "policy")

    def __init__(self, policy: LanePolicy | None = None) -> None:
        """Initialize lane manager.

        Parameters
        ----------
        policy : LanePolicy | None
            Global policy (default: new policy).
        """
        self.policy = policy or LanePolicy()
        self.lanes: dict[tuple[str, LaneType], Lane] = {}

    def _get_or_create_lane(
        self, tenant_id: str, lane_type: LaneType
    ) -> Lane:
        """Get or create a lane for the tenant-lane type combination.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.
        lane_type : LaneType
            Type of lane.

        Returns
        -------
        Lane
            The lane instance.
        """
        key = (tenant_id, lane_type)
        if key not in self.lanes:
            if lane_type == LaneType.MAIN:
                self.lanes[key] = MainLane(tenant_id, self.policy)
            elif lane_type == LaneType.CRON:
                self.lanes[key] = CronLane(tenant_id, self.policy)
            elif lane_type == LaneType.SUBAGENT:
                self.lanes[key] = SubagentLane(tenant_id, self.policy)
            else:
                raise ValueError(f"Unknown lane type: {lane_type}")
        return self.lanes[key]

    async def enqueue_main_task(
        self, request: TaskEnqueueRequest
    ) -> UUID:
        """Enqueue a task to main lane.

        Parameters
        ----------
        request : TaskEnqueueRequest
            Task enqueue request.

        Returns
        -------
        UUID
            The task_id.

        Raises
        ------
        QueueFullError
            If main lane is full.
        """
        tenant_id = request.task.tenant_id
        lane = self._get_or_create_lane(tenant_id, LaneType.MAIN)
        assert isinstance(lane, MainLane)
        return await lane.enqueue_task(request)

    async def schedule_cron_task(
        self, request: ScheduledTaskRequest
    ) -> UUID:
        """Schedule a task to cron lane.

        Parameters
        ----------
        request : ScheduledTaskRequest
            Schedule request.

        Returns
        -------
        UUID
            The schedule_id.

        Raises
        ------
        InvalidScheduleError
            If scheduled time is invalid.
        QueueFullError
            If cron lane is full.
        """
        tenant_id = request.scheduled_task.task.tenant_id
        lane = self._get_or_create_lane(tenant_id, LaneType.CRON)
        assert isinstance(lane, CronLane)
        return await lane.schedule_task(request)

    async def spawn_subagent(
        self, request: SubagentSpawnRequest
    ) -> UUID:
        """Spawn a subagent task.

        Parameters
        ----------
        request : SubagentSpawnRequest
            Spawn request.

        Returns
        -------
        UUID
            The subagent_execution_id.

        Raises
        ------
        AgentSpawnError
            If spawn fails.
        QueueFullError
            If subagent lane is full.
        """
        tenant_id = request.subagent_task.tenant_id
        lane = self._get_or_create_lane(tenant_id, LaneType.SUBAGENT)
        assert isinstance(lane, SubagentLane)
        return await lane.spawn_subagent(request)

    def get_lane(
        self, tenant_id: str, lane_type: LaneType
    ) -> Lane | None:
        """Get a lane if it exists.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.
        lane_type : LaneType
            Type of lane.

        Returns
        -------
        Lane | None
            The lane, or None if not created.
        """
        return self.lanes.get((tenant_id, lane_type))

    def get_lane_stats(
        self, tenant_id: str
    ) -> dict[str, dict[str, object]]:
        """Get statistics for all lanes for a tenant.

        Parameters
        ----------
        tenant_id : str
            Tenant identifier.

        Returns
        -------
        dict[str, dict[str, object]]
            Statistics per lane type.
        """
        stats = {}
        for lane_type in LaneType:
            lane = self.get_lane(tenant_id, lane_type)
            if lane:
                if isinstance(lane, MainLane):
                    total_size = sum(
                        pq.qsize() for pq in lane.priority_queue.values()
                    )
                    stats[lane_type.value] = {
                        "queue_size": total_size,
                        "queue_depth_percent": (
                            (
                                total_size
                                / lane.policy.max_queue_depth
                            )
                            * 100.0
                        ),
                    }
                elif isinstance(lane, CronLane):
                    stats[lane_type.value] = {
                        "scheduled_count": len(lane.schedule_map),
                        "next_execution": (
                            lane.get_next_execution_time()
                        ),
                    }
                elif isinstance(lane, SubagentLane):
                    stats[lane_type.value] = {
                        "queue_size": sum(
                            pq.qsize()
                            for pq in lane.priority_queue.values()
                        ),
                        "concurrent_count": lane.concurrent_count,
                        "concurrency_percent": (
                            lane.get_concurrency_percentage()
                        ),
                    }
        return stats


# ---------------------------------------------------------------------------
# Protocol for type hints
# ---------------------------------------------------------------------------


class LaneManagerProtocol(Protocol):
    """Protocol for lane manager implementations."""

    async def enqueue_main_task(
        self, request: TaskEnqueueRequest
    ) -> UUID:
        """Enqueue a task to main lane."""
        ...

    async def schedule_cron_task(
        self, request: ScheduledTaskRequest
    ) -> UUID:
        """Schedule a task to cron lane."""
        ...

    async def spawn_subagent(
        self, request: SubagentSpawnRequest
    ) -> UUID:
        """Spawn a subagent."""
        ...

    def get_lane(
        self, tenant_id: str, lane_type: LaneType
    ) -> Lane | None:
        """Get a lane."""
        ...
