# Draft: Polymarket Radar Skill Check

## Requirements (confirmed)
- User wants a check of the current `polymarket-radar` skill against the original requirement.
- User originally started from `archived/polymarket_radar_test.py`.
- Skill should let an agent use Polymarket information to do downstream work.
- Skill should not expose raw JSON as the primary artifact; the script-generated `summary` should be the main input to the agent.
- Assume a fixed cron job periodically prompts an agent, and that agent should use this skill to generate content.
- User clarified that the skill output should be the final report/content the user originally wanted, not merely an intermediate summary.
- User clarified that agent invocation should be as simple as possible: provide only the user's language and rely on the fixed JSON config for everything else.
- User prefers minimal design and does not want extra scripts or interfaces unless they are clearly necessary.

## Technical Decisions
- Assess the current repository state, not only the archived prototype.
- Treat the main question as requirement understanding + completeness review, not implementation.
- Model the intended flow as: scheduler -> agent prompt -> skill invocation -> summary generation -> downstream report.
- Reassess the target flow based on the clarification that the skill itself should produce the final report, making the current summary-first two-stage design a drift from the original intent.

## Research Findings
- `SKILL.md`: current skill contract, trigger description, runtime workflow, output contract.
- `scripts/polymarket_radar.py`: current stdin-driven runtime tool that returns JSON with `summary` and optional `structured_output`.
- `config/default.json`: default operating parameters for tags, thresholds, and ranking.
- `evals/evals.json`: initial eval prompt set exists, but only at prompt/expected-output level.
- `archived/polymarket_radar_test.py`: original prototype kept for reference.
- `README.md`: confirms the repo now targets direct skill workflow instead of a separate `main.py` app.
- `scripts/polymarket_radar.py --self-test`: passes locally, so the current runtime contract is at least internally consistent.
- No cron, workflow, shell wrapper, or scheduler config exists in-repo; scheduling is still an external assumption.
- No formal assertion-based evals, benchmark artifacts, reviewer outputs, or trigger-optimization assets are present.

## Open Questions
- Is the cron-triggered agent expected to output only the final narrative report, or should it also persist the raw `summary` artifact somewhere each run?
- Should the skill itself stop at `summary`, with all interpretation handled by the calling agent, or should the skill include stronger guidance/templates for the downstream report step?
- The user has now answered the prior ambiguity: the desired end state is not summary-only; the skill should directly return the final report while using fixed config defaults apart from language.

## Scope Boundaries
- INCLUDE: understanding the requirement, current-state assessment, completeness gaps, full agent usage flow.
- EXCLUDE: implementing or editing the skill/tooling in this turn.
