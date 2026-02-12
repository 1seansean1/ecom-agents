"""Integration tests for IM pipeline tools (src/im/tools.py).

Tests the tool functions with mocked database (store) and LLM calls.
Verifies pipeline dependency chain, error handling, and data flow.

Note: Tools use lazy imports (from src.im.store import ...) inside function
bodies, so we must patch at the SOURCE module (src.im.store.*), not at
src.im.tools.*.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.im.models import IMWorkspace


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_workspace(**overrides) -> IMWorkspace:
    """Factory for test workspaces at various pipeline stages."""
    defaults = {
        "workspace_id": "ws-test-001",
        "created_at": datetime(2026, 2, 11, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 11, tzinfo=timezone.utc),
        "version": 1,
        "stage": "created",
        "raw_intent": "Build a customer support chatbot",
        "goal_tuple": {},
        "predicates": [],
        "predicate_blocks": [],
        "cross_block_coupling": [],
        "coupling_matrix": {},
        "codimension": {},
        "rank_budget": {},
        "memory": {},
        "assignment": {},
        "workflow": {},
        "feasibility": {},
        "created_by": "holly_grace",
        "metadata": {},
    }
    defaults.update(overrides)
    return IMWorkspace(**defaults)


SAMPLE_G1 = [{
    "failure_predicates": [
        "Chatbot fails to respond within 5s",
        "Chatbot gives incorrect answer",
        "Chatbot leaks PII",
    ],
    "epsilon_g": 0.05,
    "horizon_t": 3600,
    "measurement_map": "Automated test suite + human review",
}]

SAMPLE_PREDICATES = [
    {"id": "f_001", "name": "response_timeout", "severity": "high", "block_id": "BLK_A",
     "epsilon_g": 0.05, "horizon_t": 3600, "description": "Bot fails to respond in time",
     "measurement_map": "Latency probe", "quality_assessment": "Falsifiable, Observable, Actionable"},
    {"id": "f_002", "name": "incorrect_answer", "severity": "critical", "block_id": "BLK_A",
     "epsilon_g": 0.01, "horizon_t": 300, "description": "Bot gives wrong info",
     "measurement_map": "Accuracy test", "quality_assessment": "Falsifiable, Observable"},
    {"id": "f_003", "name": "pii_leak", "severity": "critical", "block_id": "BLK_B",
     "epsilon_g": 0.001, "horizon_t": 86400, "description": "Bot leaks PII",
     "measurement_map": "PII scanner", "quality_assessment": "Falsifiable, Observable, Actionable"},
]

SAMPLE_BLOCKS = [
    {"id": "BLK_A", "name": "Response Quality", "predicate_ids": ["f_001", "f_002"], "intra_rank": 2},
    {"id": "BLK_B", "name": "Security", "predicate_ids": ["f_003"], "intra_rank": 1},
]

SAMPLE_CROSS_COUPLING = [
    {"from_block": "BLK_A", "to_block": "BLK_B", "rho": 0.2, "mechanism": "response quality affects security"},
]

# Common store patches — patch at the SOURCE module
STORE = "src.im.store"


# ---------------------------------------------------------------------------
# Tool 1: Parse Goal Tuple
# ---------------------------------------------------------------------------

class TestParseGoalTuple:
    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{STORE}.create_workspace", return_value="ws-new-001")
    @patch("src.im.tools._llm_parse_goal", return_value=SAMPLE_G1)
    def test_creates_workspace_and_parses(self, mock_llm, mock_create, mock_get, mock_update, mock_audit):
        from src.im.tools import im_parse_goal_tuple
        mock_get.return_value = _make_workspace(workspace_id="ws-new-001")

        result = im_parse_goal_tuple("Build a customer support chatbot")

        assert result["workspace_id"] == "ws-new-001"
        assert result["stage"] == "goal_parsed"
        assert len(result["goal_tuple"]["g1_candidates"]) == 1
        mock_create.assert_called_once()
        mock_update.assert_called_once()
        mock_audit.assert_called_once()

    @patch(f"{STORE}.get_workspace", return_value=None)
    @patch(f"{STORE}.create_workspace", return_value="ws-fail")
    def test_returns_error_when_workspace_creation_fails(self, mock_create, mock_get):
        from src.im.tools import im_parse_goal_tuple
        result = im_parse_goal_tuple("test")
        assert "error" in result

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{STORE}.create_workspace", return_value="ws-multi")
    @patch("src.im.tools._llm_parse_goal")
    def test_multiple_g1_candidates_detected(self, mock_llm, mock_create, mock_get, mock_update, mock_audit):
        from src.im.tools import im_parse_goal_tuple
        mock_llm.return_value = [SAMPLE_G1[0], {**SAMPLE_G1[0], "epsilon_g": 0.1}]
        mock_get.return_value = _make_workspace(workspace_id="ws-multi")

        result = im_parse_goal_tuple("Build a chatbot", context="ecommerce domain")

        assert result["goal_tuple"]["selected_g1_index"] is None  # ambiguous

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{STORE}.create_workspace", return_value="ws-single")
    @patch("src.im.tools._llm_parse_goal")
    def test_single_g1_auto_selected(self, mock_llm, mock_create, mock_get, mock_update, mock_audit):
        from src.im.tools import im_parse_goal_tuple
        mock_llm.return_value = [SAMPLE_G1[0]]
        mock_get.return_value = _make_workspace(workspace_id="ws-single")

        result = im_parse_goal_tuple("Simple goal")

        assert result["goal_tuple"]["selected_g1_index"] == 0


# ---------------------------------------------------------------------------
# Tool 2: Generate Failure Predicates
# ---------------------------------------------------------------------------

class TestGenerateFailurePredicates:
    def _ws_with_goal(self):
        return _make_workspace(
            stage="goal_parsed",
            goal_tuple={"g0_preference": "Build chatbot", "g1_candidates": SAMPLE_G1, "selected_g1_index": 0},
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch("src.im.tools._llm_generate_predicates")
    def test_generates_predicates(self, mock_llm, mock_get, mock_update, mock_audit):
        from src.im.tools import im_generate_failure_predicates
        mock_get.return_value = self._ws_with_goal()
        mock_llm.return_value = {
            "predicates": SAMPLE_PREDICATES,
            "blocks": SAMPLE_BLOCKS,
            "cross_coupling": SAMPLE_CROSS_COUPLING,
        }

        result = im_generate_failure_predicates("ws-test-001")

        assert len(result["predicates"]) == 3
        assert len(result["predicate_blocks"]) == 2
        assert "quality_summary" in result

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_missing_workspace(self, mock_get):
        from src.im.tools import im_generate_failure_predicates
        result = im_generate_failure_predicates("ws-nonexistent")
        assert "error" in result

    @patch(f"{STORE}.get_workspace")
    def test_g1_index_out_of_range(self, mock_get):
        from src.im.tools import im_generate_failure_predicates
        mock_get.return_value = self._ws_with_goal()
        result = im_generate_failure_predicates("ws-test-001", g1_index=5)
        assert "error" in result
        assert "out of range" in result["error"]


# ---------------------------------------------------------------------------
# Tool 3: Build Coupling Model
# ---------------------------------------------------------------------------

class TestBuildCouplingModel:
    def _ws_with_predicates(self):
        return _make_workspace(
            stage="predicates_generated",
            predicates=SAMPLE_PREDICATES,
            predicate_blocks=SAMPLE_BLOCKS,
            cross_block_coupling=SAMPLE_CROSS_COUPLING,
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_generate_mode(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_build_coupling_model
        mock_get.return_value = self._ws_with_predicates()

        result = im_build_coupling_model("ws-test-001", mode="generate")

        assert "coupling_matrix" in result
        assert result["coupling_matrix"]["dimensions"] == "3×3"

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_generate_with_lock(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_build_coupling_model
        mock_get.return_value = self._ws_with_predicates()

        result = im_build_coupling_model("ws-test-001", mode="generate", lock=True)

        assert result["coupling_matrix"]["locked"] is True

    @patch(f"{STORE}.get_workspace")
    def test_update_locked_matrix_rejected(self, mock_get):
        from src.im.tools import im_build_coupling_model
        ws = self._ws_with_predicates()
        ws.coupling_matrix = {"M": [[1, 0], [0, 1]], "locked": True, "human_overrides": []}
        mock_get.return_value = ws

        result = im_build_coupling_model("ws-test-001", mode="update",
                                          overrides=[{"row": 0, "col": 1, "value": 0.5}])
        assert "error" in result
        assert "locked" in result["error"]

    @patch(f"{STORE}.get_workspace")
    def test_invalid_mode(self, mock_get):
        from src.im.tools import im_build_coupling_model
        mock_get.return_value = self._ws_with_predicates()

        result = im_build_coupling_model("ws-test-001", mode="invalid")
        assert "error" in result
        assert "Unknown mode" in result["error"]

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_missing_workspace(self, mock_get):
        from src.im.tools import im_build_coupling_model
        result = im_build_coupling_model("ws-nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool 4: Estimate Codimension
# ---------------------------------------------------------------------------

class TestEstimateCodimension:
    def _ws_with_coupling(self):
        M = [[1.0, 0.3, 0.1], [0.3, 1.0, 0.2], [0.1, 0.2, 1.0]]
        return _make_workspace(
            stage="coupling_built",
            predicates=SAMPLE_PREDICATES,
            predicate_blocks=SAMPLE_BLOCKS,
            coupling_matrix={"M": M, "locked": True, "human_overrides": []},
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_computes_codimension(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_estimate_codimension
        mock_get.return_value = self._ws_with_coupling()

        result = im_estimate_codimension("ws-test-001", tau=0.05)

        assert "codimension" in result
        cod = result["codimension"]
        assert "cod_pi_g" in cod
        assert "eigenspectrum" in cod
        assert cod["cod_pi_g"] >= 1

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_k_preloaded_reduces_codimension(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_estimate_codimension
        mock_get.return_value = self._ws_with_coupling()

        result = im_estimate_codimension(
            "ws-test-001", tau=0.05,
            k_preloaded=[{"name": "cached_auth", "resolves": ["f_001"], "cod_reduction": 1}],
        )

        cod = result["codimension"]
        assert cod["cod_pi_g_given_k0"] is not None
        assert cod["cod_pi_g_given_k0"] <= cod["cod_pi_g"]

    @patch(f"{STORE}.get_workspace")
    def test_no_coupling_matrix(self, mock_get):
        from src.im.tools import im_estimate_codimension
        mock_get.return_value = _make_workspace(coupling_matrix={})

        result = im_estimate_codimension("ws-test-001")
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool 5: Rank Budget and Regime
# ---------------------------------------------------------------------------

class TestRankBudgetAndRegime:
    def _ws_with_codimension(self, cod=3):
        return _make_workspace(
            stage="codimension_estimated",
            predicates=SAMPLE_PREDICATES,
            cross_block_coupling=SAMPLE_CROSS_COUPLING,
            codimension={"cod_pi_g": cod, "eigenspectrum": [0.8, 0.5, 0.2]},
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_computes_rank_budget(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_rank_budget_and_regime
        mock_get.return_value = self._ws_with_codimension()

        result = im_rank_budget_and_regime("ws-test-001")

        rb = result["rank_budget"]
        assert "regime" in rb
        assert rb["regime"] in ("simple", "medium", "complex")

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_custom_agent_pool(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_rank_budget_and_regime
        mock_get.return_value = self._ws_with_codimension()

        custom_agents = [
            {"agent_id": "a1", "model_family": "GPT-4o", "jacobian_rank": 4,
             "steering_spectrum": [1, 0.8, 0.6, 0.4]},
        ]
        result = im_rank_budget_and_regime("ws-test-001", agent_pool=custom_agents)

        assert "rank_budget" in result

    @patch(f"{STORE}.get_workspace")
    def test_no_codimension(self, mock_get):
        from src.im.tools import im_rank_budget_and_regime
        mock_get.return_value = _make_workspace(codimension={})

        result = im_rank_budget_and_regime("ws-test-001")
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool 6: Memory Tier Design
# ---------------------------------------------------------------------------

class TestMemoryTierDesign:
    def _ws_with_rank_budget(self):
        return _make_workspace(
            stage="rank_budgeted",
            predicates=SAMPLE_PREDICATES,
            codimension={"cod_pi_g": 3},
            rank_budget={
                "regime": "medium",
                "agent_pool": [{"agent_id": "a1", "model_family": "GPT-4o", "jacobian_rank": 3}],
                "orchestrator": {"model_family": "Opus", "jacobian_rank": 5},
            },
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_designs_memory_tiers(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_memory_tier_design
        mock_get.return_value = self._ws_with_rank_budget()

        result = im_memory_tier_design("ws-test-001")

        assert "memory" in result
        mem = result["memory"]
        assert "tiers" in mem
        assert len(mem["tiers"]) >= 2


# ---------------------------------------------------------------------------
# Tool 7: Synthesize Agent Specs
# ---------------------------------------------------------------------------

class TestSynthesizeAgentSpecs:
    def _ws_with_memory(self):
        M = [[1.0, 0.3, 0.1], [0.3, 1.0, 0.2], [0.1, 0.2, 1.0]]
        return _make_workspace(
            stage="memory_designed",
            predicates=SAMPLE_PREDICATES,
            predicate_blocks=SAMPLE_BLOCKS,
            coupling_matrix={"M": M, "locked": True},
            rank_budget={
                "regime": "medium",
                "agent_pool": [
                    {"agent_id": "a1", "model_family": "GPT-4o", "jacobian_rank": 3,
                     "steering_spectrum": [1.0, 0.8, 0.6]},
                    {"agent_id": "a2", "model_family": "GPT-4o-mini", "jacobian_rank": 2,
                     "steering_spectrum": [1.0, 0.7]},
                ],
                "orchestrator": {"model_family": "Opus", "jacobian_rank": 5,
                                 "steering_spectrum": [1.0, 0.9, 0.7, 0.5, 0.3]},
            },
            memory={"tiers": [{"name": "M0"}, {"name": "M1"}]},
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_synthesizes_agents(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_synthesize_agent_specs
        mock_get.return_value = self._ws_with_memory()

        result = im_synthesize_agent_specs("ws-test-001")

        assign = result["assignment"]
        assert "alpha_count" in assign
        assert "delta_norm" in assign
        assert "governance_margin" in assign
        assert assign["alpha_count"] > 0

    @patch(f"{STORE}.get_workspace")
    def test_no_coupling_matrix(self, mock_get):
        from src.im.tools import im_synthesize_agent_specs
        mock_get.return_value = _make_workspace(coupling_matrix={})

        result = im_synthesize_agent_specs("ws-test-001")
        assert "error" in result


# ---------------------------------------------------------------------------
# Tool 8: Synthesize Workflow Spec
# ---------------------------------------------------------------------------

class TestSynthesizeWorkflowSpec:
    def _ws_with_assignment(self):
        return _make_workspace(
            stage="agents_synthesized",
            predicates=SAMPLE_PREDICATES,
            predicate_blocks=SAMPLE_BLOCKS,
            cross_block_coupling=SAMPLE_CROSS_COUPLING,
            rank_budget={
                "regime": "medium",
                "orchestrator": {"model_family": "Opus", "jacobian_rank": 5},
            },
            assignment={
                "alpha": [{"predicate_id": "f_001", "agent_id": "a1"},
                          {"predicate_id": "f_002", "agent_id": "a1"},
                          {"predicate_id": "f_003", "agent_id": "a2"}],
                "delta_rank": 0,
                "delta_norm": 0.0,
                "governance_margin": 2,
                "agents": [
                    {"agent_id": "a1", "assigned_predicates": ["f_001", "f_002"]},
                    {"agent_id": "a2", "assigned_predicates": ["f_003"]},
                ],
            },
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_synthesizes_workflow(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_synthesize_workflow_spec
        mock_get.return_value = self._ws_with_assignment()

        result = im_synthesize_workflow_spec("ws-test-001")

        wf = result["workflow"]
        assert "topology_pattern" in wf
        assert "node_count" in wf
        assert wf["node_count"] > 0


# ---------------------------------------------------------------------------
# Tool 9: Validate Feasibility
# ---------------------------------------------------------------------------

class TestValidateFeasibility:
    def _ws_with_workflow(self):
        return _make_workspace(
            stage="workflow_synthesized",
            predicates=SAMPLE_PREDICATES,
            codimension={"cod_pi_g": 3, "eigenspectrum": [0.8, 0.5, 0.2]},
            rank_budget={
                "regime": "medium",
                "orchestrator": {"model_family": "Opus", "jacobian_rank": 5,
                                 "steering_spectrum": [1.0, 0.9, 0.7, 0.5, 0.3]},
                "agent_pool": [
                    {"agent_id": "a1", "jacobian_rank": 3, "steering_spectrum": [1.0, 0.8, 0.6]},
                    {"agent_id": "a2", "jacobian_rank": 2, "steering_spectrum": [1.0, 0.7]},
                ],
                "rank_surplus_or_deficit": 2,
                "total_rank": 10,
            },
            assignment={
                "alpha": [{"predicate_id": "f_001", "agent_id": "a1"},
                          {"predicate_id": "f_002", "agent_id": "a1"},
                          {"predicate_id": "f_003", "agent_id": "a2"}],
                "delta_rank": 0, "delta_norm": 0.0, "governance_margin": 2,
            },
            workflow={
                "topology": {"pattern": "fan_out", "nodes": [{"id": "n1"}, {"id": "n2"}], "edges": []},
                "compiled": True, "validation_errors": [],
            },
        )

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    def test_feasibility_check(self, mock_get, mock_update, mock_audit):
        from src.im.tools import im_validate_feasibility
        mock_get.return_value = self._ws_with_workflow()

        result = im_validate_feasibility("ws-test-001")

        feas = result["feasibility"]
        assert "verdict" in feas
        assert feas["verdict"] in ("feasible", "infeasible")

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_missing_workspace(self, mock_get):
        from src.im.tools import im_validate_feasibility
        result = im_validate_feasibility("ws-nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Utility tools
# ---------------------------------------------------------------------------

class TestListWorkspaces:
    @patch(f"{STORE}.list_workspaces", return_value=[
        {"workspace_id": "ws-1", "stage": "created"},
        {"workspace_id": "ws-2", "stage": "goal_parsed"},
    ])
    def test_list(self, mock_list):
        from src.im.tools import im_list_workspaces
        result = im_list_workspaces(limit=10)
        assert result["count"] == 2
        mock_list.assert_called_once_with(limit=10)


class TestGetWorkspace:
    @patch(f"{STORE}.get_audit_trail", return_value=[])
    @patch(f"{STORE}.get_workspace")
    def test_get(self, mock_get, mock_audit):
        from src.im.tools import im_get_workspace
        mock_get.return_value = _make_workspace()

        result = im_get_workspace("ws-test-001")

        assert result["workspace_id"] == "ws-test-001"
        assert result["stage"] == "created"
        assert "audit_trail" in result

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_not_found(self, mock_get):
        from src.im.tools import im_get_workspace
        result = im_get_workspace("ws-nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Full Pipeline (mocks at tool level — these are module-level functions)
# ---------------------------------------------------------------------------

class TestRunFullPipeline:
    @patch("src.im.tools.im_validate_feasibility")
    @patch("src.im.tools.im_synthesize_workflow_spec")
    @patch("src.im.tools.im_synthesize_agent_specs")
    @patch("src.im.tools.im_memory_tier_design")
    @patch("src.im.tools.im_rank_budget_and_regime")
    @patch("src.im.tools.im_estimate_codimension")
    @patch("src.im.tools.im_build_coupling_model")
    @patch("src.im.tools.im_generate_failure_predicates")
    @patch("src.im.tools.im_parse_goal_tuple")
    @patch("src.im.tools.im_get_workspace")
    def test_full_pipeline_success(self, mock_get_ws, mock_t1, mock_t2, mock_t3, mock_t4,
                                    mock_t5, mock_t6, mock_t7, mock_t8, mock_t9):
        from src.im.tools import im_run_full_pipeline

        mock_t1.return_value = {"workspace_id": "ws-full", "goal_tuple": {}, "stage": "goal_parsed"}
        mock_t2.return_value = {"predicates": SAMPLE_PREDICATES, "predicate_blocks": SAMPLE_BLOCKS}
        mock_t3.return_value = {"coupling_matrix": {"dimensions": "3×3"}}
        mock_t4.return_value = {"codimension": {"cod_pi_g": 3}}
        mock_t5.return_value = {"rank_budget": {"regime": "medium"}}
        mock_t6.return_value = {"memory": {"tiers": []}}
        mock_t7.return_value = {"assignment": {"alpha_count": 3, "delta_norm": 0.0, "governance_margin": 2}}
        mock_t8.return_value = {"workflow": {"topology_pattern": "fan_out", "node_count": 3}}
        mock_t9.return_value = {"feasibility": {"verdict": "feasible", "governance_margin": 2}}
        mock_get_ws.return_value = {"workspace_id": "ws-full", "stage": "feasibility_validated"}

        result = im_run_full_pipeline("Build a chatbot")

        assert result["workspace_id"] == "ws-full"
        assert result["verdict"] == "feasible"
        assert result["stage"] == "feasibility_validated"
        # All 9 tools called
        mock_t1.assert_called_once()
        mock_t2.assert_called_once()
        mock_t3.assert_called_once()
        mock_t4.assert_called_once()
        mock_t5.assert_called_once()
        mock_t6.assert_called_once()
        mock_t7.assert_called_once()
        mock_t8.assert_called_once()
        mock_t9.assert_called_once()

    @patch("src.im.tools.im_parse_goal_tuple")
    def test_pipeline_stops_on_error(self, mock_t1):
        from src.im.tools import im_run_full_pipeline
        mock_t1.return_value = {"error": "LLM unavailable"}

        result = im_run_full_pipeline("Test goal")
        assert "error" in result

    @patch("src.im.tools.im_generate_failure_predicates")
    @patch("src.im.tools.im_parse_goal_tuple")
    def test_pipeline_stops_at_step2_error(self, mock_t1, mock_t2):
        from src.im.tools import im_run_full_pipeline
        mock_t1.return_value = {"workspace_id": "ws-err", "goal_tuple": {}, "stage": "goal_parsed"}
        mock_t2.return_value = {"error": "G¹ index 0 out of range"}

        result = im_run_full_pipeline("Test goal")
        assert "error" in result
        assert result["workspace_id"] == "ws-err"


# ---------------------------------------------------------------------------
# Rule-based fallbacks (pure functions, no mocking needed)
# ---------------------------------------------------------------------------

class TestFallbacks:
    def test_rule_based_parse(self):
        from src.im.tools import _rule_based_parse
        result = _rule_based_parse("Build a chatbot for customer support")
        assert len(result) == 1
        assert len(result[0]["failure_predicates"]) == 3
        assert result[0]["epsilon_g"] == 0.05

    def test_fallback_predicates(self):
        from src.im.tools import _fallback_predicates
        result = _fallback_predicates("Build chatbot", SAMPLE_G1[0])
        assert len(result["predicates"]) == 3
        assert len(result["blocks"]) == 1
        assert result["predicates"][0]["severity"] == "high"
        assert result["predicates"][1]["severity"] == "medium"

    def test_assess_quality(self):
        from src.im.tools import _assess_quality
        result = _assess_quality(SAMPLE_PREDICATES)
        assert result["total"] == 3
        assert result["strong"] >= 1

    def test_detect_ambiguities_missing_fields(self):
        from src.im.tools import _detect_ambiguities
        candidates = [{"failure_predicates": ["one"]}]
        ambiguities = _detect_ambiguities(candidates)
        assert len(ambiguities) >= 3

    def test_detect_ambiguities_good_candidate(self):
        from src.im.tools import _detect_ambiguities
        ambiguities = _detect_ambiguities(SAMPLE_G1)
        assert len(ambiguities) == 0


# ---------------------------------------------------------------------------
# Default Agent Pool
# ---------------------------------------------------------------------------

class TestDefaultAgentPool:
    def test_small_codimension(self):
        from src.im.tools import _default_agent_pool
        pool = _default_agent_pool(3)
        assert len(pool) == 2

    def test_large_codimension(self):
        from src.im.tools import _default_agent_pool
        pool = _default_agent_pool(20)
        assert len(pool) == 8

    def test_agent_properties(self):
        from src.im.tools import _default_agent_pool
        pool = _default_agent_pool(6)
        for agent in pool:
            assert "agent_id" in agent
            assert "model_family" in agent
            assert "jacobian_rank" in agent
            assert agent["jacobian_rank"] >= 1
            assert "steering_spectrum" in agent


# ---------------------------------------------------------------------------
# Tool registry sanity
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_im_tools_has_all_15(self):
        from src.im.tools import IM_TOOLS
        assert len(IM_TOOLS) == 15

    def test_im_tool_schemas_has_all_15(self):
        from src.im.tools import IM_TOOL_SCHEMAS
        assert len(IM_TOOL_SCHEMAS) == 15

    def test_schemas_match_tools(self):
        from src.im.tools import IM_TOOLS, IM_TOOL_SCHEMAS
        schema_names = {s["name"] for s in IM_TOOL_SCHEMAS}
        tool_names = set(IM_TOOLS.keys())
        assert schema_names == tool_names

    def test_all_schemas_have_required_fields(self):
        from src.im.tools import IM_TOOL_SCHEMAS
        for schema in IM_TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

    def test_all_tools_are_callable(self):
        from src.im.tools import IM_TOOLS
        for name, fn in IM_TOOLS.items():
            assert callable(fn), f"Tool {name} is not callable"


# ---------------------------------------------------------------------------
# Store: delete_workspace returns bool
# ---------------------------------------------------------------------------

class TestDeleteWorkspaceReturnType:
    def test_delete_returns_bool_annotation(self):
        """Verify the delete_workspace fix — return annotation should be bool."""
        import inspect
        from src.im.store import delete_workspace
        sig = inspect.signature(delete_workspace)
        assert sig.return_annotation in (bool, "bool")


# ---------------------------------------------------------------------------
# Tool 10: Spawn Agents
# ---------------------------------------------------------------------------

def _feasible_workspace(**overrides):
    """Create a workspace that's ready for spawning (feasibility_validated, verdict=feasible)."""
    defaults = dict(
        workspace_id="ws-spawn-001",
        stage="feasibility_validated",
        raw_intent="Build a customer support chatbot",
        predicates=SAMPLE_PREDICATES,
        predicate_blocks=SAMPLE_BLOCKS,
        cross_block_coupling=SAMPLE_CROSS_COUPLING,
        coupling_matrix={"M": [[1, 0.2, 0.1], [0.2, 1, 0.15], [0.1, 0.15, 1]], "locked": True},
        codimension={"cod_pi_g": 3, "eigenspectrum": [{"index": 0, "value": 1.3}]},
        rank_budget={
            "regime": "medium",
            "agent_pool": [
                {"agent_id": "agent_1", "name": "Quality Agent", "model_family": "GPT-4o",
                 "jacobian_rank": 2, "steering_spectrum": [1.0, 0.7], "context_window": 200000,
                 "assigned_predicates": ["f_001", "f_002"], "tools": []},
                {"agent_id": "agent_2", "name": "Security Agent", "model_family": "GPT-4o-mini",
                 "jacobian_rank": 1, "steering_spectrum": [1.0], "context_window": 200000,
                 "assigned_predicates": ["f_003"], "tools": []},
            ],
            "orchestrator": {"model_family": "Claude Opus 4.6", "jacobian_rank": 5},
            "total_rank": 10, "rank_surplus_or_deficit": 2,
        },
        assignment={
            "alpha": [
                {"predicate_id": "f_001", "agent_id": "agent_1"},
                {"predicate_id": "f_002", "agent_id": "agent_1"},
                {"predicate_id": "f_003", "agent_id": "agent_2"},
            ],
            "agents": [
                {"agent_id": "agent_1", "name": "Quality Agent", "model_family": "GPT-4o",
                 "jacobian_rank": 2, "assigned_predicates": ["f_001", "f_002"], "tools": []},
                {"agent_id": "agent_2", "name": "Security Agent", "model_family": "GPT-4o-mini",
                 "jacobian_rank": 1, "assigned_predicates": ["f_003"], "tools": []},
            ],
            "delta_rank": 0, "delta_norm": 0.0, "governance_margin": 2,
        },
        workflow={
            "topology": {
                "pattern": "hierarchical",
                "nodes": [
                    {"node_id": "orchestrator", "agent_id": "orchestrator", "role": "orchestrator"},
                    {"node_id": "agent_1", "agent_id": "agent_1", "role": "task_agent"},
                    {"node_id": "agent_2", "agent_id": "agent_2", "role": "task_agent"},
                ],
                "edges": [
                    {"source": "orchestrator", "target": "agent_1", "protocol": "async"},
                    {"source": "orchestrator", "target": "agent_2", "protocol": "async"},
                ],
            },
            "compiled": True, "validation_errors": [],
        },
        feasibility={"verdict": "feasible", "rank_coverage": True,
                     "coupling_coverage": True, "power_coverage": True, "governance_margin": 2},
        metadata={},
    )
    defaults.update(overrides)
    return _make_workspace(**defaults)


