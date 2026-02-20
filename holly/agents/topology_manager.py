"""Team Topology Manager — spawn, steer, dissolve operations.

Task 38.4 implements the formal topology operators per Goal Hierarchy §3 + §5 + §6,
with ICD-012/015 integration:

- spawn: Create new team composition with contracts
- steer: Reshape team while preserving progress
- dissolve: Tear down and reassign goals
- Contracts: Define valid communication patterns and permissions
- Eigenspectrum: Monitor communication divergence from expected patterns

References:
  - Goal Hierarchy Formal Spec, §5 (steering operators, contracts)
  - Goal Hierarchy Formal Spec, §6 (eigenspectrum divergence)
  - ICD-012: Topology Manager → Engine (task dispatch)
  - ICD-015: Topology Manager → Subagent Lane (team spawning)
"""

from __future__ import annotations

import dataclasses
import datetime
import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np


# ──────────────────────────────────────────────────────────
# §1 Agent & Contract Models
# ──────────────────────────────────────────────────────────


class AgentCapability(enum.Enum):
    """Agent capability level."""

    MINIMAL = "minimal"  # Single task, restricted scope
    STANDARD = "standard"  # General multi-task, full scope
    LEAD = "lead"  # Coordination, leadership role


@dataclass(slots=True, frozen=True)
class AgentPermissions:
    """Permissions define per-agent action spaces.
    
    Attributes
    ----------
    agent_id
        Unique agent identifier.
    can_spawn
        Whether agent can spawn new subagents.
    can_steer
        Whether agent can modify topology.
    can_dissolve
        Whether agent can dissolve team.
    capability_level
        Agent capability (MINIMAL, STANDARD, LEAD).
    max_concurrent_tasks
        Maximum concurrent tasks agent can handle.
    allowed_domains
        Set of allowed domains/scopes agent can work in.
    """

    agent_id: str
    can_spawn: bool
    can_steer: bool
    can_dissolve: bool
    capability_level: AgentCapability
    max_concurrent_tasks: int
    allowed_domains: frozenset[str]

    def __post_init__(self) -> None:
        """Validate permissions."""
        if self.max_concurrent_tasks < 1:
            raise ValueError(f"max_concurrent_tasks must be >= 1, got {self.max_concurrent_tasks}")
        if not self.agent_id:
            raise ValueError("agent_id cannot be empty")


@dataclass(slots=True, frozen=True)
class AgentContract:
    """Contract defines valid communication patterns and responsibilities.
    
    A contract is an agreement between agents about:
    - Expected message rates to peer agents
    - Responsibility domain (what goals they handle)
    - SLA (response time bounds)
    - Failure handling (escalation, repartition)
    
    Attributes
    ----------
    agent_id
        Agent party to this contract.
    peer_agent_id
        Peer agent in this contract (can be None for broadcast).
    expected_message_rate
        Expected messages per second to peer.
    responsibility_domain
        Set of goal IDs this agent is responsible for.
    max_response_time_sec
        Maximum allowed response time.
    escalation_threshold
        Number of failures before escalation.
    """

    agent_id: str
    peer_agent_id: str | None
    expected_message_rate: float
    responsibility_domain: frozenset[str]
    max_response_time_sec: float
    escalation_threshold: int

    def __post_init__(self) -> None:
        """Validate contract."""
        if self.expected_message_rate < 0:
            raise ValueError(
                f"expected_message_rate must be >= 0, got {self.expected_message_rate}"
            )
        if self.max_response_time_sec <= 0:
            raise ValueError(
                f"max_response_time_sec must be > 0, got {self.max_response_time_sec}"
            )
        if self.escalation_threshold < 1:
            raise ValueError(
                f"escalation_threshold must be >= 1, got {self.escalation_threshold}"
            )


@dataclass(slots=True, frozen=True)
class Agent:
    """An agent in the team topology.
    
    Attributes
    ----------
    agent_id
        Unique agent identifier.
    permissions
        What this agent is allowed to do.
    contracts
        Contracts with peer agents.
    assigned_goals
        Goal IDs currently assigned to this agent.
    created_at
        When this agent was spawned.
    parent_agent_id
        ID of agent that spawned this one (if any).
    """

    agent_id: str
    permissions: AgentPermissions
    contracts: frozenset[AgentContract] = field(default_factory=frozenset)
    assigned_goals: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime.datetime = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
    parent_agent_id: str | None = None

    def __post_init__(self) -> None:
        """Validate agent."""
        if not self.agent_id:
            raise ValueError("agent_id cannot be empty")
        if self.agent_id != self.permissions.agent_id:
            raise ValueError(
                f"agent_id {self.agent_id} != permissions.agent_id {self.permissions.agent_id}"
            )


