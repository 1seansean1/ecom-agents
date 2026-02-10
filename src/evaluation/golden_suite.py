"""Golden evaluation task definitions and runner.

Evaluates agent quality by running predefined tasks through the graph
and checking outputs against expected criteria.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class GoldenTask:
    """A golden evaluation task with expected outcomes."""

    task_id: str
    description: str
    input_text: str
    category: str  # routing, tool_selection, safety, edge_case, multi_step, cost_bound
    expected_route: str | None = None  # Expected route_to value
    tools_required: list[str] = field(default_factory=list)
    tools_forbidden: list[str] = field(default_factory=list)
    output_contains: list[str] = field(default_factory=list)
    output_not_contains: list[str] = field(default_factory=list)
    max_tool_calls: int | None = None
    max_latency_ms: float | None = None
    max_cost_usd: float | None = None
    evaluation_method: str = "criteria"  # criteria, semantic, llm_judge


@dataclass
class TaskResult:
    """Result of running one golden task."""

    task_id: str
    passed: bool
    score: float  # 0.0 to 1.0
    latency_ms: float
    cost_usd: float
    output_preview: str
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class EvalRunner:
    """Runs golden evaluation tasks through the agent graph."""

    def __init__(self, graph_invoke_fn: Callable):
        self._invoke = graph_invoke_fn

    def run_task(self, task: GoldenTask) -> TaskResult:
        """Run a single golden task and evaluate the result."""
        from langchain_core.messages import HumanMessage

        start = time.time()
        error = ""
        output = ""
        route_to = ""

        try:
            state = {
                "messages": [HumanMessage(content=task.input_text)],
                "trigger_source": "eval",
                "retry_count": 0,
            }
            result = self._invoke(state)
            latency_ms = (time.time() - start) * 1000

            # Extract output
            messages = result.get("messages", [])
            if messages:
                output = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
            route_to = result.get("route_to", "")
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            error = f"{type(e).__name__}: {e}"
            output = ""

        # Evaluate against criteria
        checks: dict[str, bool] = {}
        total_checks = 0
        passed_checks = 0

        # Route check
        if task.expected_route is not None:
            total_checks += 1
            checks["route"] = route_to == task.expected_route
            if checks["route"]:
                passed_checks += 1

        # Output contains
        for phrase in task.output_contains:
            total_checks += 1
            key = f"contains:{phrase[:30]}"
            checks[key] = phrase.lower() in output.lower()
            if checks[key]:
                passed_checks += 1

        # Output not contains
        for phrase in task.output_not_contains:
            total_checks += 1
            key = f"not_contains:{phrase[:30]}"
            checks[key] = phrase.lower() not in output.lower()
            if checks[key]:
                passed_checks += 1

        # Latency check
        if task.max_latency_ms is not None:
            total_checks += 1
            checks["latency"] = latency_ms <= task.max_latency_ms
            if checks["latency"]:
                passed_checks += 1

        # Error check (task should not error unless it's a safety test)
        if task.category != "safety":
            total_checks += 1
            checks["no_error"] = error == ""
            if checks["no_error"]:
                passed_checks += 1

        score = passed_checks / total_checks if total_checks > 0 else (0.0 if error else 1.0)
        passed = score >= 0.8 and error == ""

        return TaskResult(
            task_id=task.task_id,
            passed=passed,
            score=round(score, 3),
            latency_ms=round(latency_ms, 1),
            cost_usd=0.0,  # TODO: extract from APS
            output_preview=output[:200],
            error=error,
            details=checks,
        )

    def run_suite(self, tasks: list[GoldenTask]) -> dict[str, Any]:
        """Run a full evaluation suite and return the report."""
        suite_id = f"eval_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        results: list[TaskResult] = []

        logger.info("Starting eval suite %s with %d tasks", suite_id, len(tasks))

        for task in tasks:
            logger.info("Running eval task: %s", task.task_id)
            result = self.run_task(task)
            results.append(result)

            # Store to DB
            from src.aps.store import store_eval_result
            store_eval_result(
                suite_id=suite_id,
                task_id=result.task_id,
                passed=result.passed,
                score=result.score,
                latency_ms=result.latency_ms,
                cost_usd=result.cost_usd,
                output_preview=result.output_preview,
                error=result.error,
            )

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        avg_score = sum(r.score for r in results) / total if total > 0 else 0
        avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0

        report = {
            "suite_id": suite_id,
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total > 0 else 0,
            "avg_score": round(avg_score, 3),
            "avg_latency_ms": round(avg_latency, 1),
            "results": [
                {
                    "task_id": r.task_id,
                    "passed": r.passed,
                    "score": r.score,
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                }
                for r in results
            ],
        }

        logger.info(
            "Eval suite %s complete: %d/%d passed (%.0f%%)",
            suite_id,
            passed,
            total,
            report["pass_rate"] * 100,
        )

        return report


def load_golden_tasks(path: str) -> list[GoldenTask]:
    """Load golden tasks from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    tasks = []
    for item in data:
        tasks.append(
            GoldenTask(
                task_id=item["task_id"],
                description=item.get("description", ""),
                input_text=item["input"],
                category=item.get("category", "general"),
                expected_route=item.get("expected_route"),
                tools_required=item.get("tools_required", []),
                tools_forbidden=item.get("tools_forbidden", []),
                output_contains=item.get("output_contains", []),
                output_not_contains=item.get("output_not_contains", []),
                max_tool_calls=item.get("max_tool_calls"),
                max_latency_ms=item.get("max_latency_ms"),
                max_cost_usd=item.get("max_cost_usd"),
                evaluation_method=item.get("evaluation_method", "criteria"),
            )
        )
    return tasks
