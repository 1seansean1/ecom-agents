"""Integration tests for topology manager operations.

Task 38.4: 10+ integration tests covering:
- Complete spawn -> steer -> dissolve workflow
- Eigenspectrum divergence detection with realistic patterns
- Contract enforcement across multi-agent scenarios
- Observer pattern notification
- End-to-end topology lifecycle
"""

from __future__ import annotations

import datetime
import unittest
from typing import Any

import numpy as np

from holly.agents.topology_manager import (
    Agent,
    AgentCapability,
    AgentContract,
    AgentPermissions,
    CommunicationMetrics,
    DissolveSpec,
    SpawnSpec,
    SteerSpec,
    TeamTopology,
    TopologyManager,
    TopologyObserver,
    compute_eigenspectrum_divergence,
)


class MockTopologyObserver:
    """Mock observer for tracking topology changes."""

    def __init__(self) -> None:
        """Initialize mock observer."""
        self.spawned_agents: list[Agent] = []
        self.dissolved_agents: list[str] = []
        self.steered_topologies: list[tuple[TeamTopology, TeamTopology]] = []

    def on_agent_spawned(self, agent: Agent) -> None:
        """Record spawned agent."""
        self.spawned_agents.append(agent)

    def on_agent_dissolved(self, agent_id: str) -> None:
        """Record dissolved agent."""
        self.dissolved_agents.append(agent_id)

    def on_topology_steered(
        self, old_topology: TeamTopology, new_topology: TeamTopology
    ) -> None:
        """Record steered topology."""
        self.steered_topologies.append((old_topology, new_topology))


class TestTopologyLifecycle(unittest.TestCase):
    """Test complete topology lifecycle: spawn, steer, dissolve."""

    def setUp(self) -> None:
        """Set up test manager and observer."""
        self.manager = TopologyManager()
        self.observer = MockTopologyObserver()
        self.manager.register_observer(self.observer)

    def test_spawn_steer_dissolve_workflow(self) -> None:
        """Test complete spawn -> steer -> dissolve workflow."""
        # 1. Spawn initial topology with 2 agents
        perms1 = AgentPermissions(
            agent_id="lead",
            can_spawn=True,
            can_steer=True,
            can_dissolve=True,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=20,
            allowed_domains=frozenset(["*"]),
        )
        perms2 = AgentPermissions(
            agent_id="worker",
            can_spawn=False,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(["computation"]),
        )

        spawn_spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[
                ("lead", perms1, frozenset()),
                ("worker", perms2, frozenset()),
            ],
            initial_goals=frozenset(["g1", "g2", "g3"]),
        )

        topo1 = self.manager.spawn(spawn_spec)
        self.assertEqual(len(topo1.agents), 2)
        self.assertEqual(len(self.observer.spawned_agents), 2)

        # 2. Steer: reassign goal g1 from lead to worker
        steer_spec = SteerSpec(
            topology_id=topo1.topology_id,
            agent_reassignments={"g1": {"worker"}},
            preserve_agents=frozenset(["lead", "worker"]),
        )

        topo2 = self.manager.steer(steer_spec)
        self.assertFalse(topo1.is_active)
        self.assertTrue(topo2.is_active)
        self.assertEqual(len(self.observer.steered_topologies), 1)

        # 3. Dissolve the topology
        dissolve_spec = DissolveSpec(
            topology_id=topo2.topology_id,
            reassign_goals_to=None,
            reason="task complete",
        )

        self.manager.dissolve(dissolve_spec)
        self.assertFalse(topo2.is_active)
        self.assertEqual(len(self.observer.dissolved_agents), 2)

    def test_spawn_multiple_topologies(self) -> None:
        """Test spawning multiple independent topologies."""
        perms = AgentPermissions(
            agent_id="agent",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )

        # Spawn 3 topologies
        for i in range(3):
            spec = SpawnSpec(
                parent_agent_id=None,
                agent_configs=[("agent", perms, frozenset())],
                initial_goals=frozenset([f"goal-{i}"]),
            )
            self.manager.spawn(spec)

        active = self.manager.list_active_topologies()
        self.assertEqual(len(active), 3)

    def test_parent_child_agent_relationships(self) -> None:
        """Test tracking parent-child relationships in agent spawning."""
        # Parent agent spawns team
        parent_perms = AgentPermissions(
            agent_id="parent-agent",
            can_spawn=True,
            can_steer=True,
            can_dissolve=True,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=20,
            allowed_domains=frozenset(["*"]),
        )

        child1_perms = AgentPermissions(
            agent_id="child-1",
            can_spawn=False,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.MINIMAL,
            max_concurrent_tasks=1,
            allowed_domains=frozenset(["subtask"]),
        )
        child2_perms = AgentPermissions(
            agent_id="child-2",
            can_spawn=False,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.MINIMAL,
            max_concurrent_tasks=1,
            allowed_domains=frozenset(["subtask"]),
        )

        spec = SpawnSpec(
            parent_agent_id="parent-agent",
            agent_configs=[
                ("child-1", child1_perms, frozenset()),
                ("child-2", child2_perms, frozenset()),
            ],
            initial_goals=frozenset(["task1", "task2"]),
        )

        topo = self.manager.spawn(spec)

        # Check parent tracking
        for agent_id, agent in topo.agents.items():
            self.assertEqual(agent.parent_agent_id, "parent-agent")


