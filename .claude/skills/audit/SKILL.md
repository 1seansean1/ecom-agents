---
name: audit
description: "Run the Holly Grace cross-document consistency audit. Executes Standard Audit (C001-C012) and optionally Deep Review. Scores findings with severity model (P0-P3), enforces SIL-sensitive pass/fail policy, and applies cascade remediation. Use when: user says 'run audit', 'check consistency', 'validate documents', or invokes /audit."
---

# Holly Grace Audit Procedure

## 1. Purpose

This document defines one audit and review standard for Holly Grace.
Primary objective: prevent drift between overlapping assertions across `architecture.yaml`, `status.yaml`, README, progress artifacts, and governance docs.

## 2. Scope and Sources of Truth

Authoritative sources:

- Topology SSOT: `docs/architecture.yaml`
- Progress SSOT: `docs/status.yaml`
- Task source: `docs/Task_Manifest.md`
- Audit ledger: `docs/audit/finding_register.csv`

Derived artifacts that must stay synchronized:

- `docs/architecture/PROGRESS.md`
- `docs/architecture/GANTT.mermaid`
- `docs/architecture/GANTT_critical.mermaid`
- `docs/architecture/Artifact_Genealogy.md`
- `README.md` progress and version/count references

## 3. Audit Modes

### 3.1 Standard Audit (required on task boundaries)

Run:
```bash
python -m holly.arch audit
```
This executes checks `C001-C012` in `holly/arch/audit.py`.

### 3.2 Deep Review (required for high-risk changes)

Run standard audit plus:
```bash
ruff check holly tests
pytest tests/ -q
python -m holly.arch gantt --stdout
```
Then perform agent-level checks in Sections 7-9.

`mypy` is a future gate. It is NOT currently part of the Deep Review toolchain and is NOT invoked or reported. When mypy is added to the toolchain, it will be listed here as a mandatory gate. This exemption avoids the §6.2 zero-SKIP contradiction — since mypy is not invoked, it produces no SKIP result.

## 4. Standard Audit Check Map

| Check | Severity | Validates | Primary Sources |
|---|---|---|---|
| C001 | HIGH | Component count consistency | `architecture.yaml`, `Artifact_Genealogy.md` |
| C002 | MEDIUM | Connection count consistency | `architecture.yaml`, `Artifact_Genealogy.md` |
| C003 | HIGH | Task count consistency | `Task_Manifest.md`, `README.md` |
| C004 | MEDIUM | Critical-path count consistency | `Task_Manifest.md`, `README.md` |
| C005 | HIGH | Done-count sync | `status.yaml`, `PROGRESS.md`, `README.md` |
| C006 | HIGH | Resolved findings not left as placeholder SHAs | `finding_register.csv` |
| C007 | MEDIUM | Version string consistency | `architecture.yaml`, `README.md`, `Artifact_Genealogy.md` |
| C008 | MEDIUM | SIL count consistency | `SIL_Classification_Matrix.md`, `Artifact_Genealogy.md` |
| C009 | MEDIUM | Ruff gate | `holly/`, `tests/` |
| C010 | HIGH | Pytest gate | `tests/` |
| C011 | MEDIUM | Gantt freshness | generated Gantt vs checked-in Gantt |
| C012 | MEDIUM | Genealogy SAD component count consistency | `Artifact_Genealogy.md`, `architecture.yaml` |

Implementation note:

- `C006` currently checks unresolved placeholder values (`pending`, `N/A`, empty) for `RESOLVED` findings. It does not by itself guarantee git-object reachability.

## 5. Severity, Criticality, and Blast Radius Scoring

Use this scoring for findings from either Standard Audit or Deep Review. Scoring is performed by the agent at invocation time; the automated audit emits PASS/FAIL/WARN only.

### 5.1 Base factors

- Impact (`I`): 1-5
- Likelihood (`L`): 1-5
- Cascade (`C`): 1-5

Base score:
`R_base = I * L * C`  (range: 1-125)

### 5.2 Modifiers

- Blast radius (`B`):
  - `+0` single-file local fix
  - `+5` one SSOT + one downstream artifact
  - `+10` multi-document synchronization risk
  - `+15` repo-wide or workflow-wide drift risk
- Criticality (`K`):
  - `+0` SIL-1 / non-critical path
  - `+10` SIL-2 or critical-path task
  - `+20` SIL-3 component/path (`Kernel`, `Sandbox`, `Egress`, or their interfaces)
- Check severity (`S`):
  - `+10` for HIGH checks
  - `+5` for MEDIUM checks
  - `+0` for LOW checks

Final score:
`R = R_base + B + K + S`

### 5.3 Calibration examples

These worked examples anchor scoring and reduce subjectivity across invocations.

**Example A: C005 FAIL — done-count mismatch (`status.yaml` says 9, `PROGRESS.md` says 8)**
- I=3 (progress tracking incorrect, no code impact)
- L=5 (guaranteed on every read of PROGRESS.md)
- C=3 (affects PROGRESS.md + README Σ row)
- R_base = 3 × 5 × 3 = 45
- B=+10 (multi-document sync: status.yaml, PROGRESS.md, README)
- K=+0 (progress metadata, not a SIL-3 component)
- S=+10 (C005 is HIGH)
- **R = 45 + 10 + 0 + 10 = 65 → P2 (time-bounded)**

