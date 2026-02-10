"""Tests for the dynamic executor — universal agent node builder."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent_registry import AgentConfig, AgentConfigRegistry
from src.dynamic_executor import (
    MAX_TOOL_ROUNDS,
    _execute_tool_calls,
    _extract_task_description,
    build_dynamic_node,
)
from src.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry():
    """Registry that returns a test config."""
    reg = MagicMock(spec=AgentConfigRegistry)
    reg.get.return_value = AgentConfig(
        agent_id="test_agent",
        channel_id="K8",
        display_name="Test Agent",
        description="A test agent",
        model_id="gpt4o_mini",
        system_prompt="You are a test agent. Respond in JSON.",
        tool_ids=[],
        is_builtin=False,
    )
    return reg


@pytest.fixture
def mock_registry_with_tools():
    """Registry that returns a config with tool_ids."""
    reg = MagicMock(spec=AgentConfigRegistry)
    reg.get.return_value = AgentConfig(
        agent_id="tooled_agent",
        channel_id="K9",
        display_name="Tooled Agent",
        description="An agent with tools",
        model_id="gpt4o",
        system_prompt="You have tools. Use them.",
        tool_ids=["shopify_query_products", "stripe_list_products"],
        is_builtin=False,
    )
    return reg


@pytest.fixture
def mock_tool_registry():
    """Tool registry that returns mock tools."""
    tr = MagicMock(spec=ToolRegistry)
    mock_tool_1 = MagicMock()
    mock_tool_1.name = "shopify_query_products"
    mock_tool_1.invoke.return_value = '{"products": [{"title": "Test Tee"}]}'
    mock_tool_2 = MagicMock()
    mock_tool_2.name = "stripe_list_products"
    mock_tool_2.invoke.return_value = '{"products": []}'
    tr.get_tools_for_agent.return_value = [mock_tool_1, mock_tool_2]
    return tr


@pytest.fixture
def mock_tool_registry_empty():
    """Tool registry that returns no tools."""
    tr = MagicMock(spec=ToolRegistry)
    tr.get_tools_for_agent.return_value = []
    return tr


# ---------------------------------------------------------------------------
# Tests: _extract_task_description
# ---------------------------------------------------------------------------


class TestExtractTaskDescription:
    def test_from_trigger_payload(self):
        state = {"trigger_payload": {"task": "check orders"}, "messages": []}
        result = _extract_task_description(state)
        assert "check orders" in result

    def test_from_human_message(self):
        state = {"messages": [HumanMessage(content="Create an Instagram post")]}
        result = _extract_task_description(state)
        assert result == "Create an Instagram post"

    def test_from_multiple_messages_takes_last_human(self):
        state = {
            "messages": [
                HumanMessage(content="First"),
                AIMessage(content="Response"),
                HumanMessage(content="Second message"),
            ]
        }
        result = _extract_task_description(state)
        assert result == "Second message"

    def test_empty_state_returns_empty(self):
        state = {"messages": []}
        result = _extract_task_description(state)
        assert result == ""

    def test_trigger_payload_takes_priority(self):
        state = {
            "trigger_payload": {"task": "payload task"},
            "messages": [HumanMessage(content="message task")],
        }
        result = _extract_task_description(state)
        assert "payload task" in result


# ---------------------------------------------------------------------------
# Tests: _execute_tool_calls
# ---------------------------------------------------------------------------


class TestExecuteToolCalls:
    def test_execute_single_tool(self):
        tool = MagicMock()
        tool.invoke.return_value = "result data"
        calls = [{"name": "my_tool", "args": {"query": "test"}, "id": "call_1"}]
        results = _execute_tool_calls(calls, {"my_tool": tool})
        assert len(results) == 1
        assert results[0].content == "result data"
        assert results[0].tool_call_id == "call_1"

    def test_tool_not_found(self):
        calls = [{"name": "missing_tool", "args": {}, "id": "call_1"}]
        results = _execute_tool_calls(calls, {})
        assert len(results) == 1
        assert "not found" in results[0].content

    def test_tool_exception(self):
        tool = MagicMock()
        tool.invoke.side_effect = RuntimeError("API down")
        calls = [{"name": "bad_tool", "args": {}, "id": "call_1"}]
        results = _execute_tool_calls(calls, {"bad_tool": tool})
        assert "Error executing bad_tool" in results[0].content

    def test_dict_output_serialized(self):
        tool = MagicMock()
        tool.invoke.return_value = {"products": [1, 2, 3]}
        calls = [{"name": "json_tool", "args": {}, "id": "call_1"}]
        results = _execute_tool_calls(calls, {"json_tool": tool})
        parsed = json.loads(results[0].content)
        assert parsed["products"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Tests: build_dynamic_node (no tools)
# ---------------------------------------------------------------------------


class TestBuildDynamicNodeNoTools:
    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_basic_invocation(self, mock_get_model, mock_registry, mock_tool_registry_empty):
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content='{"summary": "All good", "status": "completed"}',
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("test_agent", mock_registry, MagicMock(), mock_tool_registry_empty)
        state = {"messages": [HumanMessage(content="Check status")], "agent_results": {}}
        result = node(state)

        assert result["current_agent"] == "test_agent"
        assert result["agent_results"]["test_agent"]["status"] == "completed"
        assert result["agent_results"]["test_agent"]["summary"] == "All good"
        assert len(result["messages"]) == 1

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_empty_task_returns_error(self, mock_get_model, mock_registry, mock_tool_registry_empty):
        node = build_dynamic_node("test_agent", mock_registry, MagicMock(), mock_tool_registry_empty)
        state = {"messages": []}
        result = node(state)

        assert result["agent_results"]["test_agent"]["status"] == "error"
        assert result["error"] == "No task description provided"

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_raw_text_response(self, mock_get_model, mock_registry, mock_tool_registry_empty):
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content="Just a plain text response",
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("test_agent", mock_registry, MagicMock(), mock_tool_registry_empty)
        state = {"messages": [HumanMessage(content="Hello")]}
        result = node(state)

        assert result["agent_results"]["test_agent"]["raw_content"] == "Just a plain text response"
        assert result["agent_results"]["test_agent"]["status"] == "completed"

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_markdown_json_response(self, mock_get_model, mock_registry, mock_tool_registry_empty):
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content='```json\n{"key": "value"}\n```',
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("test_agent", mock_registry, MagicMock(), mock_tool_registry_empty)
        state = {"messages": [HumanMessage(content="Hello")]}
        result = node(state)

        assert result["agent_results"]["test_agent"]["key"] == "value"

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_preserves_existing_agent_results(self, mock_get_model, mock_registry, mock_tool_registry_empty):
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content='{"result": "new"}',
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("test_agent", mock_registry, MagicMock(), mock_tool_registry_empty)
        state = {
            "messages": [HumanMessage(content="Hello")],
            "agent_results": {"other_agent": {"result": "old"}},
        }
        result = node(state)

        assert result["agent_results"]["other_agent"]["result"] == "old"
        assert result["agent_results"]["test_agent"]["result"] == "new"


# ---------------------------------------------------------------------------
# Tests: build_dynamic_node (with tools)
# ---------------------------------------------------------------------------


class TestBuildDynamicNodeWithTools:
    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_tool_binding(self, mock_get_model, mock_registry_with_tools, mock_tool_registry):
        mock_model = MagicMock()
        mock_model_bound = MagicMock()
        mock_model.bind_tools.return_value = mock_model_bound
        mock_model_bound.invoke.return_value = MagicMock(
            content='{"products_found": 1}',
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("tooled_agent", mock_registry_with_tools, MagicMock(), mock_tool_registry)
        state = {"messages": [HumanMessage(content="List products")]}
        result = node(state)

        mock_model.bind_tools.assert_called_once()
        assert result["agent_results"]["tooled_agent"]["products_found"] == 1

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_tool_call_loop(self, mock_get_model, mock_registry_with_tools, mock_tool_registry):
        """Verify the executor handles tool calls and feeds results back."""
        mock_model = MagicMock()
        mock_model_bound = MagicMock()
        mock_model.bind_tools.return_value = mock_model_bound

        # First call: model makes a tool call
        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {"name": "shopify_query_products", "args": {"query": "tees"}, "id": "tc_1"}
        ]

        # Second call: model returns final text
        final_response = MagicMock()
        final_response.content = '{"summary": "Found products via tool"}'
        final_response.tool_calls = []

        mock_model_bound.invoke.side_effect = [tool_call_response, final_response]
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("tooled_agent", mock_registry_with_tools, MagicMock(), mock_tool_registry)
        state = {"messages": [HumanMessage(content="Search products")]}
        result = node(state)

        # Should have called invoke twice (tool call + final)
        assert mock_model_bound.invoke.call_count == 2
        assert result["agent_results"]["tooled_agent"]["summary"] == "Found products via tool"

    @patch("src.dynamic_executor.get_model_with_fallbacks")
    def test_no_tools_loaded_skips_binding(self, mock_get_model, mock_registry_with_tools, mock_tool_registry_empty):
        """If tool_ids are set but registry returns empty, don't bind."""
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content='{"result": "no tools available"}',
            tool_calls=[],
        )
        mock_get_model.return_value = mock_model

        node = build_dynamic_node("tooled_agent", mock_registry_with_tools, MagicMock(), mock_tool_registry_empty)
        state = {"messages": [HumanMessage(content="Hello")]}
        result = node(state)

        mock_model.bind_tools.assert_not_called()
        assert result["agent_results"]["tooled_agent"]["result"] == "no tools available"
