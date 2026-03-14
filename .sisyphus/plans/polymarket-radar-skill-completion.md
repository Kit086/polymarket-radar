# Plan: Finish `polymarket-radar`

## Goal
Finish the existing skill so it cleanly supports the intended workflow:

1. scheduler/cron prompts an agent,
2. agent invokes `polymarket-radar`,
3. skill returns a summary-first artifact,
4. downstream agent writes the final report from that summary.

## Constraints
- Keep the skill read-only.
- Preserve `summary` as the primary artifact.
- Use raw structured output only for debugging and evaluation.
- Follow the `skill-creator` loop: improve skill, create evals, run with-skill vs baseline, grade, benchmark, and generate a human review artifact.

## Planned changes

### 1. Snapshot the current skill before any edits
- Create `/home/kit/projects/polymarket-radar-workspace/skill-snapshot/` immediately.
- Copy the current repo skill assets there before changing `SKILL.md`, `README.md`, `evals/evals.json`, or `scripts/polymarket_radar.py`.

QA:
- Tool: shell copy + directory read.
- Expected result: snapshot contains the pre-change versions of `SKILL.md`, `README.md`, `evals/evals.json`, `config/default.json`, and `scripts/polymarket_radar.py`.

### 2. Tighten the skill contract
- Update `SKILL.md` so it is explicit about cron/agent usage, summary-first output, failure handling, and when `config_overrides` are appropriate.
- Make the downstream report handoff clearer so another agent can reliably turn the summary into a report without falling back to raw JSON.

QA:
- Tool: file read.
- Expected result: `SKILL.md` explicitly describes scheduler -> agent -> skill -> summary -> downstream report and keeps `summary` as the primary artifact.

### 3. Harden the runtime where the repo drifts from the contract
- Fix obvious contract issues in `scripts/polymarket_radar.py`, especially ranking/config drift and edge cases that hurt the summary-first workflow.
- Keep changes surgical and aligned with current behavior.

QA:
- Tool: `python scripts/polymarket_radar.py --self-test` and representative live invocations.
- Expected result: self-tests pass and both Chinese and English runtime invocations return JSON with a top-level `summary` field.

### 4. Improve repo docs and eval definitions
- Expand `README.md` to document the cron -> agent -> skill -> report flow.
- Upgrade `evals/evals.json` from starter prompts into stronger skill-creator eval definitions with expectations.

QA:
- Tool: file read / JSON validation.
- Expected result: `README.md` documents the intended workflow and `evals/evals.json` contains realistic prompts plus explicit expectations.

### 5. Prepare the evaluation workspace
- Create `/home/kit/projects/polymarket-radar-workspace/iteration-1/`.
- Create per-eval directories with `eval_metadata.json`.

QA:
- Tool: directory read.
- Expected result: each eval directory exists and contains `eval_metadata.json` with `eval_id`, `eval_name`, `prompt`, and `assertions`.

### 6. Run with-skill and baseline executions
- For each eval, run one subagent that follows the current edited skill and one baseline subagent that follows the snapped pre-change `old_skill` version.
- Save outputs, transcripts/notes where possible, and timing metadata.

QA:
- Tool: task outputs + directory read.
- Expected result: each eval has both `with_skill/outputs/` and `old_skill/outputs/` populated, and each run has timing metadata.

### 7. Grade and benchmark
- Grade each run against explicit expectations.
- Aggregate benchmark results using the skill-creator scripts.
- Run an analyzer pass to surface non-obvious patterns.

QA:
- Tool: generated JSON/Markdown reads.
- Expected result: each run has `grading.json`; iteration root has `benchmark.json` and `benchmark.md`; analyzer notes are saved.

### 8. Generate review artifact
- Use `eval-viewer/generate_review.py` with `--static` to generate a reviewable HTML artifact because browser/display availability is not guaranteed.

QA:
- Tool: file existence/read.
- Expected result: a static HTML review file exists and points to outputs plus benchmark data.

### 9. Final verification and consultation
- Re-run runtime self-tests.
- Run representative live invocations.
- Consult Oracle on the finished first-pass implementation and evaluation quality before reporting back.

QA:
- Tool: shell runs + Oracle output.
- Expected result: local verification passes and Oracle returns either approval or concrete follow-up concerns to address before reporting.

## Verification checklist
- `python scripts/polymarket_radar.py --self-test` exits 0.
- Default skill invocation returns JSON with `summary`.
- Representative Chinese and English runs produce usable summaries.
- Eval workspace contains outputs for with-skill and `old_skill` runs.
- `benchmark.json` and static review HTML are generated.

## Out of scope for this pass
- Full trigger-description optimization loop unless the skill is otherwise in good shape.
- External scheduler configuration outside this repo.