**Example B: C010 FAIL — pytest failure in kernel module**
- I=5 (broken tests in safety-critical module)
- L=5 (deterministic failure, blocks every CI run)
- C=5 (kernel changes cascade to sandbox, egress, all integration tests)
- R_base = 5 × 5 × 5 = 125
- B=+15 (repo-wide: blocks all development)
- K=+20 (SIL-3 component: Kernel)
- S=+10 (C010 is HIGH)
- **R = 125 + 15 + 20 + 10 = 170 → P0 (blocking emergency)**

**Example C: C011 WARN — Gantt chart stale by 1 task**
- I=2 (visual artifact out of date, no code impact)
- L=4 (likely after any status.yaml update without regeneration)
- C=2 (only GANTT.mermaid and GANTT_critical.mermaid affected)
- R_base = 2 × 4 × 2 = 16
- B=+5 (one SSOT + one downstream)
- K=+0 (non-critical artifact)
- S=+5 (C011 is MEDIUM)
- **R = 16 + 5 + 0 + 5 = 26 → P3 (advisory)**

**Example D: C009 FAIL — ruff lint error in `holly/kernel/k1.py`**
- I=3 (code style violation, may mask real issues)
- L=5 (deterministic, fires every run)
- C=2 (localized to one file, no downstream artifact impact)
- R_base = 3 × 5 × 2 = 30
- B=+0 (single-file fix)
- K=+20 (SIL-3: kernel module)
- S=+5 (C009 is MEDIUM)
- **R = 30 + 0 + 20 + 5 = 55 → P2 (time-bounded)**

### 5.4 Priority bands

- `P0 (blocking emergency)`: `R >= 95`
- `P1 (blocking high)`: `70 <= R < 95`
- `P2 (time-bounded)`: `40 <= R < 70`
- `P3 (advisory)`: `R < 40`

## 6. Pass/Fail Policy by Slice and SIL Context

### 6.1 Global rules (all slices)

- Any `FAIL` is blocking.
- `WARN` on `C001`, `C003`, `C005`, `C006`, `C007`, `C008`, `C011`, `C012` is treated as blocking until resolved or explicitly waived.
- `SKIP` on `C009` or `C010` is blocking in executable environments.

### 6.2 SIL-sensitive escalation

- SIL-3 contexts (Slices `1/3a`, `3`, `8`):
  - Zero `FAIL`, zero `WARN`, zero `SKIP` required before merge.
  - Deep Review required.
- SIL-2 contexts:
  - Zero `FAIL` required.
  - `WARN` allowed only with documented remediation owner/date.
- SIL-1 contexts (Slices `13`, `14`):
  - Zero `FAIL` required.
  - `WARN` allowed short-term if remediation is scheduled before next pre-flight audit.

### 6.3 Release/phase-gate policy

- For release authorization and phase gate sign-off: zero `FAIL`, zero `WARN`, zero `SKIP`.

## 7. Cascade Remediation Map

When a finding is fixed, verify downstream cascades before re-running audit.

- If component or connection counts change:
  - update `architecture.yaml` or source generator
  - update `Artifact_Genealogy.md` labels and narrative references
  - verify README count/version references
- If task status changes:
  - update `docs/status.yaml`
  - run `python -m holly.arch gantt`
  - verify `PROGRESS.md`
  - verify README `Sigma` row
- If version changes (SAD/RTD/DPG):
  - update cross-document references (`README.md`, `Development_Procedure_Graph.md`, `Dev_Environment_Spec.md`, `Artifact_Genealogy.md`, audit docs)
- If finding is resolved:
  - update `finding_register.csv` with closure evidence
  - confirm closure SHA is not placeholder

## 8. Deep Review Checklist (Agent-Performed, Not Automated Gates)

- Structural coherence:
  - code modules align with RTD and `architecture.yaml`
- Specification traceability:
  - implementation and tests map to ICD/Behavior/Goal specs
- Process compliance:
  - Task Execution Checklist steps P0-P7 were followed
- Drift detection:
  - new edits did not bypass regeneration and synchronization steps
- Quality beyond standard audit:
  - type-ignore debt is tracked and bounded (mypy enforcement is a future gate; see §3.2)

## 9. Execution Procedure

1. Run Standard Audit.
2. Classify each non-PASS finding with the scoring model in Section 5.
3. Fix in SSOT-first order (never modify SSOT to fit stale derivatives).
4. Apply cascade remediation (Section 7).
5. Re-run Standard Audit.
6. If SIL-3 or critical-path work, run Deep Review gates.
7. Report findings by severity (`P0` to `P3`) with file paths and concrete evidence.

## 10. Reporting Format

Each finding must include:

- ID and check/source (for example `C005` or deep-review item)
- severity band (`P0-P3`) and computed score
- impact statement (what breaks and where)
- blast radius and cascade notes
- exact file references
- remediation action and verification step

## 11. Minimum Exit Criteria

- Task boundary pre-flight: no blocking findings.
- Task boundary post-flight: no blocking findings and all cascades resolved.
- SIL-3 merge or release gate: clean audit state (`FAIL/WARN/SKIP = 0`).
