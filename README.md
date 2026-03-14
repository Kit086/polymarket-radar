# polymarket-radar

`polymarket-radar` is a read-only skill that scans public Polymarket markets and returns a structured `summary` for downstream AI analysis.

It is designed for a two-stage workflow:

1. A scheduler or cron prompt asks an agent to produce a recurring radar or forecast brief.
2. The agent invokes `polymarket-radar` to gather current market evidence.
3. The skill returns a summary-first artifact.
4. The agent writes the final narrative report from that summary.

The skill is intentionally not the final report writer. Its main job is to turn live Polymarket data into a compact, reusable handoff artifact.

## Layout

```text
.
├── SKILL.md
├── scripts/polymarket_radar.py
├── config/default.json
├── archived/polymarket_radar_test.py
├── evals/evals.json
├── requirements.txt
└── pyproject.toml
```

## Development

This repository uses `uv` for local development, but the skill runtime only needs `python` and `requests`.

Install local dependencies:

```bash
uv sync
```

Run self-tests:

```bash
python scripts/polymarket_radar.py --self-test
```

Run the tool directly:

```bash
python scripts/polymarket_radar.py <<'EOF'
{"language":"zh-CN"}
EOF
```

Include structured output for debugging:

```bash
python scripts/polymarket_radar.py --dump-structured <<'EOF'
{"language":"en-US"}
EOF
```

## Runtime contract

Input:

```json
{
  "language": "zh-CN"
}
```

Optional fields:

- `config_path`: alternate config JSON path
- `config_overrides`: partial config overrides for one run; nested objects are merged with the default config

Output:

```json
{
  "summary": "..."
}
```

The `summary` is the primary artifact for downstream agents. Structured JSON details are only for debugging.

By default, the runtime keeps binary Yes/No markets so the summary consistently carries usable `yes_prob` values.

## Handoff guidance

- Use the returned `summary` as the main input to the downstream reporting step.
- Do not normalize raw JSON as the primary artifact.
- If a run returns no qualifying signals, downstream agents should report a low-signal or no-signal window instead of inventing evidence.
- Use `--dump-structured` only when debugging the runtime or evaluating the skill.

## Notes

- `main.py` has been removed because this repository now targets the skill workflow directly.
- The original prototype is preserved at `archived/polymarket_radar_test.py`.
- `requirements.txt` is exported for non-`uv` environments.