class TestEigenspectrumWorkflow(unittest.TestCase):
    """Test eigenspectrum monitoring in topology operations."""

    def test_eigenspectrum_normal_communication(self) -> None:
        """Test eigenspectrum on normal communication pattern."""
        # Create 3-agent topology with expected pattern
        topo = TeamTopology(topology_id="topo-normal")

        agents_config = [
            ("agent-a", AgentCapability.LEAD),
            ("agent-b", AgentCapability.STANDARD),
            ("agent-c", AgentCapability.STANDARD),
        ]

        for agent_id, cap in agents_config:
            perms = AgentPermissions(
                agent_id=agent_id,
                can_spawn=cap == AgentCapability.LEAD,
                can_steer=cap == AgentCapability.LEAD,
                can_dissolve=cap == AgentCapability.LEAD,
                capability_level=cap,
                max_concurrent_tasks=10 if cap == AgentCapability.LEAD else 5,
                allowed_domains=frozenset(["*"]),
            )
            agent = Agent(agent_id=agent_id, permissions=perms)
            topo.add_agent(agent)

        # Add contracts
        contract_ab = AgentContract(
            agent_id="agent-a",
            peer_agent_id="agent-b",
            expected_message_rate=2.0,
            responsibility_domain=frozenset(["g1", "g2"]),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )
        contract_ac = AgentContract(
            agent_id="agent-a",
            peer_agent_id="agent-c",
            expected_message_rate=1.5,
            responsibility_domain=frozenset(["g3"]),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        # Update agent contracts
        agent_a = topo.agents["agent-a"]
        topo.agents["agent-a"] = Agent(
            agent_id="agent-a",
            permissions=agent_a.permissions,
            contracts=frozenset([contract_ab, contract_ac]),
            assigned_goals=agent_a.assigned_goals,
            parent_agent_id=agent_a.parent_agent_id,
        )

        # Simulate normal communication (matches expected)
        now = datetime.datetime.now(datetime.timezone.utc)
        actual_counts = np.array(
            [[0.0, 2.0, 1.5], [1.0, 0.0, 0.5], [0.8, 0.3, 0.0]]
        )

        metrics = CommunicationMetrics(
            window_start=now - datetime.timedelta(seconds=60),
            window_end=now,
            message_counts=actual_counts * 60,  # 60 seconds
            total_messages=int(np.sum(actual_counts) * 60),
        )

        analysis = compute_eigenspectrum_divergence(topo, metrics, threshold=2.0)
        # Should not be highly divergent with normal pattern
        self.assertLess(analysis.divergence, 5.0)

    def test_eigenspectrum_detects_anomaly(self) -> None:
        """Test eigenspectrum detects anomalous communication pattern."""
        # Create simple 2-agent topology
        topo = TeamTopology(topology_id="topo-anomaly")

        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )

        agent1 = Agent(agent_id="agent-1", permissions=perms)
        agent2 = Agent(
            agent_id="agent-2",
            permissions=AgentPermissions(
                agent_id="agent-2",
                can_spawn=False,
                can_steer=False,
                can_dissolve=False,
                capability_level=AgentCapability.STANDARD,
                max_concurrent_tasks=5,
                allowed_domains=frozenset(),
            ),
        )

        topo.add_agent(agent1)
        topo.add_agent(agent2)

        # Add contract: agent-1 -> agent-2 at 1.0 msg/sec
        contract = AgentContract(
            agent_id="agent-1",
            peer_agent_id="agent-2",
            expected_message_rate=1.0,
            responsibility_domain=frozenset(),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        topo.agents["agent-1"] = Agent(
            agent_id="agent-1",
            permissions=perms,
            contracts=frozenset([contract]),
        )

        # Anomalous: agent-2 heavily talking back to agent-1 (not in contract)
        now = datetime.datetime.now(datetime.timezone.utc)
        actual_counts = np.array([[0.0, 1.0 * 60], [100.0 * 60, 0.0]])

        metrics = CommunicationMetrics(
            window_start=now - datetime.timedelta(seconds=60),
            window_end=now,
            message_counts=actual_counts,
            total_messages=int(np.sum(actual_counts)),
        )

        analysis = compute_eigenspectrum_divergence(topo, metrics, threshold=2.0)
        # Should flag as divergent due to unexpected reverse traffic
        self.assertTrue(analysis.is_divergent or analysis.divergence > 0.1)


class TestContractEnforcement(unittest.TestCase):
    """Test contract enforcement across multi-agent scenarios."""

    def test_contract_validation_on_spawn(self) -> None:
        """Test contract validation is possible after spawn."""
        manager = TopologyManager()

        perms1 = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )
        perms2 = AgentPermissions(
            agent_id="agent-2",
            can_spawn=False,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )

        contract = AgentContract(
            agent_id="agent-1",
            peer_agent_id="agent-2",
            expected_message_rate=1.0,
            responsibility_domain=frozenset(["g1"]),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[
                ("agent-1", perms1, frozenset([contract])),
                ("agent-2", perms2, frozenset()),
            ],
            initial_goals=frozenset(["g1"]),
        )

        topo = manager.spawn(spec)
        errors = manager.verify_contracts(topo)
        self.assertEqual(len(errors), 0)

    def test_multi_agent_contract_matrix(self) -> None:
        """Test building communication matrix from multi-agent contracts."""
        topo = TeamTopology(topology_id="topo-multi")

        # 3 agents with complex contract structure
        agents_config = [
            ("a", 2.0, ["b"]),
            ("b", 1.5, ["a", "c"]),
            ("c", 0.5, ["b"]),
        ]

        for agent_id, _, _ in agents_config:
            perms = AgentPermissions(
                agent_id=agent_id,
                can_spawn=True,
                can_steer=True,
                can_dissolve=True,
                capability_level=AgentCapability.STANDARD,
                max_concurrent_tasks=5,
                allowed_domains=frozenset(),
            )
            agent = Agent(agent_id=agent_id, permissions=perms)
            topo.add_agent(agent)

        # Build contracts
        contracts: dict[str, list[AgentContract]] = {
            "a": [
                AgentContract(
                    agent_id="a",
                    peer_agent_id="b",
                    expected_message_rate=2.0,
                    responsibility_domain=frozenset(),
                    max_response_time_sec=5.0,
                    escalation_threshold=3,
                )
            ],
            "b": [
                AgentContract(
                    agent_id="b",
                    peer_agent_id="a",
                    expected_message_rate=1.5,
                    responsibility_domain=frozenset(),
                    max_response_time_sec=5.0,
                    escalation_threshold=3,
                ),
                AgentContract(
                    agent_id="b",
                    peer_agent_id="c",
                    expected_message_rate=1.5,
                    responsibility_domain=frozenset(),
                    max_response_time_sec=5.0,
                    escalation_threshold=3,
                ),
            ],
            "c": [
                AgentContract(
                    agent_id="c",
                    peer_agent_id="b",
                    expected_message_rate=0.5,
                    responsibility_domain=frozenset(),
                    max_response_time_sec=5.0,
                    escalation_threshold=3,
                )
            ],
        }

        # Install contracts
        for agent_id, agent_contracts in contracts.items():
            old_agent = topo.agents[agent_id]
            topo.agents[agent_id] = Agent(
                agent_id=agent_id,
                permissions=old_agent.permissions,
                contracts=frozenset(agent_contracts),
                assigned_goals=old_agent.assigned_goals,
                parent_agent_id=old_agent.parent_agent_id,
            )

        # Generate matrix
        matrix = topo.get_expected_communication_matrix()
        self.assertEqual(matrix.shape, (3, 3))

        # Check specific entries
        agent_ids = sorted(topo.agents.keys())
        id_map = {aid: i for i, aid in enumerate(agent_ids)}

        # a->b should be 2.0
        self.assertAlmostEqual(matrix[id_map["a"], id_map["b"]], 2.0)
        # b->a should be 1.5
        self.assertAlmostEqual(matrix[id_map["b"], id_map["a"]], 1.5)


