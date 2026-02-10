# Morphogenetic Agency (v5)
## Failure‑Triggered Multiscale Active Inference with Assembly‑Cached Competencies

**One‑line compression:** *Feasibility‑constrained, CP‑profiled multiscale active inference with assembly‑cached competencies.*

---

## Abstract

This document gives a **measurement‑first** synthesis of six ideas: **Assembly Theory** (construction cost with reuse), **Cognitive Light Cones** (goal reach), **Causal Emergence** (which scales have causal grip), **Markov blankets** (agent boundaries), **active inference** (goal‑directed dynamics + exploration), and **Informational Monism** (how partitions become measurable symbols with capacities and costs). The central claim is a design pattern: **agents grow by failing**. A goal is treated as an **attractor basin** at a causally relevant, operationally feasible scale. When empirical goal failure exceeds tolerance, the agent enters a **structured morphogenetic search** (APS) that escalates from parameter tuning, to partition/goal retargeting, to boundary (blanket) expansion, to multiscale re‑organization — ordered by assembly cost because each successive tier modifies progressively more of the agent's substrate. Successful solutions are **cached as reusable subassemblies** (modules/priors/codebooks/blanket levels), with cached competencies ordered from parameter‑level (sensitization, habituation) through partition‑level (associative learning) to substrate‑level (anatomical homeostasis). The engineered analogue of Assembly Theory's "copy number" is **reuse frequency** of cached subassemblies. Over development, the framework predicts stepwise growth in the agent's feasible goal set (CLC expansion), broadening of causal contribution across scales (CE 2.0 profile), and rising informational efficiency **η = C(P)/W**. The last section specifies an instrumentation suite sufficient to falsify the bridge hypotheses that connect these frameworks.

---

## Scope and stance

This is not a claim that cells literally compute free‑energy gradients. It is:

- **Descriptive** for biology: Markov‑blanket/active‑inference language is a redescription that is useful when it yields testable predictions or engineering control handles.
- **Prescriptive** for engineered agents: we can explicitly build systems that minimize (expected) free energy and implement the exploration cascade described here.

The word **morphogenetic** is used deliberately: the framework treats agent development as analogous to biological morphogenesis — goal‑directed construction of form under resource constraints, where "form" includes computational architecture, interface structure, and compositional hierarchy, not only physical shape. The planaria results in Proposition 3 are not mere analogy; they are a biological instance of the same abstract pattern (failure‑triggered basin switching in a multistable attractor landscape) that the framework prescribes for engineered systems.

---

## Claim stack (what the argument must deliver)

1. **Bounded feasibility:** Structural resources constrain what kinds of goal horizons, observation complexities, and tolerances are feasible.
2. **Scale relevance:** Only some coarse‑grainings are operationally realizable by the agent; among those, causal contribution is distributed across scales.
3. **Goals as basins:** Goal specifications correspond to attractor basins at causally relevant scales.
4. **Boundaries matter:** Markov blankets define what partitions and interventions are feasible at each scale.
5. **Failure drives search:** Goal failure beyond tolerance triggers a structured search over parameters, partitions, boundaries, and scale organization — ordered by substrate modification cost.
6. **Success caches:** Successful solutions become reusable subassemblies with an ordered competency taxonomy; repeated reuse is the selection‑signature analogue for engineered systems.
7. **Measurable signature:** The combined system has observable developmental trajectories.

---

## Notation (minimal)

| Symbol | Meaning |
|---|---|
| x | external states |
| μ | internal states (belief/latent states) |
| s | sensory states |
| a | active states |
| b = (s,a) | Markov blanket separating μ from x |
| π | a partition / coarse‑graining map |
| σ | symbols (macrostates) produced by π |
| θ | agent configuration (architecture + parameters + stored caches) |
| F | variational free energy |
| 𝔼[F] | expected free energy (EFE) |
| AI(θ) | assembly index (structural construction cost with reuse) |
| CLC(θ) | cognitive light cone (goal reach — spatiotemporal extent) |
| EI, CP(l) | effective information / causal power profile across scales |
| η(θ) | informational efficiency (recoverable bits per unit work) |

---

## Core definitions (operational, not rhetorical)