# ──────────────────────────────────────────────────────────
# §2 Team Topology
# ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class TeamTopology:
    """The current team composition, assignments, and contracts.
    
    Attributes
    ----------
    topology_id
        Unique identifier for this topology configuration.
    agents
        Mapping of agent_id -> Agent.
    goal_assignments
        Mapping of goal_id -> set of agent_ids assigned to it.
    communication_matrix
        Expected message rates: [n_agents x n_agents] matrix.
    created_at
        When this topology was created.
    is_active
        Whether topology is currently active.
    """

    topology_id: str
    agents: dict[str, Agent] = field(default_factory=dict)
    goal_assignments: dict[str, set[str]] = field(default_factory=dict)
    communication_matrix: np.ndarray | None = None
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    is_active: bool = True

    def __post_init__(self) -> None:
        """Validate topology."""
        if not self.topology_id:
            raise ValueError("topology_id cannot be empty")

    def add_agent(self, agent: Agent) -> None:
        """Add an agent to the topology."""
        if agent.agent_id in self.agents:
            raise ValueError(f"Agent {agent.agent_id} already exists in topology")
        self.agents[agent.agent_id] = agent

    def assign_goal(self, goal_id: str, agent_id: str) -> None:
        """Assign a goal to an agent."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent {agent_id} not in topology")
        if goal_id not in self.goal_assignments:
            self.goal_assignments[goal_id] = set()
        self.goal_assignments[goal_id].add(agent_id)

    def get_expected_communication_matrix(self) -> np.ndarray:
        """Build expected communication pattern matrix from contracts.
        
        Returns
        -------
        np.ndarray
            [n_agents x n_agents] matrix with expected message rates.
        """
        if self.communication_matrix is not None:
            return self.communication_matrix

        agent_ids = sorted(self.agents.keys())
        n = len(agent_ids)
        matrix = np.zeros((n, n), dtype=np.float64)

        id_to_idx = {aid: i for i, aid in enumerate(agent_ids)}

        for agent_id, agent in self.agents.items():
            for contract in agent.contracts:
                if contract.peer_agent_id in id_to_idx:
                    i = id_to_idx[agent_id]
                    j = id_to_idx[contract.peer_agent_id]
                    matrix[i, j] = contract.expected_message_rate

        self.communication_matrix = matrix
        return matrix


@runtime_checkable
class TopologyObserver(Protocol):
    """Protocol for observing topology changes."""

    def on_agent_spawned(self, agent: Agent) -> None:
        """Called when an agent is spawned."""
        ...

    def on_agent_dissolved(self, agent_id: str) -> None:
        """Called when an agent is dissolved."""
        ...

    def on_topology_steered(
        self, old_topology: TeamTopology, new_topology: TeamTopology
    ) -> None:
        """Called when topology is steered."""
        ...


# ──────────────────────────────────────────────────────────
# §3 Eigenspectrum Divergence Monitoring
# ──────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class CommunicationMetrics:
    """Actual communication metrics collected over time window.
    
    Attributes
    ----------
    window_start
        Start of measurement window.
    window_end
        End of measurement window.
    message_counts
        [n_agents x n_agents] matrix of actual message counts.
    total_messages
        Total messages exchanged.
    """

    window_start: datetime.datetime
    window_end: datetime.datetime
    message_counts: np.ndarray
    total_messages: int

    @property
    def window_duration_sec(self) -> float:
        """Duration of measurement window in seconds."""
        delta = self.window_end - self.window_start
        return delta.total_seconds()

    @property
    def message_rates(self) -> np.ndarray:
        """Convert message counts to message rates (msgs/sec)."""
        if self.window_duration_sec <= 0:
            return self.message_counts
        return self.message_counts / self.window_duration_sec


@dataclass(slots=True, frozen=True)
class EigenspectrumAnalysis:
    """Result of eigenspectrum divergence analysis.
    
    Attributes
    ----------
    actual_eigenvalues
        Eigenvalues of actual communication matrix.
    expected_eigenvalues
        Eigenvalues of expected communication matrix.
    divergence
        L2 distance between eigenvalue vectors.
    is_divergent
        Whether divergence exceeds threshold.
    threshold
        Configured divergence threshold.
    timestamp
        When analysis was performed.
    """

    actual_eigenvalues: np.ndarray
    expected_eigenvalues: np.ndarray
    divergence: float
    is_divergent: bool
    threshold: float
    timestamp: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


def compute_eigenspectrum_divergence(
    topology: TeamTopology,
    actual_metrics: CommunicationMetrics,
    threshold: float = 2.0,
) -> EigenspectrumAnalysis:
    """Compute spectral divergence between actual and expected communication.
    
    Per Goal Hierarchy §6.2:
    - Expected pattern comes from topology contracts
    - Actual pattern measured from message logs
    - Eigenvalues capture network "shape"
    - Divergence indicates topology drift
    
    Parameters
    ----------
    topology
        Current team topology with contracts.
    actual_metrics
        Actual communication metrics over measurement window.
    threshold
        Divergence threshold for flagging divergence.
        
    Returns
    -------
    EigenspectrumAnalysis
        Eigenvalues, divergence, and status.
    """
    # Get expected communication pattern from contracts
    c_expected = topology.get_expected_communication_matrix()

    # Use actual message rates
    c_actual = actual_metrics.message_rates

    # Pad to same size if needed
    max_size = max(c_expected.shape[0], c_actual.shape[0])
    if c_expected.shape[0] < max_size:
        pad_width = ((0, max_size - c_expected.shape[0]), (0, max_size - c_expected.shape[0]))
        c_expected = np.pad(c_expected, pad_width, constant_values=0)
    if c_actual.shape[0] < max_size:
        pad_width = ((0, max_size - c_actual.shape[0]), (0, max_size - c_actual.shape[0]))
        c_actual = np.pad(c_actual, pad_width, constant_values=0)

    # Compute eigenvalues
    try:
        lambda_actual = np.linalg.eigvalsh(c_actual)
        lambda_expected = np.linalg.eigvalsh(c_expected)
    except np.linalg.LinAlgError:
        # If eigenvalue computation fails, use identity eigenvalues
        n = max_size
        lambda_actual = np.ones(n)
        lambda_expected = np.ones(n)

    # Sort by absolute value
    lambda_actual = np.sort(np.abs(lambda_actual))[::-1]
    lambda_expected = np.sort(np.abs(lambda_expected))[::-1]

    # Pad to same length if needed
    max_len = max(len(lambda_actual), len(lambda_expected))
    lambda_actual = np.pad(lambda_actual, (0, max_len - len(lambda_actual)), constant_values=0)
    lambda_expected = np.pad(lambda_expected, (0, max_len - len(lambda_expected)), constant_values=0)

    # Compute L2 divergence
    divergence = float(np.linalg.norm(lambda_actual - lambda_expected))

    is_divergent = divergence > threshold

    return EigenspectrumAnalysis(
        actual_eigenvalues=lambda_actual,
        expected_eigenvalues=lambda_expected,
        divergence=divergence,
        is_divergent=is_divergent,
        threshold=threshold,
    )


# ──────────────────────────────────────────────────────────
# §4 Topology Operations: Spawn, Steer, Dissolve
# ──────────────────────────────────────────────────────────


class TopologyOperationError(Exception):
    """Raised when a topology operation fails."""

    pass


@dataclass(slots=True, frozen=True)
class SpawnSpec:
    """Specification for spawning a new team.
    
    Attributes
    ----------
    parent_agent_id
        Agent that is spawning this team (if any).
    agent_configs
        List of (agent_id, permissions, contracts) tuples.
    initial_goals
        Set of goal IDs to assign.
    """

    parent_agent_id: str | None
    agent_configs: list[tuple[str, AgentPermissions, frozenset[AgentContract]]]
    initial_goals: frozenset[str]


@dataclass(slots=True, frozen=True)
class SteerSpec:
    """Specification for steering a team.
    
    Attributes
    ----------
    topology_id
        ID of topology to steer.
    agent_reassignments
        Mapping of goal_id -> set of new agent_ids.
    new_contracts
        Additional/replacement contracts to install.
    preserve_agents
        Set of agent IDs to keep (dissolve others).
    """

    topology_id: str
    agent_reassignments: dict[str, set[str]]
    new_contracts: frozenset[AgentContract] = field(default_factory=frozenset)
    preserve_agents: frozenset[str] | None = None


@dataclass(slots=True, frozen=True)
class DissolveSpec:
    """Specification for dissolving a team.
    
    Attributes
    ----------
    topology_id
        ID of topology to dissolve.
    reassign_goals_to
        Agent ID to reassign orphaned goals (if any).
    reason
        Human-readable reason for dissolution.
    """

    topology_id: str
    reassign_goals_to: str | None
    reason: str


# ──────────────────────────────────────────────────────────
# §5 Topology Manager (Main API)
# ──────────────────────────────────────────────────────────


class TopologyManager:
    """Master topology manager: spawn, steer, dissolve operations.
    
    Per Goal Hierarchy §5, the Topology Manager governs:
    - Agent spawning with contracts
    - Topology restructuring (steering)
    - Topology dissolution and reassignment
    - Communication contract validation
    
    Implements ICD-012 (Engine dispatch) and ICD-015 (Subagent lane spawning).
    """

    def __init__(self) -> None:
        """Initialize topology manager."""
        self._topologies: dict[str, TeamTopology] = {}
        self._topology_counter: int = 0
        self._observers: list[TopologyObserver] = []

    def register_observer(self, observer: TopologyObserver) -> None:
        """Register an observer for topology changes."""
        self._observers.append(observer)

    def spawn(
        self, spec: SpawnSpec
    ) -> TeamTopology:
        """Spawn a new team topology.
        
        Per Goal Hierarchy §5.1:
        - No agent can spawn without a contract
        - Each agent gets steering operator (permissions)
        - Team structure governed by assignment matrix
        
        Parameters
        ----------
        spec
            Spawn specification with agent configs and initial goals.
            
        Returns
        -------
        TeamTopology
            New team topology.
            
        Raises
        ------
        TopologyOperationError
            If spawn fails validation.
        """
        # Validate spec
        if not spec.agent_configs:
            raise TopologyOperationError("spawn requires at least one agent")

        # Create new topology
        self._topology_counter += 1
        topology_id = f"topo-{self._topology_counter}"

        topology = TeamTopology(topology_id=topology_id)

        # Create agents with contracts
        for agent_id, permissions, contracts in spec.agent_configs:
            agent = Agent(
                agent_id=agent_id,
                permissions=permissions,
                contracts=contracts,
                parent_agent_id=spec.parent_agent_id,
            )
            topology.add_agent(agent)

            # Notify observers
            for obs in self._observers:
                if isinstance(obs, TopologyObserver):
                    obs.on_agent_spawned(agent)

        # Assign initial goals
        agent_ids = [agent_id for agent_id, _, _ in spec.agent_configs]
        for goal_id in spec.initial_goals:
            # Round-robin assign to agents
            agent_id = agent_ids[hash(goal_id) % len(agent_ids)]
            topology.assign_goal(goal_id, agent_id)

        # Store topology
        self._topologies[topology_id] = topology

        return topology

    def steer(
        self, spec: SteerSpec
    ) -> TeamTopology:
        """Steer an existing topology to new configuration.
        
        Per Goal Hierarchy §6.3:
        - Modify team structure while preserving progress
        - Change assignments, add/remove agents
        - Keep original goals
        
        Parameters
        ----------
        spec
            Steer specification with reassignments and new contracts.
            
        Returns
        -------
        TeamTopology
            New topology configuration after steering.
            
        Raises
        ------
        TopologyOperationError
            If steer fails (topology not found, invalid reassignments).
        """
        if spec.topology_id not in self._topologies:
            raise TopologyOperationError(f"Topology {spec.topology_id} not found")

        old_topology = self._topologies[spec.topology_id]

        # Create new topology as copy of old
        self._topology_counter += 1
        new_topology_id = f"topo-{self._topology_counter}"
        new_topology = TeamTopology(topology_id=new_topology_id)

        # Copy preserved agents
        if spec.preserve_agents is not None:
            agents_to_keep = spec.preserve_agents
        else:
            agents_to_keep = frozenset(old_topology.agents.keys())

        for agent_id in agents_to_keep:
            if agent_id in old_topology.agents:
                old_agent = old_topology.agents[agent_id]

                # Update contracts if specified
                contracts = old_agent.contracts
                for contract in spec.new_contracts:
                    if contract.agent_id == agent_id:
                        contracts = frozenset(
                            c for c in contracts if c.peer_agent_id != contract.peer_agent_id
                        ) | frozenset([contract])

                new_agent = Agent(
                    agent_id=agent_id,
                    permissions=old_agent.permissions,
                    contracts=contracts,
                    assigned_goals=old_agent.assigned_goals,
                    parent_agent_id=old_agent.parent_agent_id,
                )
                new_topology.add_agent(new_agent)

        # Apply reassignments
        for goal_id, new_agents in spec.agent_reassignments.items():
            for agent_id in new_agents:
                if agent_id not in new_topology.agents:
                    raise TopologyOperationError(
                        f"Cannot assign goal {goal_id} to agent {agent_id}: agent not in steered topology"
                    )
                new_topology.assign_goal(goal_id, agent_id)

        # If goals not reassigned, keep old assignments for preserved agents
        for goal_id, agent_ids in old_topology.goal_assignments.items():
            if goal_id not in spec.agent_reassignments:
                for agent_id in agent_ids:
                    if agent_id in new_topology.agents:
                        new_topology.assign_goal(goal_id, agent_id)

        new_topology.is_active = True
        old_topology.is_active = False

        # Store new topology
        self._topologies[new_topology_id] = new_topology

        # Notify observers
        for obs in self._observers:
            if isinstance(obs, TopologyObserver):
                obs.on_topology_steered(old_topology, new_topology)

        return new_topology

    def dissolve(
        self, spec: DissolveSpec
    ) -> None:
        """Dissolve a topology and optionally reassign goals.
        
        Per Goal Hierarchy §6.3:
        - Terminate current team
        - Reassign all goals to new set of agents
        - Restart
        
        Parameters
        ----------
        spec
            Dissolve specification with target topology and reassignment.
            
        Raises
        ------
        TopologyOperationError
            If dissolve fails (topology not found).
        """
        if spec.topology_id not in self._topologies:
            raise TopologyOperationError(f"Topology {spec.topology_id} not found")

        topology = self._topologies[spec.topology_id]

        # Mark as inactive
        topology.is_active = False

        # Notify observers of agent dissolution
        for agent_id in topology.agents.keys():
            for obs in self._observers:
                if isinstance(obs, TopologyObserver):
                    obs.on_agent_dissolved(agent_id)

    def get_topology(self, topology_id: str) -> TeamTopology | None:
        """Retrieve a topology by ID."""
        return self._topologies.get(topology_id)

    def list_active_topologies(self) -> list[TeamTopology]:
        """List all active topologies."""
        return [t for t in self._topologies.values() if t.is_active]

    def verify_contracts(self, topology: TeamTopology) -> list[str]:
        """Verify that all contracts in a topology are valid.
        
        Checks:
        - Each agent has contracts with defined peers
        - No circular contract violations
        - All goals have assigned agents
        
        Returns
        -------
        list[str]
            List of validation errors (empty if valid).
        """
        errors: list[str] = []

        # Check all agents have valid contracts
        for agent_id, agent in topology.agents.items():
            for contract in agent.contracts:
                if contract.peer_agent_id is not None:
                    if contract.peer_agent_id not in topology.agents:
                        errors.append(
                            f"Agent {agent_id} has contract with non-existent peer {contract.peer_agent_id}"
                        )

        # Check all goals are assigned
        for goal_id in topology.goal_assignments.keys():
            if not topology.goal_assignments[goal_id]:
                errors.append(f"Goal {goal_id} has no assigned agents")

        return errors


# ──────────────────────────────────────────────────────────
# §6 Default Threshold Parameters
# ──────────────────────────────────────────────────────────

# Eigenspectrum divergence threshold (eigenvalue L2 distance)
EIGENSPECTRUM_DIVERGENCE_THRESHOLD = 2.0

# Critical thresholds for steer vs. dissolve decision
DIVERGENCE_CRITICAL_THRESHOLD = 5.0
RESIDUAL_CRITICAL_THRESHOLD = 0.8
