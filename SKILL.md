---
name: polymarket-radar
description: Collect hot Polymarket prediction markets, infer the dominant market narrative, explain what the market thinks is likely to happen next, and write an analytical Markdown report grounded in the script-generated summary. Use this skill whenever the user wants a future-news radar, policy readout, macro signal note, tech trend brief, or asks what Polymarket implies will happen next. This skill should prepare config.json if needed, call the local script, produce a report in the user's language, save it to reports/, and return the same Markdown content.
---

# Polymarket Radar

Use this skill to turn Polymarket market data into a research-style analytical report.

This is not a fixed-template summary skill. The goal is to answer a harder question:

- If we treat Polymarket as a prediction market, what does the market think is likely to happen next?
- What is the evidence?
- Where are the tensions, contradictions, and tail risks?

## What this skill does

- Prepare runtime config from `config/default.json` into `config/config.json` when needed.
- Call `scripts/polymarket_radar.py` to fetch a read-only `summary`.
- Treat the returned `summary` as the evidence base.
- Infer the dominant narrative or main market axis for the current run.
- Write a Markdown report in the user's language.
- Save the final Markdown report to `reports/<utc-timestamp>.md`.

## When to use this skill

Use this skill whenever the task is really about reading Polymarket as a live forecasting surface rather than merely listing markets. Typical triggers include:

- future news radar
- policy forecast
- macro signal brief
- tech trend brief
- geopolitical market readout
- "what does Polymarket think will happen?"
- recurring cron-driven market intelligence jobs

## Safety and scope

- Stay read-only.
- Do not trade.
- Do not call order placement endpoints.
- Do not require login, wallet access, or authenticated APIs.
- Do not make up market facts that are not supported by the returned `summary`.
- Use the script-returned `summary` as the primary evidence.
- Do not output raw JSON as the final user-facing artifact.
- Make it explicit that market prices are implied probabilities, not confirmed facts.

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
- All non-language runtime settings should come from `config/config.json`.
- `config/default.json` is a backup template, not the live config once `config/config.json` exists.

## Workflow

1. Choose the runtime `language` from the user context.
2. Check whether `config/config.json` exists.
3. If `config/config.json` does not exist, copy `config/default.json` to `config/config.json`.
4. Use `config/config.json` as the live runtime config for the script.
5. Run:

```bash
python scripts/polymarket_radar.py <<'EOF'
{"language":"zh-CN","config_path":"config/config.json"}
EOF
```

6. Read the returned JSON and treat the `summary` field as the evidence artifact.
7. Identify the strongest current market narrative before writing the report.
8. Write the final Markdown report in the user's language.
9. Ensure `reports/` exists. If it does not exist, create it.
10. Save the exact final Markdown report to `reports/<utc-timestamp>.md`.
11. Return the same Markdown report as the final response.
12. If the summary reports that no qualifying signals were found, say so clearly instead of inventing evidence.

## Output contract

Final output MUST be a Markdown report.

Internally, this skill first calls `scripts/polymarket_radar.py`, which returns JSON containing a `summary` string. Use that `summary` as the evidence base.

The report MUST:

- use the user's language
- include a localized title and generation time
- include a localized `Polymarket 当前热点` style hotspot board near the top
- include real analysis, not just a natural-language rewrite of the summary
- be saved to `reports/<utc-timestamp>.md`

The report does NOT need to force four equally sized sections every run.

## Reporting guidance

Write the report like an analyst, not a formatter.

Do not start from a rigid template and then force all information to fit. Start from the strongest narrative in the summary, then organize evidence around that narrative.

### Preferred report flow

Use this as a preferred structure, not a rigid fill-in-the-blanks template:

- title + generated time
- localized hotspot board near the top
- core judgment
- market consensus
- tensions / contradictions
- logic chain
- risk scenario / what the market may be underpricing
- optional secondary sections for policy / macro / tech / geopolitics / crypto when they genuinely matter in this run
- caveats

### Hotspot board

Near the top of the report, add a localized hotspot board equivalent to `Polymarket 当前热点`.

Rules:

- use small Markdown tables
- group by topic when the summary supports it
- prefer 3-5 rows per topic
- use simple columns such as:
  - `市场 | 概率 | 交易量`
  - `市场 | 领跑者 | 概率`
- only include markets supported by the summary

The hotspot board is for rapid scanning. It should not replace the deeper analysis below.

### Core judgment

Early in the report, answer this directly:

- what does the market think is most likely to happen next?
- what is the dominant narrative in this run?

Use concise judgment-first language such as:

- 核心判断
- 本期判断
- The market is really pricing...
- The dominant narrative is...

This is allowed and encouraged, as long as it is evidence-backed.

### Market consensus

After the core judgment, group the key signals into a coherent consensus view.

Do not just restate one market after another. Instead explain:

- what the market broadly expects
- what the market does not expect immediately
- what kind of path the market is pricing

### Tensions and contradictions

This is a required analytical move whenever the summary supports it.

Actively look for combinations such as:

- escalation odds are high but ultimate ceasefire odds are also high
- a disruptive geopolitical event is priced aggressively but downstream macro outcomes are only moderately priced
- short-term and long-term markets imply different paths

Then say what that likely means.

This is one of the main sources of analytical value. Do not skip it when the evidence exists.

### Logic chain

Turn isolated markets into linked causality where justified by the summary. For example:

- geopolitical stress -> energy prices -> inflation pressure -> rate path -> recession risk
- AI model leadership -> large-cap valuation narrative -> capital markets preference -> IPO attention
- conflict escalation -> political positioning -> election narrative

Do not invent facts. Only connect links that are reasonably supported by the market evidence in the summary.

### Risk scenario and underpriced tail

Include a short section on what the market may be underpricing when the summary supports it.

Useful prompts to follow:

- what is the market's main scenario?
- what would break that scenario?
- what tail risk appears insufficiently priced?

It is acceptable to say things like:

- 市场可能低估了……
- the market may be underpricing...
- the tail risk here is...

But each such claim should be supported by at least two relevant signals where possible.

### Secondary sections are optional and uneven

Policy, macro, tech, future-news, geopolitics, elections, crypto, and similar dimensions are still useful.

But do not force equal coverage.

Rules:

- if one theme dominates the run, spend most of the report there
- if a secondary theme is weak in the summary, keep it brief
- if a dimension is not meaningfully represented, do not invent a full section just for symmetry

### Evidence discipline

Prefer argument coverage over field coverage.

That means:

- do not mechanically repeat every field in every paragraph
- only cite `yes_prob`, `vol24h`, liquidity, price change, or dates when they help support the point
- after every major judgment, make the basis visible

In other words, the report should implicitly answer:

- what do you think will happen?
- why?

### Tone

Target a report that feels like a sharp internal market note:

- concise but not dry
- analytical but not overblown
- clear about uncertainty
- willing to express a view
- disciplined about evidence

## Examples

**Example 1:**
Input task: "分析一下这些数据。假定我们把 polymarket 当作一个预测市场，你觉得未来会发生什么？依据是什么？请用中文。"

Suggested tool input (skill -> script):

```json
{
  "language": "zh-CN"
}
```

Expected reporting style:

- first show a localized hotspot board
- then lead with a core judgment
- then explain the market consensus, tensions, logic chain, and risks
- do not force balanced four-way sections if one theme clearly dominates

**Example 2:**
Input task: "Give me an English analytical note on what Polymarket currently implies will happen next."

Suggested tool input (skill -> script):

```json
{
  "language": "en-US"
}
```

Expected reporting style:

- concise Markdown
- hotspot board first
- analyst-style judgment, not summary paraphrase
- explicit evidence and caveats