### Informational Monism objects (measurement first)

- A **partition** π maps physical microstates to symbols: π : X_phys → Σ.
- A symbol is **(T,ε)-recoverable** if it can be stably decoded through the agent's interface over horizon T with error ≤ ε.
- A partition + dynamics induces a **macro‑channel** P(σ_out | σ_in, u) where u summarizes allowed interventions/controls.
- **Channel capacity** C(P) is the maximum mutual information achievable over that induced macro‑channel (given the admissibility constraints).
- **Informational efficiency** is:

$$\eta(\theta) := \frac{C(P_\theta)}{W(\theta)}$$

where W is the work/energy (or a calibrated proxy like Joules, wall‑clock time, or FLOP‑energy) required to realize P_θ over the evaluation horizon.

### Goal Measurement Formalism (turning "purpose" into a test)

- **G⁰ (preference):** informal orientation / value signal. In biology: bioelectric prepattern encoding morphological target. In engineering: requirements‑level intent prior to formalization.
- **G¹ (spec):** a measurable goal tuple G¹ = (F_G, ε_G, T, m_G), where:
  - F_G is a failure predicate on observed variables,
  - ε_G is tolerated failure probability,
  - T is the evaluation horizon,
  - m_G is the observation map (what variables count as "goal state").
- **G² (implementation):** the realized policy/dynamics that attempts to satisfy G¹.
- The **specification gap** ‖G¹ − G²‖ is any metric of mismatch sufficient to predict persistent failure.
- The **formalization gap** (G⁰ → G¹) captures how well the informal preference has been translated into a testable specification. This gap is relevant at Tier 1 of the APS cascade, where "retargeting" sometimes means refining G⁰ → G¹ (formalizing a previously vague preference), not just switching between existing G¹ specs.

### Assembly Theory objects (what "caching" means structurally)

- **AI(θ):** minimum number of join operations to construct θ allowing reuse of subassemblies.
- **Selection signature (AT):** high AI with high copy number indicates selection.
  **Engineered analogue:** high structural complexity with high reuse frequency indicates functional selection/retention.

> **AT controversy note:** Assembly measures have been criticized as repackaging existing complexity notions. This framework does not require AI to be a fundamentally new information measure. We use AI as a *structural proxy* for (i) internal degrees of freedom, (ii) modular reuse, and (iii) feasible interface complexity. Any monotone structural complexity measure that tracks reusable construction cost could play the same role.

### Causal Emergence objects (which scales "do the work")

- **Effective information (EI):** mutual information under **uniform** (max‑entropy) interventions on causes:

$$EI = I(X_{\mathrm{do}};Y)= \sum_x p(\mathrm{do}(x))\, D_{KL}(P(Y|\mathrm{do}(x))\,\|\,P(Y))\quad\text{with}\quad p(\mathrm{do}(x))=\frac{1}{|X|}$$

The uniform intervention is load‑bearing: it ensures fair cross‑scale comparison by max‑entropy probing.

- **CE 2.0 (Hoel 2025):** causation is generally **distributed**; causal contribution is represented by a profile {CP(l)} across scales l, not a single argmax scale. *Emergent complexity* measures how widely distributed causation is across the scale hierarchy.

### Markov blanket object (what is feasible)

- b=(s,a) is a Markov blanket if μ ⟂ x | b.
  Operationally: s is the observation interface; a is the intervention interface.

---

## Bridge hypotheses (explicit assumptions)

These are the only places the argument "reaches across" frameworks.

**BH1 (Assembly → representational/interface capacity, necessary not sufficient).**
Higher reusable structural complexity generally enables:
- more internal degrees of freedom (more possible μ‑states),
- richer partitions π that are recoverable at the interface,
- larger/cleaner sensory and active surfaces (higher effective bandwidth).

But AI is a static structural measure; CLC is a dynamic functional measure. High AI does not guarantee large CLC without appropriate *organization* (functional blanket hierarchies with correct coupling). A disassembled watch and an assembled watch may have similar AI but radically different CLC.

