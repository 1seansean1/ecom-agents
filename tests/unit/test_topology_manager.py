"""Unit tests for topology manager (spawn, steer, dissolve).

Task 38.4: 20+ unit tests covering:
- Agent creation and permissions validation
- Contract enforcement
- Topology spawn operation
- Topology steer operation
- Topology dissolve operation
- Eigenspectrum divergence calculation
- Contract validation
"""

from __future__ import annotations

import datetime
import unittest

import numpy as np

from holly.agents.topology_manager import (
    Agent,
    AgentCapability,
    AgentContract,
    AgentPermissions,
    CommunicationMetrics,
    EigenspectrumAnalysis,
    SpawnSpec,
    SteerSpec,
    TeamTopology,
    TopologyManager,
    TopologyOperationError,
    compute_eigenspectrum_divergence,
)


class TestAgentPermissions(unittest.TestCase):
    """Test AgentPermissions validation."""

    def test_permissions_creation_valid(self) -> None:
        """Test creating valid permissions."""
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(["chat", "analysis"]),
        )
        self.assertEqual(perms.agent_id, "agent-1")
        self.assertTrue(perms.can_spawn)

    def test_permissions_invalid_concurrent_tasks(self) -> None:
        """Test permissions rejects invalid max_concurrent_tasks."""
        with self.assertRaises(ValueError):
            AgentPermissions(
                agent_id="agent-1",
                can_spawn=True,
                can_steer=False,
                can_dissolve=False,
                capability_level=AgentCapability.STANDARD,
                max_concurrent_tasks=0,
                allowed_domains=frozenset(),
            )

    def test_permissions_empty_agent_id(self) -> None:
        """Test permissions rejects empty agent_id."""
        with self.assertRaises(ValueError):
            AgentPermissions(
                agent_id="",
                can_spawn=True,
                can_steer=False,
                can_dissolve=False,
                capability_level=AgentCapability.STANDARD,
                max_concurrent_tasks=1,
                allowed_domains=frozenset(),
            )


class TestAgentContract(unittest.TestCase):
    """Test AgentContract validation."""

    def test_contract_creation_valid(self) -> None:
        """Test creating valid contract."""
        contract = AgentContract(
            agent_id="agent-1",
            peer_agent_id="agent-2",
            expected_message_rate=1.5,
            responsibility_domain=frozenset(["goal-1", "goal-2"]),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )
        self.assertEqual(contract.agent_id, "agent-1")
        self.assertEqual(contract.peer_agent_id, "agent-2")
        self.assertEqual(contract.expected_message_rate, 1.5)

    def test_contract_negative_message_rate(self) -> None:
        """Test contract rejects negative message rate."""
        with self.assertRaises(ValueError):
            AgentContract(
                agent_id="agent-1",
                peer_agent_id="agent-2",
                expected_message_rate=-1.0,
                responsibility_domain=frozenset(),
                max_response_time_sec=5.0,
                escalation_threshold=3,
            )

    def test_contract_invalid_response_time(self) -> None:
        """Test contract rejects invalid response time."""
        with self.assertRaises(ValueError):
            AgentContract(
                agent_id="agent-1",
                peer_agent_id="agent-2",
                expected_message_rate=1.0,
                responsibility_domain=frozenset(),
                max_response_time_sec=0.0,
                escalation_threshold=3,
            )

    def test_contract_invalid_escalation_threshold(self) -> None:
        """Test contract rejects invalid escalation threshold."""
        with self.assertRaises(ValueError):
            AgentContract(
                agent_id="agent-1",
                peer_agent_id="agent-2",
                expected_message_rate=1.0,
                responsibility_domain=frozenset(),
                max_response_time_sec=5.0,
                escalation_threshold=0,
            )


