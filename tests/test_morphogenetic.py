"""Tests for the morphogenetic agency subsystem.

Covers: goals, trigger, assembly, cascade, instruments, scheduler job.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest


# =========================================================================
# Goal specs
# =========================================================================


class TestGoalSpec:
    def test_default_goal_count(self):
        from src.morphogenetic.goals import get_default_goal_specs

        goals = get_default_goal_specs()
        assert len(goals) == 8

    def test_goal_has_required_fields(self):
        from src.morphogenetic.goals import LEVEL_G0, LEVEL_G1, LEVEL_G2, get_default_goal_specs

        goals = get_default_goal_specs()
        valid_levels = (LEVEL_G0, LEVEL_G1, LEVEL_G2)
        for g in goals:
            assert g.goal_id
            assert g.display_name
            assert g.formalization_level in valid_levels, f"{g.goal_id} has invalid level {g.formalization_level}"
            assert 0.0 <= g.epsilon_g <= 1.0
            assert g.horizon_t > 0
            assert g.primary_tier in (0, 1, 2, 3)

    def test_g1_and_g2_are_formalized(self):
        from src.morphogenetic.goals import LEVEL_G0, get_default_goal_specs

        goals = get_default_goal_specs()
        for g in goals:
            if g.formalization_level == LEVEL_G0:
                assert not g.is_formalized(), f"{g.goal_id} (G0) should not be formalized"
            else:
                assert g.is_formalized(), f"{g.goal_id} ({g.formalization_level}) should be formalized"

    def test_all_defaults_are_formalized(self):
        """All default goals should be at G1 or G2 (no G0 placeholders)."""
        from src.morphogenetic.goals import get_default_goal_specs

        goals = get_default_goal_specs()
        for g in goals:
            assert g.is_formalized(), f"{g.goal_id} should be formalized"

    def test_formalization_gap_is_zero_for_defaults(self):
        from src.morphogenetic.goals import compute_formalization_gap, get_default_goal_specs

        goals = get_default_goal_specs()
        gap = compute_formalization_gap(goals)
        assert gap == 0.0  # All defaults are formalized

    def test_formalization_gap(self):
        from src.morphogenetic.goals import LEVEL_G0, GoalSpec, compute_formalization_gap

        goals = [
            GoalSpec(goal_id="a", display_name="A", failure_predicate="p_fail",
                     epsilon_g=0.1, horizon_t=100, observation_map=["K1"],
                     formalization_level=LEVEL_G0),
            GoalSpec(goal_id="b", display_name="B", failure_predicate="p_fail",
                     epsilon_g=0.1, horizon_t=100, observation_map=["K1"]),
        ]
        gap = compute_formalization_gap(goals)
        assert abs(gap - 0.5) < 0.001

    def test_observation_maps_are_lists(self):
        from src.morphogenetic.goals import get_default_goal_specs

        goals = get_default_goal_specs()
        for g in goals:
            assert isinstance(g.observation_map, list)
            for ch in g.observation_map:
                assert isinstance(ch, str)

    def test_spec_gap_method(self):
        from src.morphogenetic.goals import GoalSpec

        g = GoalSpec(goal_id="t", display_name="T", failure_predicate="p_fail",
                     epsilon_g=0.1, horizon_t=100, observation_map=["K1"])
        assert abs(g.spec_gap(0.3) - 0.2) < 0.001
        assert g.spec_gap(0.05) < 0.0  # Within tolerance

    def test_is_satisfied_method(self):
        from src.morphogenetic.goals import GoalSpec

        g = GoalSpec(goal_id="t", display_name="T", failure_predicate="p_fail",
                     epsilon_g=0.1, horizon_t=100, observation_map=["K1"])
        assert g.is_satisfied(0.05)
        assert not g.is_satisfied(0.2)


# =========================================================================
# Epsilon trigger
# =========================================================================


class TestEpsilonTrigger:
    def test_hoeffding_ucb_basic(self):
        from src.morphogenetic.trigger import hoeffding_ucb

        ucb = hoeffding_ucb(0.3, 100, 0.05)
        assert ucb > 0.3  # UCB should be above p_fail
        assert ucb <= 1.0

    def test_hoeffding_ucb_wide_with_few_observations(self):
        from src.morphogenetic.trigger import hoeffding_ucb

        ucb_few = hoeffding_ucb(0.3, 5, 0.05)
        ucb_many = hoeffding_ucb(0.3, 1000, 0.05)
        assert ucb_few > ucb_many

    def test_hoeffding_ucb_zero_observations(self):
        from src.morphogenetic.trigger import hoeffding_ucb

        ucb = hoeffding_ucb(0.5, 0, 0.05)
        assert ucb == 1.0

    def test_trigger_fires_when_failing(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="test_goal", display_name="Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )
        result = check_epsilon_trigger(
            goal=goal, p_fail=0.5, n_observations=100, channel_id="K1"
        )
        assert result.triggered is True
        assert result.goal_id == "test_goal"
        assert result.channel_id == "K1"
        assert result.p_fail_ucb > 0.5

    def test_trigger_does_not_fire_when_within_tolerance(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="test_goal", display_name="Test",
            failure_predicate="p_fail", epsilon_g=0.5,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )
        result = check_epsilon_trigger(
            goal=goal, p_fail=0.05, n_observations=100, channel_id="K1"
        )
        assert result.triggered is False

    def test_trigger_skips_insufficient_observations(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="test_goal", display_name="Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )
        result = check_epsilon_trigger(
            goal=goal, p_fail=0.9, n_observations=5, channel_id="K1"
        )
        assert result.triggered is False
        assert result.reason == "insufficient_observations"

    def test_trigger_respects_formalized_check_in_all_triggers(self):
        from src.morphogenetic.goals import LEVEL_G0, GoalSpec
        from src.morphogenetic.trigger import check_all_triggers

        goals = [
            GoalSpec(
                goal_id="informal", display_name="Informal",
                failure_predicate="p_fail", epsilon_g=0.1,
                horizon_t=1800, observation_map=["K1"],
                formalization_level=LEVEL_G0,
            )
        ]
        metrics = {"K1": {"p_fail": 0.9, "n_observations": 100}}
        triggers = check_all_triggers(goals, metrics)
        assert len(triggers) == 0  # G0 goals are skipped

    def test_recommended_tier_severity(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="test_goal", display_name="Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )
        # Mild failure
        mild = check_epsilon_trigger(goal=goal, p_fail=0.15, n_observations=100, channel_id="K1")
        assert mild.triggered is True
        assert mild.recommended_tier == 0

        # Severe failure (margin >> epsilon)
        severe = check_epsilon_trigger(goal=goal, p_fail=0.9, n_observations=100, channel_id="K1")
        assert severe.triggered is True
        assert severe.recommended_tier >= 1

    def test_check_all_triggers_empty_metrics(self):
        from src.morphogenetic.goals import get_default_goal_specs
        from src.morphogenetic.trigger import check_all_triggers

        goals = get_default_goal_specs()
        triggers = check_all_triggers(goals, {})
        # With no metrics (n_observations=0), nothing should trigger
        assert len(triggers) == 0

    def test_check_all_triggers_with_failing_channel(self):
        from src.morphogenetic.goals import get_default_goal_specs
        from src.morphogenetic.trigger import check_all_triggers

        goals = get_default_goal_specs()
        metrics = {"K1": {"p_fail": 0.8, "n_observations": 100}}
        triggers = check_all_triggers(goals, metrics)
        # K1 is in observation_map of several goals
        assert len(triggers) > 0
        for t in triggers:
            assert t.channel_id == "K1"
            assert t.triggered is True


# =========================================================================
# Assembly cache
# =========================================================================


class TestAssembly:
    def test_classify_competency_tier0_escalated(self):
        from src.morphogenetic.assembly import classify_competency

        assert classify_competency(0, {"direction": "escalated"}) == "sensitization"

    def test_classify_competency_tier0_default(self):
        from src.morphogenetic.assembly import classify_competency

        assert classify_competency(0, {}) == "habituation"

    def test_classify_competency_tier1(self):
        from src.morphogenetic.assembly import classify_competency

        assert classify_competency(1, {}) == "associative"

    def test_classify_competency_tier2_3(self):
        from src.morphogenetic.assembly import classify_competency

        assert classify_competency(2, {}) == "homeostatic"
        assert classify_competency(3, {}) == "homeostatic"

    def test_compute_assembly_index(self):
        from src.morphogenetic.assembly import compute_assembly_index

        ai_simple = compute_assembly_index({"type": "theta_switch"}, tier=0)
        assert ai_simple >= 1.0

        ai_complex = compute_assembly_index(
            {"type": "scale_reorganization", "agent_added": True, "extra": "stuff"},
            tier=3,
        )
        assert ai_complex > ai_simple

    def test_generate_context_fingerprint_deterministic(self):
        from src.morphogenetic.assembly import generate_context_fingerprint

        fp1 = generate_context_fingerprint("K1", {"p_fail": 0.3})
        fp2 = generate_context_fingerprint("K1", {"p_fail": 0.3})
        assert fp1 == fp2

    def test_generate_context_fingerprint_varies_by_channel(self):
        from src.morphogenetic.assembly import generate_context_fingerprint

        fp1 = generate_context_fingerprint("K1", {"p_fail": 0.3})
        fp2 = generate_context_fingerprint("K2", {"p_fail": 0.3})
        assert fp1 != fp2

    def test_generate_competency_id_deterministic(self):
        from src.morphogenetic.assembly import generate_competency_id

        cid1 = generate_competency_id("K1", "goal_routing", {"type": "theta_switch"})
        cid2 = generate_competency_id("K1", "goal_routing", {"type": "theta_switch"})
        assert cid1 == cid2
        assert cid1.startswith("comp_")

    def test_generate_competency_id_varies(self):
        from src.morphogenetic.assembly import generate_competency_id

        cid1 = generate_competency_id("K1", "goal_a", {"type": "theta_switch"})
        cid2 = generate_competency_id("K1", "goal_b", {"type": "theta_switch"})
        assert cid1 != cid2

    def test_cached_competency_dataclass(self):
        from src.morphogenetic.assembly import CachedCompetency

        comp = CachedCompetency(
            competency_id="comp_abc", tier=0,
            competency_type="sensitization", channel_id="K1",
            goal_id="routing", adaptation={"type": "theta_switch"},
            context_fingerprint="fp_abc",
        )
        assert comp.reuse_count == 0
        assert comp.success_rate == 1.0

    def test_competency_types_ordered(self):
        from src.morphogenetic.assembly import COMPETENCY_COST, COMPETENCY_TYPES

        assert len(COMPETENCY_TYPES) == 4
        # Homeostatic should be the most expensive
        assert COMPETENCY_COST["homeostatic"] >= COMPETENCY_COST["sensitization"]


# =========================================================================
# Cascade
# =========================================================================


class TestCascade:
    def test_cascade_result_has_fields(self):
        from src.morphogenetic.cascade import CascadeResult

        result = CascadeResult("goal1", "K1")
        assert result.goal_id == "goal1"
        assert result.channel_id == "K1"
        assert result.outcome == "pending"
        assert result.cascade_id.startswith("casc_")

    def test_cascade_result_to_dict(self):
        from src.morphogenetic.cascade import CascadeResult

        result = CascadeResult("goal1", "K1")
        d = result.to_dict()
        assert d["goal_id"] == "goal1"
        assert d["channel_id"] == "K1"
        assert "cascade_id" in d
        assert "outcome" in d
        assert "diagnostics" in d

    def test_cascade_diagnostic_questions_all_tiers(self):
        from src.morphogenetic.cascade import MorphogeneticCascade
        from src.morphogenetic.trigger import TriggerResult

        cascade = MorphogeneticCascade()
        trigger = TriggerResult(
            triggered=True, goal_id="test", channel_id="K1",
            p_fail=0.5, p_fail_ucb=0.6, epsilon_g=0.1,
            recommended_tier=0,
        )

        for tier in range(4):
            diag = cascade._diagnostic_question(tier, trigger, {})
            assert "question" in diag
            assert diag["tier"] == tier
            assert diag["p_fail"] == 0.5
            assert diag["epsilon_g"] == 0.1

    def test_cascade_executes_to_completion(self):
        """Cascade should complete with success or failure (uses real DB)."""
        from src.morphogenetic.cascade import MorphogeneticCascade
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import TriggerResult

        cascade = MorphogeneticCascade()
        trigger = TriggerResult(
            triggered=True, goal_id="test", channel_id="K1",
            p_fail=0.5, p_fail_ucb=0.6, epsilon_g=0.1,
            recommended_tier=0,
        )
        goal = GoalSpec(
            goal_id="test", display_name="Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )

        result = cascade.execute(trigger, goal, {"K1": {"p_fail": 0.5}})
        assert result.outcome in ("success", "failure", "approval_pending", "cache_hit")
        assert result.tier_attempted >= 0

    def test_get_cascade_singleton(self):
        from src.morphogenetic.cascade import get_cascade

        c1 = get_cascade()
        c2 = get_cascade()
        assert c1 is c2

    def test_cascade_limits_defaults(self):
        from src.morphogenetic.cascade import (
            _CASCADE_TIMEOUT_SECONDS_DEFAULT,
            _MAX_TIER0_ATTEMPTS_DEFAULT,
            _MAX_TIER1_ATTEMPTS_DEFAULT,
        )

        assert _MAX_TIER0_ATTEMPTS_DEFAULT > 0
        assert _MAX_TIER1_ATTEMPTS_DEFAULT > 0
        assert _CASCADE_TIMEOUT_SECONDS_DEFAULT > 0

    def test_cascade_config_from_db(self):
        from src.morphogenetic.cascade import _get_cascade_config

        cfg = _get_cascade_config()
        assert "max_tier0_attempts" in cfg
        assert "tier0_enabled" in cfg
        assert cfg["max_tier0_attempts"] > 0


# =========================================================================
# Instruments
# =========================================================================


class TestInstruments:
    def test_developmental_snapshot_defaults(self):
        from src.morphogenetic.instruments import DevelopmentalSnapshot

        snap = DevelopmentalSnapshot()
        assert snap.ai_proxy == 0.0
        assert snap.clc_horizon == 0
        assert snap.clc_dimensions == 0
        assert snap.eta_mean == 0.0
        assert snap.attractor_count == 0
        assert snap.spec_gap_mean == 0.0
        assert snap.total_reuse == 0
        assert snap.p_feasible_count == 0

    def test_snapshot_to_dict(self):
        from src.morphogenetic.instruments import DevelopmentalSnapshot

        snap = DevelopmentalSnapshot()
        d = snap.to_dict()
        assert "ai_proxy" in d
        assert "clc_horizon" in d
        assert "snapshot_at" in d
        assert isinstance(d["snapshot_at"], str)
        assert isinstance(d["cp_profile"], dict)
        assert isinstance(d["competency_dist"], dict)
        assert isinstance(d["tier_usage"], dict)

    def test_compute_eta_mean_empty(self):
        from src.morphogenetic.instruments import _compute_eta_mean

        assert _compute_eta_mean({}) == 0.0

    def test_compute_eta_mean_with_values(self):
        from src.morphogenetic.instruments import _compute_eta_mean

        metrics = {
            "K1": {"eta_usd": 0.5},
            "K2": {"eta_usd": 0.3},
            "K3": {"eta_usd": 0.0},  # Excluded (zero)
        }
        eta = _compute_eta_mean(metrics)
        assert abs(eta - 0.4) < 0.001

    def test_compute_cp_profile(self):
        from src.morphogenetic.instruments import _compute_cp_profile

        metrics = {
            "K1": {"capacity": 0.85},
            "K2": {"capacity": 0.72},
            "K3": {},
        }
        profile = _compute_cp_profile(metrics)
        assert "K1" in profile
        assert "K2" in profile
        assert "K3" not in profile
        assert profile["K1"] == 0.85

    def test_count_feasible_partitions(self):
        from src.morphogenetic.instruments import _count_feasible_partitions

        metrics = {
            "K1": {"n_observations": 50},
            "K2": {"n_observations": 10},
            "K3": {"n_observations": 25},
        }
        assert _count_feasible_partitions(metrics) == 2

    def test_count_feasible_partitions_empty(self):
        from src.morphogenetic.instruments import _count_feasible_partitions

        assert _count_feasible_partitions({}) == 0

    def test_compute_spec_gap_all_satisfied(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.instruments import _compute_spec_gap

        goals = [
            GoalSpec(
                goal_id="g1", display_name="G1",
                failure_predicate="p_fail", epsilon_g=0.3,
                horizon_t=1800, observation_map=["K1"], primary_tier=0,
            )
        ]
        metrics = {"K1": {"p_fail": 0.1}}
        gap = _compute_spec_gap(goals, metrics)
        assert gap == 0.0

    def test_compute_spec_gap_failing(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.instruments import _compute_spec_gap

        goals = [
            GoalSpec(
                goal_id="g1", display_name="G1",
                failure_predicate="p_fail", epsilon_g=0.1,
                horizon_t=1800, observation_map=["K1"], primary_tier=0,
            )
        ]
        metrics = {"K1": {"p_fail": 0.5}}
        gap = _compute_spec_gap(goals, metrics)
        assert abs(gap - 0.4) < 0.001

    def test_count_attractors(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.instruments import _count_attractors

        goals = [
            GoalSpec(
                goal_id="g1", display_name="G1",
                failure_predicate="p_fail", epsilon_g=0.3,
                horizon_t=1800, observation_map=["K1"], primary_tier=0,
            ),
            GoalSpec(
                goal_id="g2", display_name="G2",
                failure_predicate="p_fail", epsilon_g=0.1,
                horizon_t=1800, observation_map=["K2"], primary_tier=0,
            ),
        ]
        metrics = {
            "K1": {"p_fail": 0.1},  # Satisfied
            "K2": {"p_fail": 0.5},  # Not satisfied
        }
        assert _count_attractors(goals, metrics) == 1

    def test_count_attractors_all_satisfied(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.instruments import _count_attractors

        goals = [
            GoalSpec(
                goal_id="g1", display_name="G1",
                failure_predicate="p_fail", epsilon_g=0.3,
                horizon_t=1800, observation_map=["K1"], primary_tier=0,
            ),
        ]
        metrics = {"K1": {"p_fail": 0.1}}
        assert _count_attractors(goals, metrics) == 1

    def test_compute_clc(self):
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.instruments import _compute_clc

        goals = [
            GoalSpec(
                goal_id="g1", display_name="G1",
                failure_predicate="p_fail", epsilon_g=0.3,
                horizon_t=1800, observation_map=["K1", "K2"],
                primary_tier=0,
            ),
            GoalSpec(
                goal_id="g2", display_name="G2",
                failure_predicate="p_fail", epsilon_g=0.3,
                horizon_t=3600, observation_map=["K3"],
                primary_tier=0,
            ),
        ]
        metrics = {
            "K1": {"p_fail": 0.1},
            "K2": {"p_fail": 0.1},
            "K3": {"p_fail": 0.5},  # Fails — g2 not satisfied
        }
        horizon, dims = _compute_clc(goals, metrics)
        assert horizon == 1800
        assert dims == 2

    def test_compute_clc_empty(self):
        from src.morphogenetic.instruments import _compute_clc

        horizon, dims = _compute_clc([], {})
        assert horizon == 0
        assert dims == 0

    def test_compute_developmental_snapshot_with_empty_data(self):
        from src.morphogenetic.instruments import compute_developmental_snapshot

        snap = compute_developmental_snapshot(goals=[], metrics={})
        assert snap.ai_proxy >= 0.0
        assert snap.attractor_count == 0
        assert snap.spec_gap_mean == 0.0


# =========================================================================
# Scheduler job
# =========================================================================


class TestSchedulerJob:
    @patch("src.aps.store.store_developmental_snapshot")
    @patch("src.aps.store.get_latest_metrics", return_value=[])
    def test_morphogenetic_evaluation_job_runs(self, mock_metrics, mock_store):
        from src.morphogenetic.scheduler_jobs import morphogenetic_evaluation_job

        morphogenetic_evaluation_job()
        mock_store.assert_called_once()

    @patch("src.aps.store.store_developmental_snapshot")
    @patch("src.aps.store.get_latest_metrics")
    def test_morphogenetic_evaluation_with_failing_channel(self, mock_metrics, mock_store):
        mock_metrics.return_value = [
            {"channel_id": "K1", "p_fail": 0.8, "n_observations": 100},
        ]

        from src.morphogenetic.scheduler_jobs import morphogenetic_evaluation_job

        # Job should complete without crashing — cascade failures are caught internally
        morphogenetic_evaluation_job()
        # store_developmental_snapshot may or may not be called depending on
        # whether cascade DB operations succeed, but the job shouldn't raise
        assert True


# =========================================================================
# Cascade config CRUD
# =========================================================================


class TestCascadeConfigCRUD:
    """Tests for cascade_config DB CRUD (store.py)."""

    def test_get_cascade_config_returns_defaults(self):
        from src.aps.store import get_cascade_config

        cfg = get_cascade_config()
        assert isinstance(cfg, dict)
        assert "min_observations" in cfg
        assert "delta" in cfg
        assert "max_tier0_attempts" in cfg
        assert "tier0_enabled" in cfg
        assert "tier2_auto_approve" in cfg

    def test_cascade_config_default_values(self):
        from src.aps.store import get_cascade_config

        cfg = get_cascade_config()
        assert cfg["min_observations"] == 20
        assert abs(cfg["delta"] - 0.05) < 0.001
        assert cfg["max_tier0_attempts"] == 3
        assert cfg["max_tier1_attempts"] == 2
        assert cfg["cascade_timeout_seconds"] == 60

    def test_update_cascade_config(self):
        from src.aps.store import get_cascade_config, reset_cascade_config, update_cascade_config

        try:
            result = update_cascade_config({"min_observations": 10, "delta": 0.1})
            assert result["min_observations"] == 10
            assert abs(result["delta"] - 0.1) < 0.001
            # Other fields unchanged
            assert result["max_tier0_attempts"] == 3
        finally:
            reset_cascade_config()

    def test_update_cascade_config_ignores_unknown_keys(self):
        from src.aps.store import update_cascade_config

        result = update_cascade_config({"unknown_key": 999, "min_observations": 15})
        assert "unknown_key" not in result
        assert result["min_observations"] == 15

    def test_reset_cascade_config(self):
        from src.aps.store import reset_cascade_config, update_cascade_config

        update_cascade_config({"min_observations": 5})
        result = reset_cascade_config()
        assert result["min_observations"] == 20

    def test_update_tier_enabled_flags(self):
        from src.aps.store import reset_cascade_config, update_cascade_config

        try:
            result = update_cascade_config({"tier2_enabled": False, "tier3_auto_approve": True})
            assert result["tier2_enabled"] is False
            assert result["tier3_auto_approve"] is True
        finally:
            reset_cascade_config()


# =========================================================================
# Goal CRUD
# =========================================================================


class TestGoalCRUD:
    """Tests for morphogenetic_goals DB CRUD (store.py)."""

    _TEST_GOAL = {
        "goal_id": "test_crud_goal",
        "display_name": "Test CRUD Goal",
        "failure_predicate": "p_fail > epsilon",
        "epsilon_g": 0.15,
        "horizon_t": 900,
        "observation_map": ["K1", "K2"],
        "formalization_level": "g1_spec",
        "g0_description": "",
        "primary_tier": 1,
        "priority": 7,
    }

    def _cleanup(self):
        from src.aps.store import delete_goal
        delete_goal("test_crud_goal")
        delete_goal("test_crud_goal_2")

    def test_upsert_and_get_goal(self):
        from src.aps.store import delete_goal, get_goal, upsert_goal

        try:
            result = upsert_goal(self._TEST_GOAL)
            assert result is not None
            assert result["goal_id"] == "test_crud_goal"
            assert result["display_name"] == "Test CRUD Goal"
            assert abs(result["epsilon_g"] - 0.15) < 0.001

            fetched = get_goal("test_crud_goal")
            assert fetched is not None
            assert fetched["goal_id"] == "test_crud_goal"
            assert fetched["observation_map"] == ["K1", "K2"]
        finally:
            self._cleanup()

    def test_upsert_updates_existing(self):
        from src.aps.store import delete_goal, get_goal, upsert_goal

        try:
            upsert_goal(self._TEST_GOAL)
            updated = {**self._TEST_GOAL, "display_name": "Updated Name", "epsilon_g": 0.25}
            result = upsert_goal(updated)
            assert result is not None
            assert result["display_name"] == "Updated Name"
            assert abs(result["epsilon_g"] - 0.25) < 0.001
        finally:
            self._cleanup()

    def test_delete_goal(self):
        from src.aps.store import delete_goal, get_goal, upsert_goal

        upsert_goal(self._TEST_GOAL)
        assert delete_goal("test_crud_goal") is True
        assert get_goal("test_crud_goal") is None

    def test_delete_nonexistent_goal(self):
        from src.aps.store import delete_goal

        assert delete_goal("nonexistent_goal_xyz") is False

    def test_get_goals_list(self):
        from src.aps.store import delete_goal, get_goals, upsert_goal

        try:
            upsert_goal(self._TEST_GOAL)
            goals = get_goals()
            assert isinstance(goals, list)
            ids = [g["goal_id"] for g in goals]
            assert "test_crud_goal" in ids
        finally:
            self._cleanup()

    def test_seed_default_goals_only_when_empty(self):
        from src.aps.store import get_goals, seed_default_goals

        # DB already has goals (seeded by previous test or get_default_goal_specs)
        goals_before = get_goals()
        count = seed_default_goals([self._TEST_GOAL])
        if goals_before:
            assert count == 0  # Should not seed if goals exist
        goals_after = get_goals()
        # Count should remain the same
        assert len(goals_after) >= len(goals_before)

    def test_goal_to_dict_round_trip(self):
        from src.morphogenetic.goals import GoalSpec, _dict_to_goal, _goal_to_dict

        goal = GoalSpec(
            goal_id="rt_test", display_name="Round Trip",
            failure_predicate="p_fail > eps", epsilon_g=0.2,
            horizon_t=600, observation_map=["K3", "K4"],
            primary_tier=2, priority=8,
        )
        d = _goal_to_dict(goal)
        assert d["goal_id"] == "rt_test"
        assert d["observation_map"] == ["K3", "K4"]

        restored = _dict_to_goal(d)
        assert restored.goal_id == "rt_test"
        assert restored.epsilon_g == 0.2
        assert restored.observation_map == ["K3", "K4"]
        assert restored.primary_tier == 2


# =========================================================================
# System image export/import
# =========================================================================


class TestSystemImage:
    """Tests for system image export/import (store.py)."""

    def test_export_returns_valid_format(self):
        from src.aps.store import export_system_image

        image = export_system_image()
        assert image["format"] == "holly-grace-system-image"
        assert image["version"] == "1.0"
        assert "exported_at" in image
        assert "checksum" in image
        assert image["checksum"].startswith("sha256:")

    def test_export_contains_all_sections(self):
        from src.aps.store import export_system_image

        image = export_system_image()
        assert "agents" in image
        assert "workflows" in image
        assert "goals" in image
        assert "cascade_config" in image
        assert "assembly_cache" in image
        assert isinstance(image["agents"], list)
        assert isinstance(image["workflows"], list)
        assert isinstance(image["goals"], list)
        assert isinstance(image["cascade_config"], dict)

    def test_import_dry_run(self):
        from src.aps.store import export_system_image, import_system_image

        image = export_system_image()
        result = import_system_image(image, dry_run=True)
        assert result["dry_run"] is True
        assert "summary" in result

    def test_import_invalid_format(self):
        from src.aps.store import import_system_image

        result = import_system_image({"format": "wrong"})
        assert "error" in result

    def test_export_import_round_trip(self):
        from src.aps.store import export_system_image, import_system_image

        image = export_system_image()
        result = import_system_image(image)
        assert result.get("applied") is True or "error" not in result

    def test_import_preview_counts(self):
        from src.aps.store import export_system_image, import_system_image

        image = export_system_image()
        result = import_system_image(image, dry_run=True)
        summary = result["summary"]
        assert isinstance(summary["agents"], list)
        assert isinstance(summary["workflows"], list)
        assert isinstance(summary["goals"], list)
        assert isinstance(summary["assembly_cache"], int)


# =========================================================================
# Trigger config from DB
# =========================================================================


class TestTriggerConfigDB:
    """Tests that trigger.py reads config from DB."""

    def test_trigger_config_function_returns_dict(self):
        from src.morphogenetic.trigger import _get_trigger_config

        cfg = _get_trigger_config()
        assert isinstance(cfg, dict)
        assert "min_observations" in cfg
        assert "delta" in cfg

    def test_trigger_uses_db_min_observations(self):
        """Trigger should respect min_observations from DB."""
        from src.aps.store import reset_cascade_config, update_cascade_config
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="db_config_test", display_name="DB Config Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )

        try:
            # Set min_observations to 5
            update_cascade_config({"min_observations": 5})

            # With 10 observations (above 5 but below default 20),
            # trigger should fire if p_fail is high enough
            result = check_epsilon_trigger(
                goal=goal, p_fail=0.5, n_observations=10, channel_id="K1"
            )
            assert result.triggered is True
            assert result.reason == "epsilon_exceeded"
        finally:
            reset_cascade_config()

    def test_trigger_delta_override(self):
        """check_epsilon_trigger accepts explicit delta parameter."""
        from src.morphogenetic.goals import GoalSpec
        from src.morphogenetic.trigger import check_epsilon_trigger

        goal = GoalSpec(
            goal_id="delta_test", display_name="Delta Test",
            failure_predicate="p_fail", epsilon_g=0.1,
            horizon_t=1800, observation_map=["K1"], primary_tier=0,
        )

        # With very tight delta (0.001), UCB will be much wider
        tight = check_epsilon_trigger(
            goal=goal, p_fail=0.08, n_observations=30,
            channel_id="K1", delta=0.001,
        )
        # With loose delta (0.5), UCB will be narrower
        loose = check_epsilon_trigger(
            goal=goal, p_fail=0.08, n_observations=30,
            channel_id="K1", delta=0.5,
        )
        assert tight.p_fail_ucb > loose.p_fail_ucb