**BH2 (Capacity bounds light cone).**
For any agent, finite internal state capacity + finite interface bandwidth + finite energy budget imply an upper bound on the set of goal specs it can satisfy:
- longer horizons T require memory / model capacity,
- richer observation maps m_G require sensory bandwidth and stable partitions,
- tighter tolerances ε_G require more control precision and/or energy.

**BH3 (Nested organization tracks complexity).**
As reusable structure increases, additional nested Markov blankets become feasible (new compositional levels with their own s_l, a_l, μ_l).

**BH4 (Caching increments reusable structure).**
Successful adaptations are stored in forms that reduce future search cost: codebooks, priors, modules, protocols, and (sometimes) new blanket levels. Repeated reuse is the analogue of high copy number. Cached competencies have an ordered taxonomy (see Proposition 7).

These hypotheses are falsifiable via the observable suite in "Instrumentation."

---

## Main argument (eight propositions)

### Proposition 1 — Assembly constrains feasible agency (bounded feasibility)

**Claim.** AI(θ) (or a structural proxy) is a necessary resource bound on feasible goal specifications and therefore on CLC(θ).

**Reasoning.**
- If the induced macro‑channel P_θ cannot stably represent the variables required by m_G over horizon T with tolerance ε_G, then G¹ is infeasible regardless of "intent."
- Increasing reusable structure typically increases the size/quality of Σ_stable(θ) and the achievable C(P_θ), expanding the set of feasible (T, m_G, ε_G).

**Deliverable.** A testable relation of the form:
- feasible goal set 𝒢(θ) ⊆ 𝒢_max(AI(θ)),
- CLC(θ) := max_{G¹∈𝒢(θ)} (horizon(G¹), dim(m_G(G¹))).

CLC is a *spatiotemporal* measure following Levin: it captures both the temporal reach (horizon) and the spatial/dimensional complexity (observation map richness) of the largest feasible goal.

*(The functional form of 𝒢_max is an open problem; see "Open problems.")*

---

### Proposition 2 — Feasible partitions + CE 2.0 pick operative scales

**Claim.** "Relevant scale" is: scales with significant causal contribution **among partitions the agent can actually implement**.

Define:
- **P_feasible(θ):** partitions π that are (i) admissible (interface‑bounded, counterfactually robust, compositional) and (ii) operationally realizable at the blanket boundary (inferable from s and intervenable via a).
- Compute CE 2.0 causal profile {CP(l)} over feasible scales.

Then the operative set is:

$$S_{\mathrm{eff}}(\theta) = \{ l : CP(l) \geq \tau \text{ and } \pi_l \in P_{\mathrm{feasible}}(\theta) \}$$

> **Engineering approximation note.** CE 2.0 treats {CP(l)} as a continuous distribution; the threshold τ discretizes it. This is an engineering necessity — resource allocation to scale‑monitoring requires discrete decisions about which scales to instrument. In principle, goal‑specification effort could be weighted proportional to CP(l) without a hard cutoff; in practice, τ trades off monitoring cost against causal coverage. The framework is robust to the choice of τ: tighter τ → more scales monitored → higher overhead; looser τ → fewer scales → risk of missing causally relevant dynamics.

**Implication.** Goal specs should choose observation maps m_G that project onto variables at scales in S_eff (possibly multiple scales if CP is distributed).

**Bridge use.** BH3 links rising reusable structure to deeper blanket hierarchies, which expands P_feasible(θ) and can broaden {CP(l)}.

---

### Proposition 3 — Goals are attractor basins at causally relevant scales

**Claim.** At causally relevant scales, the dynamics define attractors; a goal spec G¹ names a basin.

- Basins are defined over observed coordinates m_G(·).
- Failure predicate F_G describes leaving the basin.
- ε_G sets tolerated escape probability; T sets evaluation horizon.
- Compound goals (e.g. "generate profit while not harming while staying alive") are intersected basins with priority‑ordered relaxation: under resource pressure, the lowest‑priority basin constraint is relaxed first.

**Biological instance (planaria — not analogy, same abstract pattern).** Levin's experimental results demonstrate that the morphogenetic attractor landscape is:

- **Multistable:** brief pharmacological inhibition of gap junctional communication permanently rewrites the regenerative target from one‑headed to two‑headed (Durant et al. 2017). This is basin switching via bioelectric state manipulation, without genomic change.
- **Reversible:** restoring normal bioelectric state with pump‑blocking reagents resets regeneration to one‑headed (Durant et al. 2017). The landscape has at least two stable basins accessible via the same control interface.
- **Phylogenetically deep:** gap junction uncoupling in *G. dorotocephala* produces head morphologies of species ~150 Mya divergent (*S. mediterranea*, *P. felina*) despite wild‑type genome (Emmons‑Bell et al. 2015). The landscape encodes conserved alternative morphologies — more basins than default expression reveals.

This is the morphogenetic instance of the framework's general claim: goal‑directed systems operate in multistable landscapes, and interventions at the right scale (here: bioelectric, not genomic) can switch between basins. The engineering prescription follows: design agents whose goal specifications correspond to identifiable, switchable basins at causally relevant scales.

**Goal Measurement Formalism link.** Each G¹_i specifies a basin: F_{G_i} defines the basin boundary, ε_{G_i} is tolerated excursion probability, T_i is evaluation timescale, m_{G_i} projects onto goal‑relevant coordinates. The specification gap ‖G¹ − G²‖ measures how far the implemented dynamics are from reliably occupying the specified basin.

---

### Proposition 4 — Markov blankets define boundaries (and feasibility) at each scale

**Claim.** The Markov blanket b=(s,a) is the concrete implementation of "what the agent can measure and do."