AGENT_REG = "src.agent_registry"
WF_REG = "src.workflow_registry"


class TestSpawnAgents:
    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{AGENT_REG}.get_registry")
    def test_spawn_creates_agents(self, mock_registry, mock_get, mock_update, mock_audit):
        from src.im.tools import im_spawn_agents
        ws = _feasible_workspace()
        mock_get.return_value = ws
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.return_value = MagicMock()  # Success
        mock_registry.return_value = mock_reg_inst

        result = im_spawn_agents("ws-spawn-001")

        assert "error" not in result
        assert len(result["spawned"]) == 2
        assert result["stage"] == "agents_spawned"
        assert mock_reg_inst.create.call_count == 2
        mock_update.assert_called_once()
        mock_audit.assert_called_once()

    @patch(f"{STORE}.get_workspace")
    def test_spawn_dry_run(self, mock_get):
        from src.im.tools import im_spawn_agents
        mock_get.return_value = _feasible_workspace()

        result = im_spawn_agents("ws-spawn-001", dry_run=True)

        assert result["dry_run"] is True
        assert len(result["spawned"]) == 2
        assert result["stage"] == "preview"
        # No DB writes in dry run
        for s in result["spawned"]:
            assert s["dry_run"] is True

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_spawn_workspace_not_found(self, mock_get):
        from src.im.tools import im_spawn_agents
        result = im_spawn_agents("ws-nonexistent")
        assert "error" in result

    @patch(f"{STORE}.get_workspace")
    def test_spawn_requires_feasible_verdict(self, mock_get):
        from src.im.tools import im_spawn_agents
        ws = _feasible_workspace(feasibility={"verdict": "infeasible"})
        mock_get.return_value = ws

        result = im_spawn_agents("ws-spawn-001")
        assert "error" in result
        assert "feasible" in result["error"]

    @patch(f"{STORE}.get_workspace")
    def test_spawn_requires_agent_specs(self, mock_get):
        from src.im.tools import im_spawn_agents
        ws = _feasible_workspace(assignment={"agents": [], "alpha": []})
        mock_get.return_value = ws

        result = im_spawn_agents("ws-spawn-001")
        assert "error" in result

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{AGENT_REG}.get_registry")
    def test_spawn_handles_registry_error(self, mock_registry, mock_get, mock_update, mock_audit):
        from src.im.tools import im_spawn_agents
        mock_get.return_value = _feasible_workspace()
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.side_effect = Exception("DB connection failed")
        mock_registry.return_value = mock_reg_inst

        result = im_spawn_agents("ws-spawn-001")

        assert len(result["errors"]) == 2
        assert len(result["spawned"]) == 0

    def test_model_family_mapping(self):
        from src.im.tools import _MODEL_FAMILY_TO_ID
        assert _MODEL_FAMILY_TO_ID["GPT-4o"] == "gpt4o"
        assert _MODEL_FAMILY_TO_ID["GPT-4o-mini"] == "gpt4o_mini"
        assert _MODEL_FAMILY_TO_ID["Claude Opus 4.6"] == "claude_opus"
        assert _MODEL_FAMILY_TO_ID["Ollama Qwen"] == "ollama_qwen"


