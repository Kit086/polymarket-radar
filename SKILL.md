---
name: polymarket-radar
description: Collect hot Polymarket prediction markets for future-news radar, policy forecasting, macro signals, and technology trend analysis. Use this skill whenever the user wants to scan Polymarket by topic, identify the most important active prediction markets, monitor probabilities and recent movement, or turn market signals into a future-news radar / policy predictor / macro signal / tech trends report. This skill should first call the local script to fetch a summary, then use that summary as evidence to write the final Markdown report in the user's language.
---

# Polymarket Radar

Use this skill to gather read-only market signals from Polymarket and turn them into a final user-facing radar report.

This skill should call the local script to produce a stable evidence `summary`, then immediately write the final Markdown report grounded in that summary.

## What this skill does

- Query Polymarket Gamma `/events` with a curated tag set from `config/default.json`.
- Filter out irrelevant, stale, or low-quality markets.
- Keep binary Yes/No markets by default so the downstream agent gets usable implied probabilities.
- Rank markets by heat and momentum.
- Use the returned `summary` as evidence to write the final radar report.

## When to use this skill

Use this skill whenever the task is really about scanning Polymarket for signal detection, even if the user does not explicitly say "use Polymarket" or "generate a summary." Typical triggers include:

- future news radar
- policy forecast brief
- macro signal watchlist
- tech trend monitoring through prediction markets
- "what does Polymarket think about X?"
- scheduled agent jobs that periodically gather market signals before writing a report

## Safety and scope

- Stay read-only.
- Do not trade.
- Do not call order placement endpoints.
- Do not require login, wallet access, or authenticated APIs.
- Do not make up fields or market facts.
- Treat the script-returned `summary` as the primary evidence. Use raw structured output only when debugging.
- Do not output raw JSON dumps as the final user response.

## Scheduler to agent workflow

Use this skill inside a scheduled pipeline:

1. A scheduler or cron job triggers an agent with a recurring prompt.
2. That agent invokes `polymarket-radar` with the user's language.
3. The skill calls the script to collect current market signals.
4. The skill writes the final user-facing radar report grounded in the returned `summary`.

## Inputs

Expect a JSON payload for `scripts/polymarket_radar.py`.

Required:

```json
{
  "language": "zh-CN"
}
```

Guidance:

- `language` should come from the active user context.
- All non-language settings (tags, thresholds, limits) should come from `config/default.json`.

## Workflow

1. Choose the runtime `language` from the user context.
2. Run:

```bash
python scripts/polymarket_radar.py <<'EOF'
{"language":"zh-CN"}
EOF
```

3. Read the returned JSON and treat the `summary` field as the main evidence artifact.
4. Write the final Markdown report in the user's language, grounded in the returned `summary`.
5. If the summary reports that no qualifying signals were found, say so clearly instead of inventing market evidence.

## Output contract

Final output MUST be a Markdown report (not JSON).

Internally, this skill first calls `scripts/polymarket_radar.py`, which returns JSON containing a `summary` string. Use that `summary` as the evidence base.

The Markdown report MUST include 4 fixed sections (localized to the user's language):

- future news radar
- policy predictor
- macro signals
- technology trends

## Reporting guidance

After the `summary` is returned, write the final report grounded in the returned market evidence. Make it clear that market probabilities are implied probabilities rather than confirmed facts.

Use a compact format suitable for scheduled runs. Prefer short sections with bullet points over long essays.

Use this structure:

- Title + generated time (from the summary)
- A short cross-tag highlights block (from the summary's global top signals)
- 4 fixed sections (future news radar / policy predictor / macro signals / technology trends)
- Caveats (implied probabilities, low-liquidity noise, uncertainty)

## Examples

**Example 1:**
Input task: "看一下 Polymarket 里最近最值得关注的市场，给我一份中文雷达报告"
Suggested tool input (skill -> script):

```json
{
  "language": "zh-CN"
}
```

**Example 2:**
Input task: "Give me an English radar report based on the hottest prediction markets on Polymarket."
Suggested tool input (skill -> script):

```json
{
  "language": "en-US"
}
```
