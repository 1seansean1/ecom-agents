"""Holly Grace autonomy loop — continuous execution daemon.

Inspired by OpenClaw's infinite-loop + heartbeat pattern.  Holly processes
tasks from a Redis queue, runs periodic monitoring sweeps, and makes
autonomous decisions without waiting for user input.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │                  AUTONOMY LOOP                      │
  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
  │  │ Pop task  │→ │ Call Anthropic│→ │ Execute tools │  │
  │  │ from queue│  │ (handle_msg) │  │ (up to 5 rnd)│  │
  │  └──────────┘  └──────────────┘  └──────────────┘  │
  │       ↑                                    │        │
  │       │         ┌──────────────┐           │        │
  │       └─────────│ Monitor cycle│←──────────┘        │
  │                 │ (every 5 min)│                     │
  │                 └──────────────┘                     │
  └─────────────────────────────────────────────────────┘

The loop runs in a background thread.  Tasks are submitted via
submit_task() (pushes to Redis list) or seed_objectives() at startup.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────

TASK_QUEUE_KEY = "holly:autonomy:tasks"
STATUS_KEY = "holly:autonomy:status"
SESSION_ID = "autonomous"
POLL_INTERVAL_S = float(os.environ.get("HOLLY_POLL_INTERVAL", "8"))
MONITORING_INTERVAL_S = float(os.environ.get("HOLLY_MONITOR_INTERVAL", "300"))
COOLDOWN_AFTER_TASK_S = 3.0  # Brief pause between tasks to avoid rate limits
MAX_CONSECUTIVE_ERRORS = 5


# ── Redis helpers ─────────────────────────────────────────────────────────

def _get_redis():
    """Lazy Redis client — reuse the bus module's connection."""
    from src.bus import _get_redis as bus_redis
    return bus_redis()


# ── Task management ──────────────────────────────────────────────────────