# ---------------------------------------------------------------------------
# Tool 11: Deploy Workflow
# ---------------------------------------------------------------------------

class TestDeployWorkflow:
    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{WF_REG}.get_workflow_registry")
    def test_deploy_creates_workflow(self, mock_wf_reg, mock_get, mock_update, mock_audit):
        from src.im.tools import im_deploy_workflow
        ws = _feasible_workspace(metadata={"spawn_short_id": "abc12345"})
        mock_get.return_value = ws
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.return_value = {"workflow_id": "im_abc12345"}
        mock_wf_reg.return_value = mock_reg_inst

        result = im_deploy_workflow("ws-spawn-001")

        assert "error" not in result
        assert result["workflow_id"] == "im_abc12345"
        assert result["nodes"] == 3  # orchestrator + 2 agents
        assert result["edges"] >= 2  # at least the 2 from topology
        assert result["stage"] == "deployed"
        mock_reg_inst.create.assert_called_once()
        mock_update.assert_called_once()

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{WF_REG}.get_workflow_registry")
    def test_deploy_with_activate(self, mock_wf_reg, mock_get, mock_update, mock_audit):
        from src.im.tools import im_deploy_workflow
        mock_get.return_value = _feasible_workspace(metadata={"spawn_short_id": "test1234"})
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.return_value = {}
        mock_wf_reg.return_value = mock_reg_inst

        result = im_deploy_workflow("ws-spawn-001", activate=True)

        assert result["activated"] is True
        mock_reg_inst.activate.assert_called_once_with("im_test1234")

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{WF_REG}.get_workflow_registry")
    @patch("src.holly.tools.start_workflow")
    def test_deploy_with_auto_start(self, mock_start, mock_wf_reg, mock_get, mock_update, mock_audit):
        from src.im.tools import im_deploy_workflow
        mock_get.return_value = _feasible_workspace(metadata={"spawn_short_id": "auto1234"})
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.return_value = {}
        mock_wf_reg.return_value = mock_reg_inst
        mock_start.return_value = {"run_id": "run-001"}

        result = im_deploy_workflow("ws-spawn-001", auto_start=True)

        assert result["run_id"] == "run-001"
        mock_start.assert_called_once()

    @patch(f"{STORE}.get_workspace", return_value=None)
    def test_deploy_workspace_not_found(self, mock_get):
        from src.im.tools import im_deploy_workflow
        result = im_deploy_workflow("ws-nonexistent")
        assert "error" in result

    @patch(f"{STORE}.get_workspace")
    def test_deploy_requires_feasible(self, mock_get):
        from src.im.tools import im_deploy_workflow
        ws = _feasible_workspace(feasibility={"verdict": "infeasible"})
        mock_get.return_value = ws

        result = im_deploy_workflow("ws-spawn-001")
        assert "error" in result

    @patch(f"{STORE}.get_workspace")
    def test_deploy_requires_workflow_nodes(self, mock_get):
        from src.im.tools import im_deploy_workflow
        ws = _feasible_workspace(workflow={"topology": {"nodes": [], "edges": []}})
        mock_get.return_value = ws

        result = im_deploy_workflow("ws-spawn-001")
        assert "error" in result

    @patch(f"{STORE}.log_audit")
    @patch(f"{STORE}.update_workspace")
    @patch(f"{STORE}.get_workspace")
    @patch(f"{WF_REG}.get_workflow_registry")
    def test_deploy_adds_end_edges_for_terminals(self, mock_wf_reg, mock_get, mock_update, mock_audit):
        from src.im.tools import im_deploy_workflow
        mock_get.return_value = _feasible_workspace(metadata={"spawn_short_id": "end12345"})
        mock_reg_inst = MagicMock()
        mock_reg_inst.create.return_value = {}
        mock_wf_reg.return_value = mock_reg_inst

        result = im_deploy_workflow("ws-spawn-001")

        # Original topology: orch→a1, orch→a2. a1 and a2 have no outgoing.
        # Deploy should add __end__ edges for terminals.
        assert result["edges"] >= 4  # 2 original + at least 2 __end__


