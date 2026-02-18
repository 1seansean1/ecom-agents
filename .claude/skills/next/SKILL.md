---
name: next
description: "Execute critical-path tasks from the Holly Grace development pipeline. Single-task by default. Runs pre-flight audit, state sync, dependency-checked task identification, implementation, test authoring, doc sync, pre-push audit gate, scored post-commit remediation. With --loop: repeats until critical path is complete or a halt condition is met. Use when: user says 'next task', 'continue building', 'next on critical path', or invokes /next."
---

# /next — Execute the next critical-path task

You are executing one or more tasks from the Holly Grace development pipeline.

- **Default mode:** Execute one task, then stop and report.
- **Loop mode** (user says `/next --loop`, `/next --loop --max-tasks N`, "keep going", or "run to completion"): Execute tasks continuously, subject to halt conditions (§Halt Conditions). `--max-tasks N` caps the number of task iterations (default: unlimited, halts on other conditions).

Follow the Task Execution Checklist (README.md §Task Execution Checklist) exactly. No shortcuts.

**Repo root:** Find the holly-grace repo in the user's workspace folder.
**Venv:** Activate the Python virtual environment before running any commands.

---

## Phase 1: Pre-flight (P0–P2)

1. **Run audit.** Execute `python -m holly.arch audit` from the repo root. If any check shows FAIL, fix it. If a pre-existing FAIL cannot be resolved within 3 attempts (see §Attempt Definition), halt and report per §Halt Conditions. Do not proceed to a new task with existing failures.

2. **Sync state.** Read `docs/status.yaml` and identify all tasks marked `done`. Read `docs/architecture/PROGRESS.md` and confirm the done counts match. Read the README progress table (Σ row) and confirm it matches too. If any disagree, fix the discrepancy before proceeding.

3. **Identify next task.** Derive the critical path dynamically: parse `docs/Task_Manifest.md` for tasks annotated as critical-path, cross-reference `docs/status.yaml` for completion status. Selection criteria — the next task must satisfy BOTH:
   - Status is NOT `done` in `status.yaml`.
   - All declared dependencies (per `Task_Manifest.md`) have status `done` in `status.yaml`.
   Select the first task satisfying both conditions in manifest order. Do not use a hardcoded task sequence. Sanity check: confirm the derived critical path contains ≥1 task. If the parser returns zero critical-path tasks, halt — the manifest format may have changed. If all critical-path tasks are `done`, proceed to Phase 5 (Project Completion). Report which task you will execute.

4. **Read task spec.** In `docs/Task_Manifest.md`, find the task entry. Note its MP step, input artifacts, output artifacts, verification method, and acceptance criteria. Read any referenced specification documents (ICD, Behavior Specs, Goal Hierarchy) that the task traces to.

5. **Spec pre-check (P2).** Verify the acceptance criteria are concrete and testable. If vague, sharpen them against the γ-phase specs before proceeding. If still untestable, halt per §Halt Conditions (condition 5).

6. **Report plan.** Tell the user: "Next task: `<ID>` — `<name>`. Dependencies satisfied. Acceptance criteria: `<list>`. Proceeding with implementation."

## Phase 2: Implementation (P3–P5)

7. **Implement (P3A).** Write production code in the module specified by the RTD (`docs/architecture/RTD_0.1.0.4.mermaid`). Follow existing code patterns: type annotations, docstrings, `__slots__`, ruff compliance, `from __future__ import annotations`.

8. **Test authoring (P3C).** Write tests exercising the acceptance criteria. At minimum: one positive test per criterion, one negative test (invalid input / failure path). Use property-based tests (hypothesis) for invariant-heavy code. Place in `tests/unit/` or `tests/integration/` as appropriate.

9. **Verification (P4).** Run:
   - `ruff check holly tests` — must be zero errors
   - `pytest tests/ -q` — must be all pass, zero regressions
   If either fails, fix. If a failure cannot be resolved within 3 attempts, halt per §Halt Conditions.