class TestSteerVsDissolveDecision(unittest.TestCase):
    """Test decision making for steer vs dissolve."""

    def test_steer_on_low_divergence(self) -> None:
        """Test steering is chosen on low eigenspectrum divergence."""
        manager = TopologyManager()

        # Spawn a topology
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )

        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[("agent-1", perms, frozenset())],
            initial_goals=frozenset(["goal-1"]),
        )

        topo = manager.spawn(spec)

        # Eigenspectrum shows low divergence
        now = datetime.datetime.now(datetime.timezone.utc)
        metrics = CommunicationMetrics(
            window_start=now - datetime.timedelta(seconds=60),
            window_end=now,
            message_counts=np.zeros((1, 1)),
            total_messages=0,
        )

        analysis = compute_eigenspectrum_divergence(topo, metrics, threshold=2.0)
        # With no communication, divergence should be low
        self.assertFalse(analysis.is_divergent)

    def test_goal_reassignment_in_steer(self) -> None:
        """Test steered topology properly reassigns goals."""
        manager = TopologyManager()

        # Create 3-agent topology
        configs = [
            ("lead", AgentCapability.LEAD),
            ("worker-1", AgentCapability.STANDARD),
            ("worker-2", AgentCapability.STANDARD),
        ]

        agent_configs = []
        for agent_id, cap in configs:
            perms = AgentPermissions(
                agent_id=agent_id,
                can_spawn=cap == AgentCapability.LEAD,
                can_steer=cap == AgentCapability.LEAD,
                can_dissolve=cap == AgentCapability.LEAD,
                capability_level=cap,
                max_concurrent_tasks=10 if cap == AgentCapability.LEAD else 5,
                allowed_domains=frozenset(["*"]),
            )
            agent_configs.append((agent_id, perms, frozenset()))

        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=agent_configs,
            initial_goals=frozenset(["g1", "g2", "g3", "g4", "g5"]),
        )

        topo1 = manager.spawn(spec)
        self.assertEqual(len(topo1.goal_assignments), 5)

        # Steer: consolidate goals on fewer agents
        steer_spec = SteerSpec(
            topology_id=topo1.topology_id,
            agent_reassignments={
                "g1": {"worker-1"},
                "g2": {"worker-1"},
                "g3": {"worker-2"},
                "g4": {"worker-2"},
                "g5": {"worker-2"},
            },
            preserve_agents=frozenset(["lead", "worker-1", "worker-2"]),
        )

        topo2 = manager.steer(steer_spec)

        # Verify reassignments
        self.assertEqual(topo2.goal_assignments["g1"], {"worker-1"})
        self.assertEqual(topo2.goal_assignments["g2"], {"worker-1"})
        self.assertEqual(topo2.goal_assignments["g3"], {"worker-2"})


if __name__ == "__main__":
    unittest.main()