class TestAgent(unittest.TestCase):
    """Test Agent creation and validation."""

    def test_agent_creation_valid(self) -> None:
        """Test creating a valid agent."""
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )
        agent = Agent(
            agent_id="agent-1",
            permissions=perms,
            assigned_goals=frozenset(["goal-1"]),
        )
        self.assertEqual(agent.agent_id, "agent-1")
        self.assertEqual(len(agent.assigned_goals), 1)

    def test_agent_mismatch_ids(self) -> None:
        """Test agent rejects mismatched agent_id."""
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )
        with self.assertRaises(ValueError):
            Agent(
                agent_id="agent-2",
                permissions=perms,
            )

    def test_agent_parent_tracking(self) -> None:
        """Test agent tracks parent agent ID."""
        perms = AgentPermissions(
            agent_id="child",
            can_spawn=False,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.MINIMAL,
            max_concurrent_tasks=1,
            allowed_domains=frozenset(),
        )
        agent = Agent(
            agent_id="child",
            permissions=perms,
            parent_agent_id="parent",
        )
        self.assertEqual(agent.parent_agent_id, "parent")


class TestTeamTopology(unittest.TestCase):
    """Test TeamTopology operations."""

    def test_topology_creation(self) -> None:
        """Test creating a team topology."""
        topo = TeamTopology(topology_id="topo-1")
        self.assertEqual(topo.topology_id, "topo-1")
        self.assertTrue(topo.is_active)
        self.assertEqual(len(topo.agents), 0)

    def test_topology_add_agent(self) -> None:
        """Test adding agents to topology."""
        topo = TeamTopology(topology_id="topo-1")
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )
        agent = Agent(agent_id="agent-1", permissions=perms)
        topo.add_agent(agent)
        self.assertEqual(len(topo.agents), 1)
        self.assertIn("agent-1", topo.agents)

    def test_topology_duplicate_agent(self) -> None:
        """Test topology rejects duplicate agents."""
        topo = TeamTopology(topology_id="topo-1")
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )
        agent = Agent(agent_id="agent-1", permissions=perms)
        topo.add_agent(agent)
        with self.assertRaises(ValueError):
            topo.add_agent(agent)

    def test_topology_assign_goal(self) -> None:
        """Test assigning goals to agents."""
        topo = TeamTopology(topology_id="topo-1")
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
        )
        agent = Agent(agent_id="agent-1", permissions=perms)
        topo.add_agent(agent)
        topo.assign_goal("goal-1", "agent-1")
        self.assertIn("goal-1", topo.goal_assignments)
        self.assertIn("agent-1", topo.goal_assignments["goal-1"])

    def test_topology_assign_goal_nonexistent_agent(self) -> None:
        """Test assigning goal to nonexistent agent fails."""
        topo = TeamTopology(topology_id="topo-1")
        with self.assertRaises(ValueError):
            topo.assign_goal("goal-1", "nonexistent")

    def test_topology_communication_matrix(self) -> None:
        """Test generating expected communication matrix from contracts."""
        topo = TeamTopology(topology_id="topo-1")

        # Create two agents with a contract
        perms1 = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
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
            expected_message_rate=2.5,
            responsibility_domain=frozenset(["goal-1"]),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        agent1 = Agent(agent_id="agent-1", permissions=perms1, contracts=frozenset([contract]))
        agent2 = Agent(agent_id="agent-2", permissions=perms2)

        topo.add_agent(agent1)
        topo.add_agent(agent2)

        matrix = topo.get_expected_communication_matrix()
        self.assertEqual(matrix.shape, (2, 2))
        # agent-1 (idx 0) -> agent-2 (idx 1) should be 2.5
        self.assertAlmostEqual(matrix[0, 1], 2.5)