- IM's interface‑boundedness (C1) is the statement: partitions must live at the blanket boundary. The agent cannot partition states it cannot sense.
- Nested blankets imply nested feasible partition sets, enabling multiscale control without micromanaging microdynamics (boundary‑condition control / "bioprompting" in Levin's terminology).
- AI(θ) constrains the depth of the blanket hierarchy: low AI → shallow hierarchy → few compositional levels → narrow P_feasible.

**Bridge use.** BH3 links rising reusable structure to deeper blanket hierarchies, which expands P_feasible(θ) and can broaden {CP(l)}.

---

### Proposition 5 — Active inference supplies within‑blanket dynamics and an exploration term

**Claim.** Within each blanket level l, dynamics can be implemented (engineering) or redescribed (biology) as minimizing variational free energy. Under the standard generative model p(s,x) = p(s|x)p(x):

$$F = -\ln p(s) + D_{KL}(q(x)\,\|\,p(x|s))$$

Since D_KL ≥ 0, F upper‑bounds surprise −ln p(s). Perception (updating μ) reduces the KL term; action (updating a) reduces surprise by changing sensory input.

Exploration pressure comes from **expected free energy** (EFE), which decomposes into:
- **Extrinsic value** (pragmatic): preference satisfaction / goal‑seeking,
- **Epistemic value** (intrinsic): information gain / uncertainty reduction.

The epistemic term supplies exploration without hand‑coded randomness — agents preferentially sample actions that reduce model uncertainty about the landscape.

**Engineering payoff.** This gives one optimization language for:
- state inference (update μ → reduce KL),
- control (update a → reduce surprise),
- exploration (choose actions that maximize expected information gain).

**Shared priors compress communication.** When agents share a generative model (shared context K in IM terms), prediction errors decrease: H(I|K) < H(I). This reduces the free energy each agent must dissipate, directly reducing W_operate and increasing η. In morphogenesis: the bioelectric prepattern acts as K, biasing all cells toward the same attractor basin.

---

### Proposition 6 — Goal failure triggers a structured morphogenetic search (APS)

**Trigger.** If UCB_{1−δ}(p̂_fail(θ; t)) > ε_G, enter exploration.

**APS cascade (ordered by substrate modification cost — cheapest first).**

| Tier | Operation | What is modified | Why this ordering |
|---|---|---|---|
| **0: Parameter tuning** | Adjust μ, a within current model | Nothing structural — beliefs and actions only | Zero assembly cost; operates within existing landscape |
| **1: Goal/partition retargeting** | Change which basin is targeted; repartition π_G; possibly refine G⁰→G¹ (formalize a vague preference) | The goal specification (a configuration artifact) | Low assembly cost; changes *which goal* is pursued, not *what the agent is* |
| **2: Boundary expansion** | Expand s or a, add protocols/modules, modify priors/codebooks | The agent's sensing/acting substrate | Medium assembly cost; changes the agent's *interface* — what it can measure and do |
| **3: Scale reorganization** | Recompute {CP(l)}; add/remove blanket levels; redesign compositional hierarchy | The agent's scale structure | High assembly cost; reorganizes *how many levels of description* the agent operates across |

**Ordering justification.** Each tier modifies progressively more of the agent's substrate. Tier 0 changes parameters within a fixed architecture. Tier 1 changes the goal specification, which is a configuration artifact (analogous to changing a setpoint vs. rewiring the controller). Tier 2 changes the agent's boundary — what it can sense and do — which requires structural modification. Tier 3 reorganizes the compositional hierarchy itself, which is the most expensive because it may invalidate existing caches and require re‑deriving the causal profile.

**Selection criterion.** Choose the candidate change that best trades off:
- expected reduction in failure probability / free energy,
- expected information gain (epistemic value from EFE),
- assembly cost / implementation cost.

**Diagnostic cascade.** At each tier, the agent answers a question before escalating:
- Tier 0: "Can I reach the basin with better parameters?" If no →
- Tier 1: "Am I targeting the right basin? Is my G¹ well‑specified?" If wrong basin or vague G⁰ →
- Tier 2: "Do I need capabilities I don't have?" If yes →
- Tier 3: "Is my scale structure correct for this problem?"

---

### Proposition 7 — Successful solutions cache as reusable assembly (competency taxonomy)

**Claim.** When APS succeeds, the winning solution is stored in a form that reduces future expected search cost.

Track two quantities:
- **structural complexity proxy** (AI or module‑graph join cost),
- **reuse count** n_i (copy‑number analogue): how often a cached subassembly is invoked successfully across episodes/tasks.

**Competency taxonomy (ordered by assembly cost).** Following Levin's continuum of cognitive competencies, each cached adaptation type corresponds to a distinct landscape modification:

| Competency | Landscape modification | IM/Agentic analogue | Assembly cost (ordinal) |
|---|---|---|---|
| **Sensitization** | Lower basin barrier (easier to trigger response) | Reduce ε_G threshold for known failure mode | Lowest (parameter) |
| **Habituation** | Raise barrier for benign perturbation (harder to trigger) | Increase ε_G for benign fluctuations | Low (parameter) |
| **Associative learning** | Create saddle/channel connecting previously separate basins; context→response binding | Cache codebook K indexed by context fingerprint | Medium (new partition element) |
| **Anatomical homeostasis** | Create entirely new attractor basin actively maintained as setpoint | New G¹ with own (F_G, ε_G, T, m_G) and dedicated monitoring | High (new blanket level + attractor) |

The ordinal claim — each successive type requires strictly more structural modification — is defensible from the landscape descriptions. Specific integer ΔAI values are not assigned because the mapping from cognitive competencies to join‑counts is not yet formally derived (see Open Problems).

These competency types map onto Levin's *persuadability continuum*: the most efficient protocol for interacting with a system progresses from direct physical manipulation → reward/punishment → symbolic communication → linguistic goal‑setting. Each step up the continuum implies a larger CLC and higher assembly.

**Prediction.** Reuse counts become heavy‑tailed: a few caches dominate (high n_i), and those tend to be higher‑complexity modules that enable larger CLC expansions.

---

### Proposition 8 — The compound system has a measurable developmental signature

If Propositions 1–7 hold, then during development/training we expect:

1. **CLC expands stepwise** (new basins become reliably reachable; both horizon T and observation complexity dim(m_G) grow).
2. **P_feasible expands** (new partitions become recoverable/intervenable).
3. **CP(l) broadens** (causal contribution distributes across more scales).
4. **η increases** (capacity per work rises as priors/caches compress communication).
5. **ε‑triggers decline in mastered regions** and remain nonzero at the frontier.
6. **Competency distribution shifts** from low‑cost types (sensitization/habituation) toward high‑cost types (associative learning/anatomical homeostasis) over developmental time.

---

## Instrumentation (how you would actually measure this)

| Observable | Practical estimator | What would count as support |
|---|---|---|
| AI‑proxy(θ) | Minimal join count of module DAG; number of reusable codebooks + compositional depth | Rises when new reusable modules appear |
| Reuse count n_i | Invocation count of cache i conditioned on success | Heavy‑tailed; correlates with retained modules |
| CLC(θ) | Max (T, dim(m_G)) pair with UCB(p_fail) ≤ ε_G for some goal family | Stepwise increases aligned with new modules |
| P_feasible | Count of partitions whose symbols are (T,ε)-recoverable and controllable | Increases with interface expansion |
| CP(l) profile | EI/causal contribution per scale from controlled interventions and confusion matrices | Broadens; shifts after Tier‑3 events |
| η(θ) | Estimated channel capacity / measured energy or time cost | Increases as caches reduce per‑task cost |
| APS tier usage | Logs of which tier was needed to restore success | Shifts to higher tiers at capability frontiers |
| Attractor count | Number of distinct G¹ simultaneously satisfied stably | Increases with growth |
| Spec gap ‖G¹−G²‖ | Regret: expected failure rate minus ε_G, estimated from holdout episodes with distribution shift | Shrinks within mastered domains; persists at frontier |
| Formalization gap | Fraction of active goals still at G⁰ (no testable F_G) vs. formalized G¹ | G⁰ fraction decreases over development |
| Competency distribution | Classify cached adaptations as sensitization / habituation / associative / homeostatic | Shifts from low‑cost to high‑cost types |

---

## Open problems (what must be derived or tested)

1. **Derive AI → CLC bounds** via explicit information‑theoretic constraints (rate‑distortion / channel capacity / memory limits). The finite‑representational‑capacity argument is sound but informal; a proper derivation should yield functional form for 𝒢_max.
2. **Thermodynamic grounding:** relate ΔF or mutual information processed per episode to minimal work and to tier costs (Landauer‑style floors). Each APS tier should have at least an order‑of‑magnitude thermodynamic cost estimate.
3. **Operational CE 2.0 measurement:** robust estimators of CP(l) in partially observed, non‑stationary systems.
4. **AT mapping in engineered systems:** principled AI proxies for software/modules and how reuse relates to "copy number."
5. **Pruning and re‑organization:** conditions under which AI‑proxy is not monotone (compression, forgetting) while η improves.
6. **Competency → ΔAI derivation:** formalize the mapping from landscape modifications (barrier lowering, basin linking, basin creation) to join‑count increments in the assembly space. This would convert ordinal cost rankings to cardinal measures.
7. **G⁰ → G¹ formalization dynamics:** under what conditions does the APS cascade refine preferences into specifications vs. simply switching between existing specs? This is the requirements‑elicitation problem recast in morphogenetic terms.

---

## The argument in 18 lines (compressed)

1) Partitions π create symbols σ; symbols exist only if recoverable.
2) Recoverable partitions + dynamics induce a macro‑channel P(σ_out|σ_in,u).
3) Capacity C(P) and cost W define efficiency η = C(P)/W.
4) Markov blankets implement the interface that makes partitions/interventions feasible.
5) Feasible partitions P_feasible are those inferable from s and controllable via a.
6) EI quantifies causal content under uniform intervention; admissibility ensures EI > 0.
7) CE 2.0 yields a distributed causal profile {CP(l)} rather than a single best scale.
8) Goals must be specified on variables at scales with significant CP within P_feasible.
9) Goal specs G¹=(F_G,ε_G,T,m_G) name attractor basins under those variables.
10) Active inference provides within‑blanket dynamics; EFE supplies epistemic exploration pressure.
11) Finite structure + interface + energy bound which goals are feasible (CLC bound).
12) Failure beyond tolerance triggers exploration (ε‑trigger).
13) Exploration escalates by substrate cost: tune params → retarget basin → expand boundary → reorganize scales.
14) Candidate changes are evaluated by expected success + information gain − implementation cost.
15) Successful changes are cached as reusable subassemblies with ordered competency types.
16) Reuse frequency is the engineered analogue of "copy number."
17) Caching expands feasible partitions and horizons, broadens causal profiles, compresses communication, and raises η.
18) Therefore: agents grow by failing, in a measurable, multiscale, thermodynamically constrained way.