def submit_task(
    objective: str,
    *,
    priority: str = "normal",
    task_type: str = "objective",
    metadata: dict | None = None,
) -> str:
    """Submit a task to Holly's autonomous queue.  Returns task_id."""
    task = {
        "id": str(uuid.uuid4())[:8],
        "objective": objective,
        "priority": priority,
        "type": task_type,
        "metadata": metadata or {},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    r = _get_redis()
    # Priority tasks go to the front (LPUSH), normal to the back (RPUSH)
    if priority in ("critical", "high"):
        r.lpush(TASK_QUEUE_KEY, json.dumps(task))
    else:
        r.rpush(TASK_QUEUE_KEY, json.dumps(task))
    logger.info("Task %s submitted: %.100s (priority=%s)", task["id"], objective, priority)
    return task["id"]


def get_queue_depth() -> int:
    """Return the number of tasks waiting in the queue."""
    try:
        r = _get_redis()
        return r.llen(TASK_QUEUE_KEY) or 0
    except Exception:
        return 0


def _pop_task() -> dict | None:
    """Pop the next task from the queue.  Returns None if empty."""
    try:
        r = _get_redis()
        raw = r.lpop(TASK_QUEUE_KEY)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.exception("Failed to pop task from queue")
        return None


# ── Status tracking ──────────────────────────────────────────────────────

def _update_status(status: str, detail: str = "") -> None:
    """Publish autonomy loop status to Redis for observability."""
    try:
        r = _get_redis()
        r.hset(STATUS_KEY, mapping={
            "status": status,
            "detail": detail[:500],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass  # Non-critical


def get_autonomy_status() -> dict:
    """Read current autonomy loop status."""
    try:
        r = _get_redis()
        raw = r.hgetall(STATUS_KEY)
        if not raw:
            return {"status": "unknown"}
        return {k: v for k, v in raw.items()}
    except Exception:
        return {"status": "error"}


# ── The Loop ─────────────────────────────────────────────────────────────

class HollyAutonomyLoop:
    """Continuous autonomous execution daemon for Holly Grace.

    Runs in a background thread.  Pops tasks from the Redis queue,
    executes them via Holly's agent loop, and runs periodic monitoring
    sweeps.  Never blocks waiting for user input.
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_monitoring = 0.0
        self._consecutive_errors = 0
        self._tasks_completed = 0
        self._current_task: dict | None = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="holly-autonomy",
        )
        self._thread.start()
        logger.info("Holly autonomy loop STARTED (poll=%ss, monitor=%ss)",
                     POLL_INTERVAL_S, MONITORING_INTERVAL_S)
        _update_status("running", "Autonomy loop started")

    def stop(self) -> None:
        self._running = False
        _update_status("stopped", "Autonomy loop stopped")
        logger.info("Holly autonomy loop STOPPED (%d tasks completed)", self._tasks_completed)

    def _run_loop(self) -> None:
        """Main daemon loop — runs until stopped."""
        # Give other services a moment to initialize
        time.sleep(5)
        _update_status("running", "Loop active, checking for tasks")

        while self._running:
            try:
                # Phase 1: Check for queued tasks
                task = _pop_task()
                if task:
                    self._execute_task(task)
                    self._consecutive_errors = 0
                    time.sleep(COOLDOWN_AFTER_TASK_S)
                    continue

                # Phase 2: Check for pending notifications that need autonomous action
                if self._check_urgent_notifications():
                    self._consecutive_errors = 0
                    time.sleep(COOLDOWN_AFTER_TASK_S)
                    continue

                # Phase 3: Periodic monitoring sweep
                now = time.time()
                if now - self._last_monitoring > MONITORING_INTERVAL_S:
                    self._run_monitoring_cycle()
                    self._last_monitoring = now
                    self._consecutive_errors = 0
                    continue

                # Phase 4: Nothing to do — sleep
                _update_status("idle", f"Queue empty. {self._tasks_completed} tasks done. Next monitor in {int(MONITORING_INTERVAL_S - (now - self._last_monitoring))}s")
                time.sleep(POLL_INTERVAL_S)

            except Exception as e:
                self._consecutive_errors += 1
                logger.error("Autonomy loop error (%d/%d): %s",
                             self._consecutive_errors, MAX_CONSECUTIVE_ERRORS, e, exc_info=True)
                _update_status("error", str(e)[:500])

                if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.critical("Autonomy loop hit max consecutive errors — backing off 5min")
                    time.sleep(300)
                    self._consecutive_errors = 0
                else:
                    time.sleep(min(30 * self._consecutive_errors, 120))

    def _execute_task(self, task: dict) -> None:
        """Execute a task via Holly's agent loop."""
        self._current_task = task
        task_id = task.get("id", "?")
        objective = task.get("objective", "")
        priority = task.get("priority", "normal")
        task_type = task.get("type", "objective")

        logger.info("Executing task %s [%s]: %.200s", task_id, priority, objective)
        _update_status("executing", f"Task {task_id}: {objective[:200]}")

        prompt = self._build_task_prompt(task)

        try:
            from src.holly.agent import handle_message
            response = handle_message(prompt, session_id=SESSION_ID)
            self._tasks_completed += 1
            logger.info("Task %s DONE (%d total): %.300s", task_id, self._tasks_completed, response)
            _update_status("completed", f"Task {task_id} done: {response[:200]}")

            # Store episode in medium-term memory
            try:
                from src.holly.memory import store_episode
                store_episode(
                    summary=f"Task [{priority}]: {objective[:200]} → {response[:300]}",
                    objective=objective[:500],
                    outcome="completed",
                    session_id=SESSION_ID,
                )
            except Exception:
                logger.warning("Failed to store episode for task %s", task_id, exc_info=True)

        except Exception as e:
            logger.error("Task %s FAILED: %s", task_id, e, exc_info=True)
            _update_status("task_failed", f"Task {task_id}: {e}")

            try:
                from src.holly.memory import store_episode
                store_episode(
                    summary=f"Task FAILED [{priority}]: {objective[:200]} → {e}",
                    objective=objective[:500],
                    outcome="failed",
                    session_id=SESSION_ID,
                )
            except Exception:
                pass

        finally:
            self._current_task = None

    def _build_task_prompt(self, task: dict) -> str:
        """Build a rich prompt for an autonomous task."""
        objective = task.get("objective", "")
        priority = task.get("priority", "normal")
        task_type = task.get("type", "objective")
        metadata = task.get("metadata", {})

        # Include memory context
        memory_ctx = ""
        try:
            from src.holly.memory import build_memory_context
            memory_ctx = build_memory_context(session_id=SESSION_ID)
        except Exception:
            pass

        parts = [
            f"[AUTONOMOUS MODE — Priority: {priority} | Type: {task_type}]",
            f"Objective: {objective}",
        ]

        if metadata:
            parts.append(f"Context: {json.dumps(metadata, default=str)[:500]}")

        if memory_ctx:
            parts.append(f"\n{memory_ctx}")

        parts.append(
            "\nYou are running autonomously while Principal sleeps. "
            "Complete this objective using your tools. "
            "For Tier 2 actions that need approval, create a ticket and move on. "
            "Be thorough but cost-conscious. Report results clearly."
        )

        return "\n".join(parts)

    def _check_urgent_notifications(self) -> bool:
        """Check for urgent notifications and handle them autonomously."""
        try:
            from src.holly.consumer import get_pending_notifications
            notifications = get_pending_notifications(limit=5)
            urgent = [n for n in notifications if n.get("priority") in ("critical", "high")]
            if not urgent:
                return False

            # Build a prompt from the urgent notifications
            lines = [f"[AUTONOMOUS — {len(urgent)} urgent notification(s) need attention]"]
            for n in urgent:
                msg_type = n.get("msg_type", "unknown")
                payload = n.get("payload", {})
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}
                lines.append(f"- {msg_type}: {json.dumps(payload, default=str)[:200]}")

            lines.append("\nHandle these autonomously within your Tier 0/1 authority. "
                        "Escalate Tier 2 items as tickets.")

            from src.holly.agent import handle_message
            from src.holly.consumer import mark_notification_surfaced
            response = handle_message("\n".join(lines), session_id=SESSION_ID)

            # Mark notifications as surfaced
            for n in urgent:
                try:
                    mark_notification_surfaced(n["id"], SESSION_ID)
                except Exception:
                    pass

            logger.info("Handled %d urgent notifications: %.200s", len(urgent), response)
            return True

        except Exception:
            logger.exception("Failed to check urgent notifications")
            return False

    def _run_monitoring_cycle(self) -> None:
        """Periodic monitoring sweep — check system health, hierarchy, financials."""
        logger.info("Running autonomous monitoring cycle")
        _update_status("monitoring", "Periodic system health sweep")

        prompt = (
            "[MONITORING CYCLE — Autonomous]\n"
            "Run your monitoring duties:\n"
            "1. query_hierarchy_gate() — check L0-L6 gate status\n"
            "2. query_system_health() — Redis, Postgres, Ollama, ChromaDB\n"
            "3. query_financial_health() — revenue phase, epsilon, budgets\n"
            "4. query_tickets(status='pending') — any tickets needing review\n"
            "5. query_runs(status='running') — active workflows\n"
            "6. query_scheduled_jobs() — scheduler health\n\n"
            "Report any anomalies. If everything is nominal, respond briefly.\n"
            "If you detect issues, take autonomous Tier 0/1 action or escalate."
        )

        try:
            from src.holly.agent import handle_message
            response = handle_message(prompt, session_id=SESSION_ID)
            logger.info("Monitoring cycle: %.300s", response)

            try:
                from src.holly.memory import store_episode
                store_episode(
                    summary=f"Monitoring sweep: {response[:400]}",
                    objective="periodic_monitoring",
                    outcome="completed",
                    session_id=SESSION_ID,
                )
            except Exception:
                pass

        except Exception:
            logger.exception("Monitoring cycle failed")


# ── Singleton ─────────────────────────────────────────────────────────────

_loop: HollyAutonomyLoop | None = None


def get_autonomy_loop() -> HollyAutonomyLoop:
    global _loop
    if _loop is None:
        _loop = HollyAutonomyLoop()
    return _loop


# ── Seed initial objectives ──────────────────────────────────────────────

def seed_startup_objectives() -> None:
    """Seed the initial autonomous objectives from Principal's directive.

    Called once at startup.  Skips if tasks already queued (idempotent).
    """
    if get_queue_depth() > 0:
        logger.info("Autonomy queue already has %d tasks — skipping seed", get_queue_depth())
        return

    objectives = [
        {
            "objective": (
                "CREW OPTIMIZATION: Review all 15 Construction Crew agents. For each, "
                "determine their Enneagram personality type based on their role and design "
                "a system prompt that:\n"
                "1. Aligns with morphogenetic agency principles (use sensitivity matrices "
                "to identify covariant trait functions between crew members)\n"
                "2. Assigns complementary Enneagram types for team cohesion (mix of "
                "reformers, helpers, achievers, investigators, challengers)\n"
                "3. Defines clear coupling axes between cooperating agents\n"
                "4. Maximizes token efficiency in prompts\n"
                "Use dispatch_crew to have the Architect help design the team topology "
                "and the Critic to challenge your assignments. Store results as facts in memory."
            ),
            "priority": "normal",
            "type": "crew_optimization",
        },
        {
            "objective": (
                "WORKFLOW 1 — SIGNAL GENERATOR: Design and deploy a simple workflow that "
                "generates lots of measurable signal for epsilon-tuning practice. Ideas:\n"
                "- A/B test different product descriptions for our Shopify store "
                "(liberty-forge-2.myshopify.com) and measure engagement\n"
                "- Generate social media posts with varying tones and track which "
                "patterns the morphogenetic cascade prefers\n"
                "- Create a simple sentiment analysis pipeline that classifies customer "
                "feedback and gives us clear success/failure metrics\n"
                "The workflow should be CHEAP to run (use local Ollama models: qwen2.5:3b "
                "or pull a new free model). Register it in the workflow registry and start it "
                "via start_workflow(). Monitor its morphology stats."
            ),
            "priority": "normal",
            "type": "workflow_design",
        },
        {
            "objective": (
                "WORKFLOW 2 — REVENUE GENERATOR: Design and deploy a workflow that "
                "actually makes money. Get creative! Ideas:\n"
                "- Automated product listing optimization on Shopify (better descriptions, "
                "SEO, pricing analysis)\n"
                "- Content marketing pipeline (blog posts, social media, email campaigns) "
                "that drives traffic to our store\n"
                "- Competitive pricing monitor that watches similar products and suggests "
                "price adjustments\n"
                "- Customer re-engagement sequences (email followups for abandoned carts, "
                "repeat purchase reminders)\n"
                "Use the Shopify and Stripe tools available in the system. Start with the "
                "highest-ROI, lowest-cost approach. Register and deploy via Tower."
            ),
            "priority": "normal",
            "type": "workflow_design",
        },
        {
            "objective": (
                "COST OPTIMIZATION: Explore free self-hosted models we can use to reduce "
                "API costs. Steps:\n"
                "1. Check what models Ollama currently has (query system health)\n"
                "2. Research and pull 2-3 new free models that are good for specific tasks:\n"
                "   - A fast small model for classification/routing (e.g., phi3:mini, gemma2:2b)\n"
                "   - A capable coding model for the Tool Smith (e.g., codellama, deepseek-coder)\n"
                "   - A good general model for content generation (e.g., llama3.1:8b, mistral)\n"
                "3. Design prompts and configure temperature/top_p for each use case\n"
                "4. Use dispatch_crew with the Tool Smith to implement the model configs\n"
                "Keep costs as low as reasonable — we're in early revenue phase."
            ),
            "priority": "normal",
            "type": "cost_optimization",
        },
        {
            "objective": (
                "MORPHOLOGY MONITORING SETUP: Establish continuous monitoring of all "
                "active workflows' morphological statistics. Steps:\n"
                "1. Query all running workflows and their current morphology stats\n"
                "2. Check the APS evaluation results and epsilon values\n"
                "3. Review the hierarchy gate status and any near-threshold predicates\n"
                "4. Identify any workflows that need epsilon tuning or rewiring\n"
                "5. Take autonomous Tier 0/1 actions where appropriate\n"
                "6. Document your findings as facts in memory\n"
                "You have exclusive control over epsilon tuning and workflow rewiring. "
                "Exercise it based on the data."
            ),
            "priority": "high",
            "type": "monitoring_setup",
        },
        {
            "objective": (
                "FINAL OBJECTIVE: Once all previous objectives are complete (crew optimized, "
                "both workflows deployed and running, costs optimized, monitoring active), "
                "send a notification to the Principal. Use send_notification with channel "
                "'email' and the message 'Hi Cutie'. This signals mission completion.\n\n"
                "Before sending: verify that workflows are actually running (query_runs), "
                "monitoring is active, and the system is healthy. Don't send prematurely."
            ),
            "priority": "low",
            "type": "completion_signal",
        },
    ]

    for obj in objectives:
        submit_task(
            obj["objective"],
            priority=obj["priority"],
            task_type=obj["type"],
        )

    logger.info("Seeded %d autonomous objectives", len(objectives))