10. **Regression gate (P5).** Confirm the pre-existing test count still passes. Report: "Tests: X passed (was Y before this task, +Z new)."

## Phase 3: Documentation sync, audit gate, and commit (P6–P7)

This phase is where most process violations occur. Execute every step.

11. **Update status.yaml (P6.1a).** Mark the task `done` with today's date and a note including test count contribution. Format:
    ```yaml
    <task_id>:
      status: done
      date: "<YYYY-MM-DD>"
      note: "<summary> (<N> tests)"
    ```

12. **Regenerate tracking artifacts.** Run `python -m holly.arch gantt`. This regenerates `GANTT.mermaid`, `GANTT_critical.mermaid`, and `PROGRESS.md`.

13. **Diff PROGRESS.md.** Confirm the done count incremented. If unchanged, something is wrong — halt and investigate.

14. **Update README progress table.** Update the Slice 1 row and Σ row to match PROGRESS.md totals.

15. **Update Artifact Genealogy.** Unconditionally verify counts in `docs/architecture/Artifact_Genealogy.md`: mermaid node labels, narrative paragraphs, inventory table, and chronology section. Update any that changed.

16. **Pre-push audit gate.** Run `python -m holly.arch audit`. This is mandatory before commit/push. Requirements:
    - Zero `FAIL`.
    - For SIL-3 context: zero `WARN`, zero `SKIP`.
    - `SKIP` on `C009` or `C010` is blocking in any executable environment (per Audit Procedure §6.1).
    If the gate fails, fix the issues (SSOT-first, cascade per Audit Procedure §7), then re-run. If unresolvable within 3 attempts, halt per §Halt Conditions. Do not commit or push with a failing audit gate.

17. **Commit and push (P7).** Stage only files touched by this task. Commit message: `Task <ID>: <summary>`. Push to both remotes: `git push github main:master && git push gitlab main`. Both pushes are chained with `&&` — if the first fails, the second does not execute.

18. **Report completion.** Tell the user: "Task `<ID>` complete. Tests: X total (+Y new). Committed: `<sha>`."

## Phase 4: Post-commit verification and remediation

One verification pass after push confirms the committed state is clean and catches any issues the pre-push gate could not detect (e.g., git-level problems, push-triggered state changes).

19. **Standard Audit.** Run `python -m holly.arch audit`. Record all non-PASS results.

20. **Deep Review (conditional).** Run Deep Review gates if ANY of the following are true:
    - The task is in a SIL-3 context (Slices `1/3a`, `3`, `8`)
    - The task modified any file in a component classified SIL-3 in `docs/SIL_Classification_Matrix.md` (currently: Kernel, Sandbox, Egress, and their interfaces)
    ```bash
    ruff check holly tests
    pytest tests/ -q
    python -m holly.arch gantt --stdout
    ```
    `mypy` is a future gate and is NOT invoked. It is not reported as SKIP. When mypy is added to the toolchain, this exemption will be removed and it will become a mandatory Deep Review gate.
    Then perform the agent-level Deep Review checklist (Audit Procedure §8): structural coherence, specification traceability, process compliance, drift detection.

21. **Score findings.** For each non-PASS result from steps 19–20, compute the severity score per Audit Procedure §5. Use the calibration examples in Audit Procedure §5.3 to anchor I/L/C assignments:
    - `R = (I × L × C) + B + K + S`
    - Classify into priority band: `P0` (≥95), `P1` (70–94), `P2` (40–69), `P3` (<40).

22. **Report findings.** For each finding, report per Audit Procedure §10:
    - ID and check/source
    - Severity band and computed score
    - Impact statement
    - Blast radius and cascade notes
    - Exact file references
    - Remediation action and verification step

23. **Remediate.** Fix all blocking findings (`P0`, `P1`, and `WARN`-on-blocking-checks per §6.1). Fix in SSOT-first order (Audit Procedure §9 step 3). Apply cascade remediation per §7. For `P2` findings, fix if feasible within scope; otherwise document remediation owner/date. `P3` findings are advisory — note them and proceed. If a blocking finding cannot be resolved within 3 attempts, halt per §Halt Conditions.