---

## References (core set)

- Cronin, L., Walker, S.I., Sharma, A. et al. (2023). Assembly Theory and the origin of life. *Nature* 622, 553–563.
- Durant, F., Morokuma, J., Fields, C., Williams, K., Adams, D.S., Levin, M. (2017). Long-term stochastic editing of regenerative anatomy via targeting endogenous bioelectric gradients. *Biophys. J.* 112(10), 2231–2243.
- Emmons-Bell, M., Durant, F., Hammelman, J., et al. (2015). Gap junctional blockade stochastically induces different species-specific head anatomies in genetically wild-type *G. dorotocephala*. *IJMS* 16(11), 27865–27896.
- Fields, C., Levin, M. (2022). Competency in navigating arbitrary spaces as an invariant for analyzing cognition in diverse embodiments. *Entropy* 24(6), 819.
- Friston, K. (2010). The free-energy principle: a unified brain theory? *Nat. Rev. Neurosci.* 11, 127–138.
- Friston, K., Levin, M., Sengupta, B., Pezzulo, G. (2015). Knowing one's place: a free-energy approach to pattern regulation. *J. R. Soc. Interface* 12, 20141383.
- Friston, K., Schwartenbeck, P., FitzGerald, T., et al. (2012). The anatomy of choice: dopamine and decision-making. *Phil. Trans. R. Soc. B* 369, 20130481.
- Hoel, E.P., Albantakis, L., Tononi, G. (2013). Quantifying causal emergence shows that macro can beat micro. *PNAS* 110(49), 19790–19795.
- Hoel, E.P. (2017). When the map is better than the territory. *Entropy* 19(5), 188.
- Hoel, E.P. (2025). Causal Emergence 2.0. *arXiv*:2503.13395v3.
- Kirchhoff, M., Parr, T., Palacios, E., Friston, K., Kiverstein, J. (2018). The Markov blankets of life. *J. R. Soc. Interface* 15, 20170792.
- Kuchling, F., Friston, K., Georgiev, G., Levin, M. (2022). Morphogenesis as Bayesian inference. *Front. Comput. Neurosci.* 16, 988977.
- Levin, M. (2019). The computational boundary of a "Self". *Front. Psychol.* 10, 2688.
- Bruineberg, J., Dolega, K., Dewhurst, J., Baltieri, M. (2020). The Emperor's New Markov Blankets. *BBS*.