# ---------------------------------------------------------------------------
# Tool 12: Instantiate (convenience wrapper)
# ---------------------------------------------------------------------------

class TestInstantiate:
    @patch("src.im.tools.im_deploy_workflow")
    @patch("src.im.tools.im_spawn_agents")
    def test_instantiate_success(self, mock_spawn, mock_deploy):
        from src.im.tools import im_instantiate
        mock_spawn.return_value = {
            "workspace_id": "ws-inst-001",
            "spawned": [{"agent_id": "a1"}, {"agent_id": "a2"}],
            "errors": [],
            "stage": "agents_spawned",
        }
        mock_deploy.return_value = {
            "workspace_id": "ws-inst-001",
            "workflow_id": "im_inst001",
            "nodes": 3,
            "edges": 4,
            "activated": False,
            "run_id": "run-inst-001",
            "stage": "deployed",
        }

        result = im_instantiate("ws-inst-001")

        assert result["agents_spawned"] == 2
        assert result["workflow_id"] == "im_inst001"
        assert result["run_id"] == "run-inst-001"
        assert result["stage"] == "deployed"
        mock_spawn.assert_called_once_with("ws-inst-001")
        mock_deploy.assert_called_once_with("ws-inst-001", activate=False, auto_start=True)

    @patch("src.im.tools.im_spawn_agents")
    def test_instantiate_stops_on_spawn_error(self, mock_spawn):
        from src.im.tools import im_instantiate
        mock_spawn.return_value = {"error": "Workspace must have verdict=feasible"}

        result = im_instantiate("ws-fail")
        assert "error" in result

    @patch("src.im.tools.im_deploy_workflow")
    @patch("src.im.tools.im_spawn_agents")
    def test_instantiate_propagates_deploy_error(self, mock_spawn, mock_deploy):
        from src.im.tools import im_instantiate
        mock_spawn.return_value = {"spawned": [{"agent_id": "a1"}], "errors": []}
        mock_deploy.return_value = {"error": "No workflow topology nodes"}

        result = im_instantiate("ws-fail-deploy")
        assert "error" in result
        assert "spawn" in result  # spawn result preserved


# ---------------------------------------------------------------------------
# New stages in WorkspaceStage enum
# ---------------------------------------------------------------------------

class TestNewWorkspaceStages:
    def test_agents_spawned_stage(self):
        from src.im.models import WorkspaceStage
        assert WorkspaceStage.AGENTS_SPAWNED.value == "agents_spawned"

    def test_deployed_stage(self):
        from src.im.models import WorkspaceStage
        assert WorkspaceStage.DEPLOYED.value == "deployed"

    def test_total_stages(self):
        from src.im.models import WorkspaceStage
        assert len(list(WorkspaceStage)) == 12