24. **Re-run audit (only if remediation occurred).** If step 23 changed files, re-run `python -m holly.arch audit`. Confirm zero `FAIL`. For SIL-3 context, confirm zero `WARN`. If no remediation was needed, skip this step.

25. **Commit remediation (if any).** If remediation changed files, stage and commit: `Audit remediation for Task <ID>`. Push to both remotes with `&&`.

26. **Verify exit criteria.** Confirm Audit Procedure §11 minimum exit criteria are met:
    - Task boundary post-flight: no blocking findings, all cascades resolved.
    - SIL-3 context: `FAIL/WARN = 0`.

## Loop (loop mode only)

27. **Loop controls.** Before starting the next iteration, check halt conditions:
    - If `--max-tasks N` was specified and N tasks have been completed this session, halt gracefully.
    - If the conversation has exceeded 100 tool calls since the last `/next` invocation, halt gracefully.
    - If the agent is uncertain about previously-implemented code structure or test coverage (indicative of context degradation), halt gracefully.
    When halting: commit current state (if uncommitted changes exist), report progress summary (tasks completed this session, total done count, test count, last SHA), and stop. The next `/next` invocation will pick up cleanly from Phase 1 pre-flight.

28. **Return to Phase 1, step 1.** Begin the next iteration.

## Default mode exit

If not in loop mode, stop after step 26. Report: "Task `<ID>` complete. Audit: clean (N P3 advisory notes). Next critical-path task: `<next_id>`. Run `/next` to continue or `/next --loop` for continuous execution." Omit the P3 parenthetical if there are zero advisory findings.

## Phase 5: Project Completion

29. **All critical-path tasks done.** When step 3 finds no remaining critical-path tasks with status other than `done`, execute one final audit pass (steps 19–26) and report:
    "Critical path complete. All tasks done. Final audit: clean. Total tests: X. Last commit: `<sha>`."

---

## Halt Conditions

The agent MUST halt and report to the user when any of the following occur:

1. **Unresolvable failure.** A FAIL or blocking finding cannot be resolved within 3 attempts. Action: create a WIP branch using idempotent creation (`git checkout -B wip/<task_id>` — the `-B` flag creates or resets the branch, avoiding failure if it already exists from a prior halt), commit partial progress there, report the blocking issue with full context (failing check, file references, attempts made, error output), and ask the user for guidance. Do not commit partial work to `main`.

2. **Loop limit reached.** `--max-tasks` count exhausted, or 100+ tool calls in this session. Action: commit current state to `main` (if clean and audit-passing), report progress summary, stop cleanly.

3. **Design-level issue.** The agent determines that a test failure or acceptance criterion requires architectural changes beyond the current task's scope. Action: report the issue, do not attempt speculative refactoring, ask the user.

4. **Push failure.** Either remote rejects the push (e.g., diverged history, auth failure). Action: do not force-push. Report the error and stop.

5. **Ambiguous acceptance criteria.** Step 5 determines criteria are untestable even after consulting specs. Action: report the ambiguity with specific questions, ask the user to clarify before proceeding.

6. **Manifest parse failure.** Step 3 returns zero critical-path tasks when tasks are known to remain. Action: report the parse anomaly with manifest path and expected task IDs, ask the user to verify manifest format.

---

## Attempt Definition

One remediation attempt consists of exactly these steps in order:
1. **Edit**: modify the file(s) believed to cause the failure.
2. **Gate**: re-run the specific failing gate (e.g., `ruff check`, `pytest`, `python -m holly.arch audit`).
3. **Inspect**: read the gate output and determine if the failure is resolved.

If the failure persists after step 3, that counts as one failed attempt. Three failed attempts triggers a halt. Attempts are counted per-finding, not globally — resolving finding A resets the counter before attempting finding B.