---

## v4 → v5 change log

| # | Issue | Resolution |
|---|---|---|
| A | S_eff threshold τ discretizes continuous CP(l) | Added engineering‑approximation note acknowledging τ as practical necessity; noted CP‑weighting alternative |
| B | VFE equation glossed factorization assumption | Simplified to single form (surprise + KL); added "under the standard generative model p(s,x) = p(s\|x)p(x)" |
| C | APS tier ordering unjustified | Added ordering rationale column to APS table + justification paragraph + diagnostic cascade questions |
| D | Competency taxonomy absent | Restored full taxonomy table in Proposition 7 with ordinal costs and landscape modifications |
| E | G⁰→G¹ formalization gap underutilized | Integrated into Goal Measurement Formalism definition + Tier 1 description + Open Problem 7 + Instrumentation |
| F | Missing Hoel 2025 CE 2.0 reference | Added to references and to CE 2.0 definition |
| G | Spec gap estimator vague | Replaced with "regret: expected failure rate minus ε_G from holdout episodes with distribution shift" |
| — | One‑line compression said "CP‑weighted" but argument uses τ‑threshold | Changed to "CP‑profiled" |
| — | CLC defined as max horizon only | Changed to max (T, dim(m_G)) — spatiotemporal per Levin |
| — | "Morphogenetic" absent after title | Added Scope section paragraph + Proposition 3 framing as morphogenetic instance |
| — | Competency distribution missing from Proposition 8 predictions | Added as prediction 6 |
| — | Formalization gap missing from instrumentation | Added row |
| — | Competency → ΔAI derivation missing from open problems | Added as Open Problem 6 |
