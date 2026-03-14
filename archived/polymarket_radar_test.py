#!/usr/bin/env python3
"""
Polymarket radar test script

Purpose:
- Query Polymarket Gamma API by tag
- Collect candidate events and markets for future-news / policy / macro radar use cases
- Re-rank signals using market-level fields
- Output structured JSON for an AI agent to read and turn into a report

Notes:
- This script is read-only. It does not trade.
- It currently supports order values: volume24hr, volume
- In practice: volume24hr works, volume_24hr does NOT work.
- Language is only stored in output metadata for downstream report generation.

Python: 3.10+
Dependencies: requests

Usage:
    python polymarket_radar_test.py

Optional:
    python polymarket_radar_test.py --json-out radar_output.json
    python polymarket_radar_test.py --print-summary
    python polymarket_radar_test.py --summary-out radar_summary.txt
    python polymarket_radar_test.py --self-test
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

# ============================================================
# Config area
# Treat these variables as your future config file.
# Every config item below includes a comment describing its purpose.
# ============================================================

# Language hint for the downstream AI agent.
# The collector itself remains language-agnostic and only stores this in output metadata.
USER_LANGUAGE = "zh-CN"

# High-level operating mode for future extensions.
# Current script does not branch heavily by mode yet, but it is exposed for downstream usage.
MODE = "radar"  # radar | macro | policy | tech

# Tags to query independently from Gamma /events.
# Results are merged in memory after each tag is fetched.
INCLUDE_TAGS = [
    "politics",
    "economy",
    "world",
    "tech",
    "crypto",
]

# Event categories that should always be excluded.
# This is a hard block based on explicit category names when available.
EXCLUDE_CATEGORIES = {
    "sports",
}

# Keywords that should cause exclusion when found in event titles, market questions, or tag labels.
# Useful when category is missing or unreliable.
EXCLUDE_KEYWORDS = [
    "nba",
    "nfl",
    "mlb",
    "nhl",
    "soccer",
    "tennis",
    "golf",
    "march madness",
    "champions league",
    "mavericks",
    "grizzlies",
]

# Allowed sort order for Gamma /events requests.
# Supported values in this script: volume24hr, volume.
ORDER = "volume24hr"

# Number of events to request per tag before local filtering and rescoring.
LIMIT_PER_TAG = 20

# Whether to request only active events from Gamma.
ACTIVE_ONLY = True

# Whether to request closed events from Gamma.
# For a future-looking radar this normally stays False.
CLOSED = False

# Whether Gamma should include related tags when filtering by tag_slug.
FETCH_RELATED_TAGS = False

# HTTP timeout in seconds for each API request.
REQUEST_TIMEOUT_SECONDS = 20

# Pause between requests to reduce burstiness.
SLEEP_BETWEEN_REQUESTS_SECONDS = 0.2

# Number of final signals to keep per tag after scoring and deduplication.
MAX_EVENTS_PER_TAG = 5

# Maximum number of markets to keep per event.
# Set to 1 to make the output more event-centric and avoid repeated sub-markets.
MAX_MARKETS_PER_EVENT = 1

# Maximum number of cross-tag signals to keep in the global summary section.
MAX_GLOBAL_SIGNALS = 12

# Theme priority multiplier by queried tag.
# Higher values make that tag slightly more likely to surface in ranking.
TAG_PRIORITY = {
    "politics": 1.00,
    "economy": 1.00,
    "world": 0.95,
    "tech": 0.85,
    "crypto": 0.80,
}

# Weights used when building the hot-score from market data.
# These are normalized internally before combination.
RESCORE_WEIGHTS = {
    "volume24hr": 0.45,
    "volume": 0.15,
    "oneDayPriceChange": 0.25,
    "liquidity": 0.15,
}

# Minimum acceptable probability_yes for a market to survive filtering.
# Use None to disable this lower-bound filter.
MIN_PROBABILITY_YES: Optional[float] = 0.05

# Maximum acceptable probability_yes for a market to survive filtering.
# Use None to disable this upper-bound filter.
MAX_PROBABILITY_YES: Optional[float] = 0.95

# Minimum 24h volume required for a market to survive filtering.
# Use None to disable the filter.
MIN_VOLUME24HR: Optional[float] = 1000.0

# Minimum liquidity required for a market to survive filtering.
# Use None to disable the filter.
MIN_LIQUIDITY: Optional[float] = 10000.0

# Keep events whose end_date is on or after (today - END_DATE_GRACE_DAYS).
# Example: 1 means yesterday is still allowed, older events are removed.
END_DATE_GRACE_DAYS = 1

# When true, missing event category values are replaced with an inferred category.
# The inferred value uses tag context, event title, market question, and event tags.
ENABLE_CATEGORY_INFERENCE = True

# Optional mapping from queried tag to a preferred fallback category label.
# Used when Gamma category is missing and keyword-based inference is inconclusive.
TAG_TO_CATEGORY_FALLBACK = {
    "politics": "Politics",
    "economy": "Economy",
    "world": "World",
    "tech": "Tech",
    "crypto": "Crypto",
}

# Keyword rules for inferred category assignment when Gamma category is null.
# More specific domains should appear before broader political vocabulary.
# First matching category wins.
CATEGORY_INFERENCE_RULES = {
    "Economy": [
        "fed",
        "interest rate",
        "inflation",
        "cpi",
        "ppi",
        "recession",
        "gdp",
        "jobs",
        "unemployment",
        "treasury",
        "yield",
        "cut rates",
        "rate cut",
        "central bank",
    ],
    "World": [
        "iran",
        "china",
        "taiwan",
        "ukraine",
        "russia",
        "nato",
        "strait of hormuz",
        "ceasefire",
        "sanction",
        "war",
        "missile",
        "border",
        "israel",
        "gaza",
        "lebanon",
    ],
    "Tech": [
        "openai",
        "anthropic",
        "xai",
        "gpt",
        "claude",
        "deepseek",
        "ai model",
        "ipo",
        "acquired",
        "acquisition",
        "sp 500",
        "semiconductor",
        "nvidia",
        "tesla",
        "amazon",
        "apple",
        "meta",
        "google",
    ],
    "Crypto": [
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "solana",
        "crypto",
        "token",
        "etf",
        "stablecoin",
    ],
    "Politics": [
        "election",
        "parliament",
        "president",
        "prime minister",
        "senate",
        "house",
        "vote",
        "coalition",
        "government",
        "minister",
        "campaign",
        "party",
        "tariff",
        "policy",
        "regulation",
        "mayor",
        "nominee",
    ],
}

# Optional: fetch CLOB order book for top signals only.
ENABLE_CLOB_BOOK_ENRICHMENT = False

# Maximum number of CLOB /book enrichments in one run.
MAX_CLOB_BOOK_REQUESTS = 8

# APIs
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
USER_AGENT = "polymarket-radar-test/0.4"


# ============================================================
# Data models
# ============================================================


@dataclass
class MarketSignal:
    market_id: str
    event_id: str
    event_title: str
    event_slug: Optional[str]
    tag_context: str
    category: Optional[str]
    category_source: str
    market_question: str
    probability_yes: Optional[float]
    probability_no: Optional[float]
    outcomes: List[str]
    outcome_prices: List[float]
    volume24hr: float
    volume: float
    liquidity: float
    one_hour_price_change: float
    one_day_price_change: float
    best_bid: Optional[float]
    best_ask: Optional[float]
    spread: Optional[float]
    end_date: Optional[str]
    open_interest: Optional[float]
    clob_token_ids: List[str]
    signal_score: float
    hot_score: float
    momentum_score: float
    theme_priority: float
    why_selected: List[str]
    source: Dict[str, Any]
    clob_book: Optional[Dict[str, Any]] = None


@dataclass
class TagReport:
    tag: str
    total_events_scanned: int
    total_events_after_filtering: int
    selected_signals: List[MarketSignal]


# ============================================================
# Utility helpers
# ============================================================


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_today_date() -> date:
    return datetime.now(timezone.utc).date()


def write_stderr(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            return default
    return default


def safe_json_loads_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def lower_or_empty(value: Any) -> str:
    return str(value).lower() if value is not None else ""


def contains_excluded_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in EXCLUDE_KEYWORDS)


def normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if math.isclose(min_v, max_v):
        return [1.0 for _ in values] if max_v > 0 else [0.0 for _ in values]
    return [(v - min_v) / (max_v - min_v) for v in values]


def compute_spread(
    best_bid: Optional[float], best_ask: Optional[float]
) -> Optional[float]:
    if best_bid is None or best_ask is None:
        return None
    if best_bid < 0 or best_ask < 0:
        return None
    return max(best_ask - best_bid, 0.0)


def parse_iso_datetime_to_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def event_is_recent_enough(end_date_value: Optional[str]) -> bool:
    parsed_date = parse_iso_datetime_to_date(end_date_value)
    if parsed_date is None:
        return True
    cutoff = utc_today_date() - timedelta(days=END_DATE_GRACE_DAYS)
    return parsed_date >= cutoff


def probability_passes_filters(probability_yes: Optional[float]) -> bool:
    if probability_yes is None:
        return True
    if MIN_PROBABILITY_YES is not None and probability_yes < MIN_PROBABILITY_YES:
        return False
    if MAX_PROBABILITY_YES is not None and probability_yes > MAX_PROBABILITY_YES:
        return False
    return True


def quality_passes_filters(volume24hr: float, liquidity: float) -> bool:
    if MIN_VOLUME24HR is not None and volume24hr < MIN_VOLUME24HR:
        return False
    if MIN_LIQUIDITY is not None and liquidity < MIN_LIQUIDITY:
        return False
    return True


def infer_category(
    gamma_category: Any,
    tag_context: str,
    event_title: str,
    market_question: str,
    tags: List[Dict[str, Any]],
) -> Tuple[Optional[str], str]:
    raw_category = str(gamma_category).strip() if gamma_category is not None else ""
    if raw_category:
        return raw_category, "gamma"

    if not ENABLE_CATEGORY_INFERENCE:
        fallback = TAG_TO_CATEGORY_FALLBACK.get(tag_context)
        return fallback, "tag_fallback" if fallback else "missing"

    parts = [tag_context, event_title, market_question]
    for tag in tags:
        parts.append(str(tag.get("label") or ""))
        parts.append(str(tag.get("slug") or ""))
    haystack = " ".join(parts).lower()

    for inferred_category, keywords in CATEGORY_INFERENCE_RULES.items():
        if any(keyword in haystack for keyword in keywords):
            return inferred_category, "inferred"

    fallback = TAG_TO_CATEGORY_FALLBACK.get(tag_context)
    if fallback:
        return fallback, "tag_fallback"
    return None, "missing"


# ============================================================
# HTTP client
# ============================================================


class ApiClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            }
        )

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()


# ============================================================
# Polymarket queries
# ============================================================


def validate_order(order: str) -> None:
    allowed = {"volume24hr", "volume"}
    if order not in allowed:
        raise ValueError(
            f"Unsupported ORDER={order!r}. Allowed values: {sorted(allowed)}"
        )


def fetch_events_for_tag(client: ApiClient, tag_slug: str) -> List[Dict[str, Any]]:
    params = {
        "tag_slug": tag_slug,
        "limit": LIMIT_PER_TAG,
        "order": ORDER,
        "ascending": "false",
        "related_tags": str(FETCH_RELATED_TAGS).lower(),
    }
    if ACTIVE_ONLY:
        params["active"] = "true"
    params["closed"] = str(CLOSED).lower()

    url = f"{GAMMA_BASE}/events"
    data = client.get_json(url, params=params)
    if not isinstance(data, list):
        raise RuntimeError(
            f"Unexpected /events response for tag={tag_slug}: expected list"
        )
    return data


def fetch_clob_book(client: ApiClient, token_id: str) -> Optional[Dict[str, Any]]:
    url = f"{CLOB_BASE}/book"
    try:
        data = client.get_json(url, params={"token_id": token_id})
        if isinstance(data, dict):
            return data
        return None
    except requests.RequestException:
        return None


# ============================================================
# Filtering and scoring
# ============================================================


def event_passes_filters(event: Dict[str, Any]) -> bool:
    category = lower_or_empty(event.get("category"))
    title = lower_or_empty(event.get("title"))

    if category in EXCLUDE_CATEGORIES:
        return False
    if contains_excluded_keyword(title):
        return False

    event_end_date = event.get("endDate")
    if not event_is_recent_enough(event_end_date):
        return False

    tags = event.get("tags") or []
    for tag in tags:
        label = lower_or_empty(tag.get("label"))
        slug = lower_or_empty(tag.get("slug"))
        if label in EXCLUDE_CATEGORIES or slug in EXCLUDE_CATEGORIES:
            return False
        if contains_excluded_keyword(label) or contains_excluded_keyword(slug):
            return False

    return True


def parse_market_probabilities(
    market: Dict[str, Any],
) -> Tuple[List[str], List[float], Optional[float], Optional[float]]:
    outcomes = safe_json_loads_list(market.get("outcomes"))
    raw_prices = safe_json_loads_list(market.get("outcomePrices"))
    prices = [safe_float(x) for x in raw_prices]

    probability_yes = None
    probability_no = None
    if outcomes and prices and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            label = str(outcome).strip().lower()
            if label == "yes":
                probability_yes = price
            elif label == "no":
                probability_no = price

    return [str(x) for x in outcomes], prices, probability_yes, probability_no


def extract_candidate_signals(
    tag: str, events: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    filtered_events: List[Dict[str, Any]] = []
    candidate_markets: List[Dict[str, Any]] = []

    for event in events:
        if not event_passes_filters(event):
            continue
        filtered_events.append(event)

        event_title = event.get("title") or ""
        event_id = str(event.get("id", ""))
        event_slug = event.get("slug")
        gamma_category = event.get("category")
        event_tags = event.get("tags") or []
        event_liquidity = safe_float(event.get("liquidity"))
        event_volume = safe_float(event.get("volume"))
        event_volume24hr = safe_float(event.get("volume24hr"))
        event_open_interest = safe_float(event.get("openInterest"), default=0.0)
        end_date = event.get("endDate")

        markets = event.get("markets") or []
        for market in markets:
            question = str(market.get("question") or event_title).strip()
            if contains_excluded_keyword(question):
                continue

            market_end_date = market.get("endDate") or end_date
            if not event_is_recent_enough(market_end_date):
                continue

            outcomes, outcome_prices, prob_yes, prob_no = parse_market_probabilities(
                market
            )
            if not probability_passes_filters(prob_yes):
                continue

            volume24hr = safe_float(market.get("volume24hr"), default=event_volume24hr)
            volume = safe_float(market.get("volume"), default=event_volume)
            liquidity = safe_float(market.get("liquidity"), default=event_liquidity)
            if not quality_passes_filters(volume24hr, liquidity):
                continue

            one_hour = safe_float(market.get("oneHourPriceChange"))
            one_day = safe_float(market.get("oneDayPriceChange"))
            best_bid_val = market.get("bestBid")
            best_ask_val = market.get("bestAsk")
            best_bid = safe_float(best_bid_val) if best_bid_val is not None else None
            best_ask = safe_float(best_ask_val) if best_ask_val is not None else None
            spread = compute_spread(best_bid, best_ask)
            clob_token_ids = [
                str(x) for x in safe_json_loads_list(market.get("clobTokenIds"))
            ]
            resolved_category, category_source = infer_category(
                gamma_category=gamma_category,
                tag_context=tag,
                event_title=event_title,
                market_question=question,
                tags=event_tags,
            )

            candidate_markets.append(
                {
                    "market_id": str(market.get("id", "")),
                    "event_id": event_id,
                    "event_title": event_title,
                    "event_slug": event_slug,
                    "tag_context": tag,
                    "category": resolved_category,
                    "category_source": category_source,
                    "market_question": question,
                    "probability_yes": prob_yes,
                    "probability_no": prob_no,
                    "outcomes": outcomes,
                    "outcome_prices": outcome_prices,
                    "volume24hr": volume24hr,
                    "volume": volume,
                    "liquidity": liquidity,
                    "oneHourPriceChange": one_hour,
                    "oneDayPriceChange": one_day,
                    "bestBid": best_bid,
                    "bestAsk": best_ask,
                    "spread": spread,
                    "endDate": market_end_date,
                    "openInterest": event_open_interest,
                    "clobTokenIds": clob_token_ids,
                    "source": {
                        "event_url": f"https://polymarket.com/event/{event_slug}"
                        if event_slug
                        else None,
                        "gamma_event_id": event_id,
                        "gamma_market_id": str(market.get("id", "")),
                    },
                }
            )

    return filtered_events, candidate_markets


def score_candidates(tag: str, candidates: List[Dict[str, Any]]) -> List[MarketSignal]:
    if not candidates:
        return []

    vol24_list = [safe_float(item.get("volume24hr")) for item in candidates]
    vol_list = [safe_float(item.get("volume")) for item in candidates]
    liq_list = [safe_float(item.get("liquidity")) for item in candidates]
    move_list = [abs(safe_float(item.get("oneDayPriceChange"))) for item in candidates]

    n_vol24 = normalize(vol24_list)
    n_vol = normalize(vol_list)
    n_liq = normalize(liq_list)
    n_move = normalize(move_list)

    theme_priority = TAG_PRIORITY.get(tag, 0.5)
    results: List[MarketSignal] = []

    for idx, item in enumerate(candidates):
        hot_score = (
            RESCORE_WEIGHTS["volume24hr"] * n_vol24[idx]
            + RESCORE_WEIGHTS["volume"] * n_vol[idx]
            + RESCORE_WEIGHTS["liquidity"] * n_liq[idx]
        )
        momentum_score = n_move[idx]
        signal_score = 0.50 * hot_score + 0.30 * momentum_score + 0.20 * theme_priority

        why_selected: List[str] = []
        if n_vol24[idx] >= 0.7:
            why_selected.append("high recent market activity")
        if n_vol[idx] >= 0.7:
            why_selected.append("high cumulative market attention")
        if n_move[idx] >= 0.7:
            why_selected.append("significant recent probability movement")
        if n_liq[idx] >= 0.7:
            why_selected.append("relatively strong liquidity")
        if item.get("category_source") == "inferred":
            why_selected.append("category inferred from text and tag context")
        if not why_selected:
            why_selected.append("selected by combined radar score")

        results.append(
            MarketSignal(
                market_id=item["market_id"],
                event_id=item["event_id"],
                event_title=item["event_title"],
                event_slug=item.get("event_slug"),
                tag_context=item["tag_context"],
                category=item.get("category"),
                category_source=item.get("category_source", "missing"),
                market_question=item["market_question"],
                probability_yes=item.get("probability_yes"),
                probability_no=item.get("probability_no"),
                outcomes=item.get("outcomes", []),
                outcome_prices=item.get("outcome_prices", []),
                volume24hr=safe_float(item.get("volume24hr")),
                volume=safe_float(item.get("volume")),
                liquidity=safe_float(item.get("liquidity")),
                one_hour_price_change=safe_float(item.get("oneHourPriceChange")),
                one_day_price_change=safe_float(item.get("oneDayPriceChange")),
                best_bid=item.get("bestBid"),
                best_ask=item.get("bestAsk"),
                spread=item.get("spread"),
                end_date=item.get("endDate"),
                open_interest=item.get("openInterest"),
                clob_token_ids=item.get("clobTokenIds", []),
                signal_score=round(signal_score, 6),
                hot_score=round(hot_score, 6),
                momentum_score=round(momentum_score, 6),
                theme_priority=round(theme_priority, 6),
                why_selected=why_selected,
                source=item.get("source", {}),
            )
        )

    results.sort(key=lambda x: x.signal_score, reverse=True)
    return results


def unique_top_signals(
    signals: List[MarketSignal], per_event_limit: int, global_limit: int
) -> List[MarketSignal]:
    chosen: List[MarketSignal] = []
    event_counts: Dict[str, int] = {}

    for signal in signals:
        count = event_counts.get(signal.event_id, 0)
        if count >= per_event_limit:
            continue
        chosen.append(signal)
        event_counts[signal.event_id] = count + 1
        if len(chosen) >= global_limit:
            break
    return chosen


# ============================================================
# Report assembly
# ============================================================


def build_output(tag_reports: List[TagReport]) -> Dict[str, Any]:
    all_signals: List[MarketSignal] = []
    for report in tag_reports:
        all_signals.extend(report.selected_signals)

    all_signals.sort(key=lambda x: x.signal_score, reverse=True)
    global_signals = unique_top_signals(
        all_signals, per_event_limit=1, global_limit=MAX_GLOBAL_SIGNALS
    )

    return {
        "meta": {
            "generated_at": utc_now_iso(),
            "language": USER_LANGUAGE,
            "mode": MODE,
            "source": "Polymarket Gamma API + optional CLOB public book",
            "config": {
                "include_tags": INCLUDE_TAGS,
                "exclude_categories": sorted(EXCLUDE_CATEGORIES),
                "order": ORDER,
                "limit_per_tag": LIMIT_PER_TAG,
                "active_only": ACTIVE_ONLY,
                "closed": CLOSED,
                "fetch_related_tags": FETCH_RELATED_TAGS,
                "max_events_per_tag": MAX_EVENTS_PER_TAG,
                "max_markets_per_event": MAX_MARKETS_PER_EVENT,
                "max_global_signals": MAX_GLOBAL_SIGNALS,
                "min_probability_yes": MIN_PROBABILITY_YES,
                "max_probability_yes": MAX_PROBABILITY_YES,
                "min_volume24hr": MIN_VOLUME24HR,
                "min_liquidity": MIN_LIQUIDITY,
                "end_date_grace_days": END_DATE_GRACE_DAYS,
                "enable_category_inference": ENABLE_CATEGORY_INFERENCE,
                "enable_clob_book_enrichment": ENABLE_CLOB_BOOK_ENRICHMENT,
            },
        },
        "tag_reports": [
            {
                "tag": report.tag,
                "total_events_scanned": report.total_events_scanned,
                "total_events_after_filtering": report.total_events_after_filtering,
                "selected_signals": [
                    asdict(signal) for signal in report.selected_signals
                ],
            }
            for report in tag_reports
        ],
        "global_summary_candidates": [asdict(signal) for signal in global_signals],
        "guidance_for_agent": {
            "report_sections": [
                "overview",
                "per-tag signal summary",
                "market evidence",
                "interpretation",
                "AI judgement",
                "cross-tag conclusion",
                "uncertainty and caveats",
            ],
            "caveats": [
                "Polymarket probabilities are market-implied probabilities, not confirmed facts.",
                "Low-liquidity markets can produce noisier signals.",
                "High activity does not guarantee high predictive accuracy.",
                "Some categories may be inferred when Gamma does not provide one.",
            ],
        },
    }


def build_human_summary(output: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("Polymarket Radar Test Summary")
    lines.append("=" * 80)
    meta = output["meta"]
    lines.append(f"Generated at: {meta['generated_at']}")
    lines.append(f"Language:     {meta['language']}")
    lines.append(f"Mode:         {meta['mode']}")
    lines.append(f"Tags:         {', '.join(meta['config']['include_tags'])}")
    lines.append(f"Order:        {meta['config']['order']}")
    lines.append("")

    for tag_report in output["tag_reports"]:
        lines.append(
            f"[{tag_report['tag']}] scanned={tag_report['total_events_scanned']} filtered={tag_report['total_events_after_filtering']}"
        )
        for idx, signal in enumerate(tag_report["selected_signals"], start=1):
            prob_yes = signal.get("probability_yes")
            prob_text = (
                f"{prob_yes:.1%}" if isinstance(prob_yes, (int, float)) else "n/a"
            )
            day_change = safe_float(signal.get("one_day_price_change"))
            why_selected = signal.get("why_selected") or []
            why_selected_text = (
                "; ".join(str(x) for x in why_selected) if why_selected else "n/a"
            )
            lines.append(f"  {idx}. {signal['event_title']}")
            lines.append(f"     question: {signal['market_question']}")
            lines.append(
                f"     category: {signal.get('category') or 'n/a'} ({signal.get('category_source', 'missing')})"
            )
            lines.append(
                f"     yes_prob: {prob_text} | score={signal['signal_score']:.3f} | vol24h={signal['volume24hr']:.2f}"
            )
            lines.append(
                f"     liquidity: {safe_float(signal.get('liquidity')):.2f} | "
                f"one_day_price_change: {day_change:+.4f} | end_date: {signal.get('end_date') or 'n/a'}"
            )
            lines.append(f"     why_selected: {why_selected_text}")
        lines.append("")

    lines.append("Top global signals:")
    for idx, signal in enumerate(output["global_summary_candidates"], start=1):
        prob_yes = signal.get("probability_yes")
        prob_text = f"{prob_yes:.1%}" if isinstance(prob_yes, (int, float)) else "n/a"
        day_change = safe_float(signal.get("one_day_price_change"))
        why_selected = signal.get("why_selected") or []
        why_selected_text = (
            "; ".join(str(x) for x in why_selected) if why_selected else "n/a"
        )
        lines.append(f"  {idx}. [{signal['tag_context']}] {signal['market_question']}")
        lines.append(
            f"     category: {signal.get('category') or 'n/a'} ({signal.get('category_source', 'missing')})"
        )
        lines.append(
            f"     yes={prob_text} | score={signal['signal_score']:.3f} | "
            f"vol24h={safe_float(signal.get('volume24hr')):.2f}"
        )
        lines.append(
            f"     liquidity: {safe_float(signal.get('liquidity')):.2f} | "
            f"one_day_price_change: {day_change:+.4f} | end_date: {signal.get('end_date') or 'n/a'}"
        )
        lines.append(f"     why_selected: {why_selected_text}")

    return "\n".join(lines)


def print_human_summary(output: Dict[str, Any]) -> None:
    print(build_human_summary(output))


# ============================================================
# Self tests
# ============================================================


def run_self_tests() -> int:
    failures: List[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(safe_float("1.25") == 1.25, "safe_float should parse numeric strings")
    check(
        safe_float("bad", default=7.0) == 7.0,
        "safe_float should return default on invalid strings",
    )
    check(
        safe_json_loads_list('["Yes", "No"]') == ["Yes", "No"],
        "safe_json_loads_list should parse JSON lists",
    )
    check(
        safe_json_loads_list("not-json") == [],
        "safe_json_loads_list should return empty list on invalid JSON",
    )
    check(
        math.isclose(compute_spread(0.2, 0.7) or 0.0, 0.5, rel_tol=1e-9, abs_tol=1e-9),
        "compute_spread should compute ask-bid",
    )
    check(
        compute_spread(None, 0.7) is None,
        "compute_spread should return None for missing values",
    )
    check(
        normalize([5.0, 5.0]) == [1.0, 1.0],
        "normalize should handle equal positive values",
    )
    check(
        normalize([0.0, 0.0]) == [0.0, 0.0], "normalize should handle equal zero values"
    )
    check(
        parse_iso_datetime_to_date("2026-03-13T16:00:00Z") == date(2026, 3, 13),
        "parse_iso_datetime_to_date should parse Z timestamps",
    )
    check(
        probability_passes_filters(0.5) is True,
        "probability_passes_filters should allow mid-range probabilities",
    )
    check(
        probability_passes_filters(0.001) is False,
        "probability_passes_filters should reject low probabilities",
    )
    check(
        probability_passes_filters(0.999) is False,
        "probability_passes_filters should reject high probabilities",
    )
    check(
        quality_passes_filters(2000.0, 20000.0) is True,
        "quality_passes_filters should allow strong markets",
    )
    check(
        quality_passes_filters(10.0, 20000.0) is False,
        "quality_passes_filters should reject low volume24hr",
    )
    check(
        quality_passes_filters(2000.0, 5.0) is False,
        "quality_passes_filters should reject low liquidity",
    )

    check(
        event_passes_filters(
            {
                "category": "Politics",
                "title": "Fed cuts rates",
                "tags": [],
                "endDate": None,
            }
        )
        is True,
        "event_passes_filters should accept non-sports events",
    )
    check(
        event_passes_filters(
            {"category": "Sports", "title": "NBA finals", "tags": [], "endDate": None}
        )
        is False,
        "event_passes_filters should reject sports category",
    )
    check(
        event_passes_filters(
            {"category": "Politics", "title": "NBA odds", "tags": [], "endDate": None}
        )
        is False,
        "event_passes_filters should reject excluded keywords",
    )
    old_date = (utc_today_date() - timedelta(days=END_DATE_GRACE_DAYS + 1)).isoformat()
    check(
        event_passes_filters(
            {
                "category": "Politics",
                "title": "Old event",
                "tags": [],
                "endDate": f"{old_date}T00:00:00Z",
            }
        )
        is False,
        "event_passes_filters should reject events older than grace window",
    )
    yesterday_date = (
        utc_today_date() - timedelta(days=END_DATE_GRACE_DAYS)
    ).isoformat()
    check(
        event_passes_filters(
            {
                "category": "Politics",
                "title": "Yesterday event",
                "tags": [],
                "endDate": f"{yesterday_date}T00:00:00Z",
            }
        )
        is True,
        "event_passes_filters should keep yesterday within grace window",
    )

    outcomes, prices, prob_yes, prob_no = parse_market_probabilities(
        {"outcomes": '["Yes", "No"]', "outcomePrices": '["0.61", "0.39"]'}
    )
    check(
        outcomes == ["Yes", "No"],
        "parse_market_probabilities should return parsed outcomes",
    )
    check(
        prices == [0.61, 0.39], "parse_market_probabilities should return parsed prices"
    )
    check(
        prob_yes == 0.61 and prob_no == 0.39,
        "parse_market_probabilities should map yes/no probabilities",
    )

    inferred_category, inferred_source = infer_category(
        gamma_category=None,
        tag_context="economy",
        event_title="Fed decision in March",
        market_question="Will the Fed cut rates?",
        tags=[],
    )
    check(
        inferred_category == "Economy"
        and inferred_source in {"inferred", "tag_fallback"},
        "infer_category should provide a usable fallback category",
    )

    summary_text = build_human_summary(
        {
            "meta": {
                "generated_at": "2026-03-13T00:00:00+00:00",
                "language": "zh-CN",
                "mode": "radar",
                "config": {"include_tags": ["economy"], "order": "volume24hr"},
            },
            "tag_reports": [
                {
                    "tag": "economy",
                    "total_events_scanned": 1,
                    "total_events_after_filtering": 1,
                    "selected_signals": [
                        {
                            "event_title": "Fed decision in April?",
                            "market_question": "Will there be no change in Fed interest rates after the April 2026 meeting?",
                            "category": "Economy",
                            "category_source": "inferred",
                            "probability_yes": 0.915,
                            "signal_score": 0.55,
                            "volume24hr": 147281.02,
                            "liquidity": 119216.66,
                            "one_day_price_change": 0.02,
                            "end_date": "2026-04-29T00:00:00Z",
                            "why_selected": ["high recent market activity"],
                        }
                    ],
                }
            ],
            "global_summary_candidates": [],
        }
    )
    check(
        "why_selected:" in summary_text,
        "build_human_summary should include why_selected",
    )
    check(
        "one_day_price_change:" in summary_text,
        "build_human_summary should include one_day_price_change",
    )
    check("end_date:" in summary_text, "build_human_summary should include end_date")
    check("liquidity:" in summary_text, "build_human_summary should include liquidity")

    sample_candidates = [
        {
            "market_id": "1",
            "event_id": "e1",
            "event_title": "Fed cut by June",
            "event_slug": "fed-cut-by-june",
            "tag_context": "economy",
            "category": "Economy",
            "category_source": "gamma",
            "market_question": "Will the Fed cut by June?",
            "probability_yes": 0.63,
            "probability_no": 0.37,
            "outcomes": ["Yes", "No"],
            "outcome_prices": [0.63, 0.37],
            "volume24hr": 1000.0,
            "volume": 5000.0,
            "liquidity": 70000.0,
            "oneHourPriceChange": 0.03,
            "oneDayPriceChange": 0.11,
            "bestBid": 0.62,
            "bestAsk": 0.64,
            "spread": 0.02,
            "endDate": "2026-06-30T00:00:00Z",
            "openInterest": 1200.0,
            "clobTokenIds": ["t1", "t2"],
            "source": {},
        },
        {
            "market_id": "2",
            "event_id": "e2",
            "event_title": "OpenAI launches model",
            "event_slug": "openai-launches-model",
            "tag_context": "tech",
            "category": "Tech",
            "category_source": "gamma",
            "market_question": "Will OpenAI launch a new model?",
            "probability_yes": 0.42,
            "probability_no": 0.58,
            "outcomes": ["Yes", "No"],
            "outcome_prices": [0.42, 0.58],
            "volume24hr": 100.0,
            "volume": 800.0,
            "liquidity": 80.0,
            "oneHourPriceChange": 0.01,
            "oneDayPriceChange": 0.01,
            "bestBid": 0.41,
            "bestAsk": 0.43,
            "spread": 0.02,
            "endDate": "2026-12-31T00:00:00Z",
            "openInterest": 500.0,
            "clobTokenIds": ["t3", "t4"],
            "source": {},
        },
    ]
    scored = score_candidates("economy", sample_candidates)
    check(len(scored) == 2, "score_candidates should return all candidates")
    check(
        scored[0].signal_score >= scored[1].signal_score,
        "score_candidates should sort descending by score",
    )

    unique = unique_top_signals(scored + scored, per_event_limit=1, global_limit=10)
    unique_event_ids = [signal.event_id for signal in unique]
    check(
        unique_event_ids.count("e1") == 1,
        "unique_top_signals should limit one signal per event when requested",
    )

    if failures:
        for failure in failures:
            write_stderr(f"SELF-TEST FAILED: {failure}")
        return 1

    print("Self-tests passed.")
    return 0


# ============================================================
# Main pipeline
# ============================================================


def run_pipeline() -> Dict[str, Any]:
    validate_order(ORDER)
    client = ApiClient()
    tag_reports: List[TagReport] = []

    clob_enrich_budget = MAX_CLOB_BOOK_REQUESTS

    for tag in INCLUDE_TAGS:
        events = fetch_events_for_tag(client, tag)
        filtered_events, candidate_markets = extract_candidate_signals(tag, events)
        scored = score_candidates(tag, candidate_markets)
        chosen = unique_top_signals(
            scored,
            per_event_limit=MAX_MARKETS_PER_EVENT,
            global_limit=MAX_EVENTS_PER_TAG,
        )

        if ENABLE_CLOB_BOOK_ENRICHMENT and clob_enrich_budget > 0:
            for signal in chosen:
                if clob_enrich_budget <= 0:
                    break
                if not signal.clob_token_ids:
                    continue
                book = fetch_clob_book(client, signal.clob_token_ids[0])
                if book:
                    signal.clob_book = book
                    clob_enrich_budget -= 1
                    time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

        tag_reports.append(
            TagReport(
                tag=tag,
                total_events_scanned=len(events),
                total_events_after_filtering=len(filtered_events),
                selected_signals=chosen,
            )
        )

        time.sleep(SLEEP_BETWEEN_REQUESTS_SECONDS)

    return build_output(tag_reports)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket radar test script")
    parser.add_argument(
        "--json-out", dest="json_out", default=None, help="Write output JSON to a file"
    )
    parser.add_argument(
        "--print-summary",
        dest="print_summary",
        action="store_true",
        help="Print a readable terminal summary",
    )
    parser.add_argument(
        "--summary-out",
        dest="summary_out",
        default=None,
        help="Write the readable summary to a text file",
    )
    parser.add_argument(
        "--self-test",
        dest="self_test",
        action="store_true",
        help="Run built-in self-tests and exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.self_test:
        return run_self_tests()

    try:
        output = run_pipeline()
    except requests.HTTPError as exc:
        write_stderr(f"HTTP error: {exc}")
        return 1
    except requests.RequestException as exc:
        write_stderr(f"Network error: {exc}")
        return 1
    except Exception as exc:
        write_stderr(f"Unhandled error: {exc}")
        return 1

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    summary_text: Optional[str] = None
    if args.print_summary or args.summary_out:
        summary_text = build_human_summary(output)

    if args.summary_out:
        with open(args.summary_out, "w", encoding="utf-8") as f:
            f.write(summary_text or "")
            if summary_text and not summary_text.endswith("\n"):
                f.write("\n")

    if args.print_summary:
        print()
        print(summary_text or "")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