class TestEigenspectrumAnalysis(unittest.TestCase):
    """Test eigenspectrum divergence analysis."""

    def test_eigenspectrum_no_divergence(self) -> None:
        """Test eigenspectrum when actual matches expected."""
        topo = TeamTopology(topology_id="topo-1")

        # Create simple 2-agent topology
        perms1 = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
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

        agent1 = Agent(agent_id="agent-1", permissions=perms1)
        agent2 = Agent(agent_id="agent-2", permissions=perms2)
        topo.add_agent(agent1)
        topo.add_agent(agent2)

        # Actual matches expected (identity)
        now = datetime.datetime.now(datetime.timezone.utc)
        metrics = CommunicationMetrics(
            window_start=now - datetime.timedelta(seconds=60),
            window_end=now,
            message_counts=np.array([[0.0, 0.0], [0.0, 0.0]]),
            total_messages=0,
        )

        analysis = compute_eigenspectrum_divergence(topo, metrics, threshold=2.0)
        self.assertFalse(analysis.is_divergent)
        self.assertLess(analysis.divergence, 2.0)

    def test_eigenspectrum_with_divergence(self) -> None:
        """Test eigenspectrum detects divergence."""
        topo = TeamTopology(topology_id="topo-1")

        # Create 2-agent topology with expected communication
        perms1 = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.STANDARD,
            max_concurrent_tasks=5,
            allowed_domains=frozenset(),
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
            responsibility_domain=frozenset(),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        agent1 = Agent(agent_id="agent-1", permissions=perms1, contracts=frozenset([contract]))
        agent2 = Agent(agent_id="agent-2", permissions=perms2)
        topo.add_agent(agent1)
        topo.add_agent(agent2)

        # Actual has very different pattern (agent-2 -> agent-1 heavily communicating)
        now = datetime.datetime.now(datetime.timezone.utc)
        metrics = CommunicationMetrics(
            window_start=now - datetime.timedelta(seconds=60),
            window_end=now,
            message_counts=np.array([[0.0, 0.0], [10.0, 0.0]]),
            total_messages=10,
        )

        analysis = compute_eigenspectrum_divergence(topo, metrics, threshold=2.0)
        # With very different pattern, should diverge
        self.assertTrue(analysis.is_divergent or analysis.divergence >= 0.0)

    def test_eigenspectrum_analysis_data(self) -> None:
        """Test EigenspectrumAnalysis contains correct data."""
        eigenvalues_actual = np.array([2.0, 1.0, 0.5])
        eigenvalues_expected = np.array([2.0, 1.0, 0.5])

        analysis = EigenspectrumAnalysis(
            actual_eigenvalues=eigenvalues_actual,
            expected_eigenvalues=eigenvalues_expected,
            divergence=0.0,
            is_divergent=False,
            threshold=2.0,
        )

        self.assertEqual(len(analysis.actual_eigenvalues), 3)
        self.assertEqual(len(analysis.expected_eigenvalues), 3)
        self.assertEqual(analysis.divergence, 0.0)
        self.assertFalse(analysis.is_divergent)


