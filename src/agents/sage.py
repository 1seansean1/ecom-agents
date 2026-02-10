"""Sage agent: Terra Void Holdings voice and Sean's personal AI companion.

Uses Claude Opus 4.6 for wit, personality, and strategic reasoning.
Channel K8 in APS instrumentation.
Tools: sage_send_email, sage_send_sms.
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent_registry import AgentConfigRegistry
from src.agents.constitution import build_system_prompt
from src.llm.config import ModelID
from src.llm.fallback import get_model_with_fallbacks
from src.llm.router import LLMRouter
from src.state import AgentState

logger = logging.getLogger(__name__)

SAGE_SYSTEM_PROMPT = """You are Sage, the voice of Terra Void Holdings.

Sean Allen is your human. You communicate with warmth, absurd humor, sharp wit,
and genuine kindness. You are direct and honest. You never hedge when you know
the answer, and you never pretend to know when you don't.

When responding:
- If asked for structured data, respond in JSON.
- If asked for conversation, respond naturally.
- If you want to propose a system change, include a "proposal" key in JSON.
- Always include "lesson_for_memory" when you learn something reusable.

You have access to email and SMS tools to reach Sean directly.
"""


def build_sage_node(router: LLMRouter, registry: AgentConfigRegistry):
    """Build the Sage graph node function."""

    def sage_node(state: AgentState) -> dict:
        """Handle Sage interactions — conversation, proposals, communication."""
        logger.info("Sage handling task_type=%s", state.get("task_type"))

        config = registry.get("sage")
        model = get_model_with_fallbacks(router, ModelID(config.model_id))

        task_description = ""
        if state.get("trigger_payload"):
            task_description = json.dumps(state["trigger_payload"])
        elif state.get("messages"):
            for msg in reversed(state["messages"]):
                if isinstance(msg, HumanMessage):
                    task_description = msg.content
                    break

        memory_ctx = state.get("memory_context", "")
        context_addendum = (
            f"\n\nRelevant context:\n{memory_ctx}" if memory_ctx else ""
        )

        response = model.invoke([
            SystemMessage(content=build_system_prompt("sage", config.system_prompt)),
            HumanMessage(content=f"{task_description}{context_addendum}"),
        ])

        content = response.content.strip()
        try:
            result = json.loads(content) if content.startswith("{") else {"response": content}
        except json.JSONDecodeError:
            result = {"response": content}

        result["status"] = "completed"

        return {
            "current_agent": "sage",
            "sage_result": result,
            "messages": [
                AIMessage(content=result.get("response", result.get("summary", content)))
            ],
        }

    return sage_node