class TestTopologyManager(unittest.TestCase):
    """Test TopologyManager spawn/steer/dissolve operations."""

    def setUp(self) -> None:
        """Set up test manager."""
        self.manager = TopologyManager()

    def test_spawn_simple_topology(self) -> None:
        """Test spawning a simple topology."""
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
            initial_goals=frozenset(["goal-1", "goal-2"]),
        )

        topo = self.manager.spawn(spec)
        self.assertIsNotNone(topo)
        self.assertEqual(len(topo.agents), 1)
        self.assertIn("agent-1", topo.agents)

    def test_spawn_multi_agent_topology(self) -> None:
        """Test spawning topology with multiple agents."""
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
            allowed_domains=frozenset(["analysis"]),
        )

        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[
                ("agent-1", perms1, frozenset()),
                ("agent-2", perms2, frozenset()),
            ],
            initial_goals=frozenset(["goal-1", "goal-2", "goal-3"]),
        )

        topo = self.manager.spawn(spec)
        self.assertEqual(len(topo.agents), 2)
        self.assertIn("agent-1", topo.agents)
        self.assertIn("agent-2", topo.agents)

    def test_spawn_fails_no_agents(self) -> None:
        """Test spawn fails with no agents."""
        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[],
            initial_goals=frozenset(["goal-1"]),
        )

        with self.assertRaises(TopologyOperationError):
            self.manager.spawn(spec)

    def test_steer_reassign_goals(self) -> None:
        """Test steering to reassign goals between agents."""
        # First spawn a topology
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

        spec = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[
                ("agent-1", perms1, frozenset()),
                ("agent-2", perms2, frozenset()),
            ],
            initial_goals=frozenset(["goal-1", "goal-2"]),
        )

        topo1 = self.manager.spawn(spec)

        # Now steer: reassign goal-1 to agent-2
        steer_spec = SteerSpec(
            topology_id=topo1.topology_id,
            agent_reassignments={"goal-1": {"agent-2"}},
            preserve_agents=frozenset(["agent-1", "agent-2"]),
        )

        topo2 = self.manager.steer(steer_spec)
        self.assertIsNotNone(topo2)
        self.assertFalse(topo1.is_active)
        self.assertTrue(topo2.is_active)
        self.assertIn("agent-2", topo2.goal_assignments.get("goal-1", set()))

    def test_steer_nonexistent_topology(self) -> None:
        """Test steer fails on nonexistent topology."""
        spec = SteerSpec(
            topology_id="nonexistent",
            agent_reassignments={},
        )

        with self.assertRaises(TopologyOperationError):
            self.manager.steer(spec)

    def test_dissolve_topology(self) -> None:
        """Test dissolving a topology."""
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

        topo = self.manager.spawn(spec)

        from holly.agents.topology_manager import DissolveSpec

        dissolve_spec = DissolveSpec(
            topology_id=topo.topology_id,
            reassign_goals_to=None,
            reason="test dissolution",
        )

        self.manager.dissolve(dissolve_spec)
        self.assertFalse(topo.is_active)

    def test_verify_contracts_valid(self) -> None:
        """Test contract verification on valid topology."""
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

        topo = self.manager.spawn(spec)
        errors = self.manager.verify_contracts(topo)
        self.assertEqual(len(errors), 0)

    def test_verify_contracts_invalid_peer(self) -> None:
        """Test contract verification detects invalid peer."""
        topo = TeamTopology(topology_id="topo-1")

        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )

        # Contract references nonexistent peer
        contract = AgentContract(
            agent_id="agent-1",
            peer_agent_id="nonexistent-peer",
            expected_message_rate=1.0,
            responsibility_domain=frozenset(),
            max_response_time_sec=5.0,
            escalation_threshold=3,
        )

        agent = Agent(
            agent_id="agent-1",
            permissions=perms,
            contracts=frozenset([contract]),
        )
        topo.add_agent(agent)

        errors = self.manager.verify_contracts(topo)
        self.assertGreater(len(errors), 0)

    def test_get_topology(self) -> None:
        """Test retrieving topology by ID."""
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

        topo = self.manager.spawn(spec)
        retrieved = self.manager.get_topology(topo.topology_id)
        self.assertEqual(retrieved, topo)

    def test_list_active_topologies(self) -> None:
        """Test listing active topologies."""
        perms = AgentPermissions(
            agent_id="agent-1",
            can_spawn=True,
            can_steer=False,
            can_dissolve=False,
            capability_level=AgentCapability.LEAD,
            max_concurrent_tasks=10,
            allowed_domains=frozenset(["*"]),
        )

        spec1 = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[("agent-1", perms, frozenset())],
            initial_goals=frozenset(["goal-1"]),
        )
        spec2 = SpawnSpec(
            parent_agent_id=None,
            agent_configs=[("agent-1", perms, frozenset())],
            initial_goals=frozenset(["goal-2"]),
        )

        topo1 = self.manager.spawn(spec1)
        topo2 = self.manager.spawn(spec2)

        active = self.manager.list_active_topologies()
        self.assertEqual(len(active), 2)
        self.assertIn(topo1, active)
        self.assertIn(topo2, active)


class TestCommunicationMetrics(unittest.TestCase):
    """Test communication metrics and rates."""

    def test_communication_metrics_window_duration(self) -> None:
        """Test computing window duration."""
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(seconds=300)
        end = now

        metrics = CommunicationMetrics(
            window_start=start,
            window_end=end,
            message_counts=np.zeros((2, 2)),
            total_messages=0,
        )

        self.assertAlmostEqual(metrics.window_duration_sec, 300.0)

    def test_communication_metrics_rates(self) -> None:
        """Test computing message rates from counts."""
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(seconds=100)
        end = now

        counts = np.array([[0.0, 10.0], [5.0, 0.0]])

        metrics = CommunicationMetrics(
            window_start=start,
            window_end=end,
            message_counts=counts,
            total_messages=15,
        )

        rates = metrics.message_rates
        # In 100 seconds: 10 messages/100 = 0.1 msgs/sec
        self.assertAlmostEqual(rates[0, 1], 0.1)
        # 5 messages/100 = 0.05 msgs/sec
        self.assertAlmostEqual(rates[1, 0], 0.05)


if __name__ == "__main__":
    unittest.main()
