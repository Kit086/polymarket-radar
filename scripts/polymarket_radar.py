#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "default.json"


@dataclass
class RadarConfig:
    mode: str
    tags: List[str]
    exclude_categories: List[str]
    exclude_keywords: List[str]
    order: str
    limit_per_tag: int
    active_only: bool
    closed: bool
    fetch_related_tags: bool
    request_timeout_seconds: int
    sleep_between_requests_seconds: float
    max_events_per_tag: int
    max_markets_per_event: int
    max_global_signals: int
    tag_priority: Dict[str, float]
    rescore_weights: Dict[str, float]
    min_probability_yes: Optional[float]
    max_probability_yes: Optional[float]
    min_volume24hr: Optional[float]
    min_liquidity: Optional[float]
    end_date_grace_days: int
    enable_category_inference: bool
    tag_to_category_fallback: Dict[str, str]
    category_inference_rules: Dict[str, List[str]]
    enable_clob_book_enrichment: bool
    max_clob_book_requests: int
    require_binary_yes_no_market: bool
    gamma_base: str
    clob_base: str
    user_agent: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RadarConfig":
        return cls(
            mode=str(data.get("mode", "radar")),
            tags=[str(item) for item in data.get("tags", [])],
            exclude_categories=[
                str(item).lower() for item in data.get("exclude_categories", [])
            ],
            exclude_keywords=[
                str(item).lower() for item in data.get("exclude_keywords", [])
            ],
            order=str(data.get("order", "volume24hr")),
            limit_per_tag=int(data.get("limit_per_tag", 20)),
            active_only=bool(data.get("active_only", True)),
            closed=bool(data.get("closed", False)),
            fetch_related_tags=bool(data.get("fetch_related_tags", False)),
            request_timeout_seconds=int(data.get("request_timeout_seconds", 20)),
            sleep_between_requests_seconds=float(
                data.get("sleep_between_requests_seconds", 0.2)
            ),
            max_events_per_tag=int(data.get("max_events_per_tag", 5)),
            max_markets_per_event=int(data.get("max_markets_per_event", 1)),
            max_global_signals=int(data.get("max_global_signals", 12)),
            tag_priority={
                str(k): float(v) for k, v in dict(data.get("tag_priority", {})).items()
            },
            rescore_weights={
                str(k): float(v)
                for k, v in dict(data.get("rescore_weights", {})).items()
            },
            min_probability_yes=optional_float(data.get("min_probability_yes")),
            max_probability_yes=optional_float(data.get("max_probability_yes")),
            min_volume24hr=optional_float(data.get("min_volume24hr")),
            min_liquidity=optional_float(data.get("min_liquidity")),
            end_date_grace_days=int(data.get("end_date_grace_days", 1)),
            enable_category_inference=bool(data.get("enable_category_inference", True)),
            tag_to_category_fallback={
                str(k): str(v)
                for k, v in dict(data.get("tag_to_category_fallback", {})).items()
            },
            category_inference_rules={
                str(k): [str(item).lower() for item in values]
                for k, values in dict(data.get("category_inference_rules", {})).items()
            },
            enable_clob_book_enrichment=bool(
                data.get("enable_clob_book_enrichment", False)
            ),
            max_clob_book_requests=int(data.get("max_clob_book_requests", 8)),
            require_binary_yes_no_market=bool(
                data.get("require_binary_yes_no_market", True)
            ),
            gamma_base=str(data.get("gamma_base", "https://gamma-api.polymarket.com")),
            clob_base=str(data.get("clob_base", "https://clob.polymarket.com")),
            user_agent=str(data.get("user_agent", "polymarket-radar-skill/1.0")),
        )


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


def optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == "null":
        return None
    return float(value)


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_today_date() -> date:
    return datetime.now(timezone.utc).date()


def write_stderr(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if math.isclose(min_v, max_v):
        return [1.0 for _ in values] if max_v > 0 else [0.0 for _ in values]
    return [(value - min_v) / (max_v - min_v) for value in values]


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
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def event_is_recent_enough(end_date_value: Optional[str], config: RadarConfig) -> bool:
    parsed_date = parse_iso_datetime_to_date(end_date_value)
    if parsed_date is None:
        return True
    cutoff = utc_today_date() - timedelta(days=config.end_date_grace_days)
    return parsed_date >= cutoff


def probability_passes_filters(
    probability_yes: Optional[float], config: RadarConfig
) -> bool:
    if probability_yes is None:
        return True
    if (
        config.min_probability_yes is not None
        and probability_yes < config.min_probability_yes
    ):
        return False
    if (
        config.max_probability_yes is not None
        and probability_yes > config.max_probability_yes
    ):
        return False
    return True


def quality_passes_filters(
    volume24hr: float, liquidity: float, config: RadarConfig
) -> bool:
    if config.min_volume24hr is not None and volume24hr < config.min_volume24hr:
        return False
    if config.min_liquidity is not None and liquidity < config.min_liquidity:
        return False
    return True


def contains_excluded_keyword(text: str, config: RadarConfig) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in config.exclude_keywords)


def is_chinese(language: str) -> bool:
    lowered = language.lower()
    return lowered.startswith("zh")


def localize_reason(reason_key: str, language: str) -> str:
    zh = {
        "high_recent_market_activity": "近 24 小时市场活跃度高",
        "high_cumulative_market_attention": "累计市场关注度高",
        "significant_recent_probability_movement": "近期隐含概率波动明显",
        "relatively_strong_liquidity": "流动性相对较强",
        "category_inferred_from_text_and_tag_context": "类别由文本和 tag 上下文推断得出",
        "selected_by_combined_radar_score": "由综合雷达评分选出",
    }
    en = {
        "high_recent_market_activity": "high recent market activity",
        "high_cumulative_market_attention": "high cumulative market attention",
        "significant_recent_probability_movement": "significant recent probability movement",
        "relatively_strong_liquidity": "relatively strong liquidity",
        "category_inferred_from_text_and_tag_context": "category inferred from text and tag context",
        "selected_by_combined_radar_score": "selected by combined radar score",
    }
    table = zh if is_chinese(language) else en
    return table.get(reason_key, reason_key)


def infer_category(
    gamma_category: Any,
    tag_context: str,
    event_title: str,
    market_question: str,
    tags: List[Dict[str, Any]],
    config: RadarConfig,
) -> Tuple[Optional[str], str]:
    raw_category = str(gamma_category).strip() if gamma_category is not None else ""
    if raw_category:
        return raw_category, "gamma"

    if not config.enable_category_inference:
        fallback = config.tag_to_category_fallback.get(tag_context)
        return fallback, "tag_fallback" if fallback else "missing"

    parts = [tag_context, event_title, market_question]
    for tag in tags:
        parts.append(str(tag.get("label") or ""))
        parts.append(str(tag.get("slug") or ""))
    haystack = " ".join(parts).lower()

    for inferred_category, keywords in config.category_inference_rules.items():
        if any(keyword in haystack for keyword in keywords):
            return inferred_category, "inferred"

    fallback = config.tag_to_category_fallback.get(tag_context)
    if fallback:
        return fallback, "tag_fallback"
    return None, "missing"


class ApiClient:
    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json",
            }
        )

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        response = self.session.get(
            url, params=params, timeout=self.config.request_timeout_seconds
        )
        response.raise_for_status()
        return response.json()


def validate_order(order: str) -> None:
    allowed = {"volume24hr", "volume"}
    if order not in allowed:
        raise ValueError(
            f"Unsupported order={order!r}. Allowed values: {sorted(allowed)}"
        )


def fetch_events_for_tag(
    client: ApiClient, tag_slug: str, config: RadarConfig
) -> List[Dict[str, Any]]:
    params = {
        "tag_slug": tag_slug,
        "limit": config.limit_per_tag,
        "order": config.order,
        "ascending": "false",
        "related_tags": str(config.fetch_related_tags).lower(),
        "closed": str(config.closed).lower(),
    }
    if config.active_only:
        params["active"] = "true"

    data = client.get_json(f"{config.gamma_base}/events", params=params)
    if not isinstance(data, list):
        raise RuntimeError(
            f"Unexpected /events response for tag={tag_slug}: expected list"
        )
    return data


def fetch_clob_book(
    client: ApiClient, token_id: str, config: RadarConfig
) -> Optional[Dict[str, Any]]:
    try:
        data = client.get_json(
            f"{config.clob_base}/book", params={"token_id": token_id}
        )
    except requests.RequestException:
        return None
    return data if isinstance(data, dict) else None


def event_passes_filters(event: Dict[str, Any], config: RadarConfig) -> bool:
    category = lower_or_empty(event.get("category"))
    title = lower_or_empty(event.get("title"))

    if category in config.exclude_categories:
        return False
    if contains_excluded_keyword(title, config):
        return False

    if not event_is_recent_enough(event.get("endDate"), config):
        return False

    for tag in event.get("tags") or []:
        label = lower_or_empty(tag.get("label"))
        slug = lower_or_empty(tag.get("slug"))
        if label in config.exclude_categories or slug in config.exclude_categories:
            return False
        if contains_excluded_keyword(label, config) or contains_excluded_keyword(
            slug, config
        ):
            return False

    return True


def parse_market_probabilities(
    market: Dict[str, Any],
) -> Tuple[List[str], List[float], Optional[float], Optional[float]]:
    outcomes = safe_json_loads_list(market.get("outcomes"))
    raw_prices = safe_json_loads_list(market.get("outcomePrices"))
    prices = [safe_float(item) for item in raw_prices]

    probability_yes = None
    probability_no = None
    if outcomes and prices and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            label = str(outcome).strip().lower()
            if label == "yes":
                probability_yes = price
            elif label == "no":
                probability_no = price

    return [str(item) for item in outcomes], prices, probability_yes, probability_no


def extract_candidate_signals(
    tag: str,
    events: List[Dict[str, Any]],
    config: RadarConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    filtered_events: List[Dict[str, Any]] = []
    candidate_markets: List[Dict[str, Any]] = []

    for event in events:
        if not event_passes_filters(event, config):
            continue
        filtered_events.append(event)

        event_title = str(event.get("title") or "")
        event_id = str(event.get("id", ""))
        event_slug = event.get("slug")
        gamma_category = event.get("category")
        event_tags = event.get("tags") or []
        event_liquidity = safe_float(event.get("liquidity"))
        event_volume = safe_float(event.get("volume"))
        event_volume24hr = safe_float(event.get("volume24hr"))
        event_open_interest = safe_float(event.get("openInterest"), default=0.0)
        event_end_date = event.get("endDate")

        for market in event.get("markets") or []:
            question = str(market.get("question") or event_title).strip()
            if contains_excluded_keyword(question, config):
                continue

            market_end_date = market.get("endDate") or event_end_date
            if not event_is_recent_enough(market_end_date, config):
                continue

            outcomes, outcome_prices, prob_yes, prob_no = parse_market_probabilities(
                market
            )
            if config.require_binary_yes_no_market and (
                prob_yes is None or prob_no is None
            ):
                continue
            if not probability_passes_filters(prob_yes, config):
                continue

            volume24hr = safe_float(market.get("volume24hr"), default=event_volume24hr)
            volume = safe_float(market.get("volume"), default=event_volume)
            liquidity = safe_float(market.get("liquidity"), default=event_liquidity)
            if not quality_passes_filters(volume24hr, liquidity, config):
                continue

            one_hour = safe_float(market.get("oneHourPriceChange"))
            one_day = safe_float(market.get("oneDayPriceChange"))
            best_bid_raw = market.get("bestBid")
            best_ask_raw = market.get("bestAsk")
            best_bid = safe_float(best_bid_raw) if best_bid_raw is not None else None
            best_ask = safe_float(best_ask_raw) if best_ask_raw is not None else None
            spread = compute_spread(best_bid, best_ask)
            clob_token_ids = [
                str(item) for item in safe_json_loads_list(market.get("clobTokenIds"))
            ]
            resolved_category, category_source = infer_category(
                gamma_category=gamma_category,
                tag_context=tag,
                event_title=event_title,
                market_question=question,
                tags=event_tags,
                config=config,
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


def score_candidates(
    tag: str, candidates: List[Dict[str, Any]], config: RadarConfig, language: str
) -> List[MarketSignal]:
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

    theme_priority = config.tag_priority.get(tag, 0.5)
    weight_volume24 = max(config.rescore_weights.get("volume24hr", 0.0), 0.0)
    weight_volume = max(config.rescore_weights.get("volume", 0.0), 0.0)
    weight_liquidity = max(config.rescore_weights.get("liquidity", 0.0), 0.0)
    weight_move = max(config.rescore_weights.get("oneDayPriceChange", 0.0), 0.0)
    weighted_total = weight_volume24 + weight_volume + weight_liquidity + weight_move
    hot_total = weight_volume24 + weight_volume + weight_liquidity
    results: List[MarketSignal] = []

    for idx, item in enumerate(candidates):
        hot_components = (
            weight_volume24 * n_vol24[idx]
            + weight_volume * n_vol[idx]
            + weight_liquidity * n_liq[idx]
        )
        hot_score = hot_components / hot_total if hot_total > 0 else 0.0
        momentum_score = n_move[idx]
        weighted_market_score = (
            (hot_components + weight_move * momentum_score) / weighted_total
            if weighted_total > 0
            else 0.0
        )
        signal_score = 0.85 * weighted_market_score + 0.15 * theme_priority

        why_selected: List[str] = []
        if n_vol24[idx] >= 0.7:
            why_selected.append(
                localize_reason("high_recent_market_activity", language)
            )
        if n_vol[idx] >= 0.7:
            why_selected.append(
                localize_reason("high_cumulative_market_attention", language)
            )
        if n_move[idx] >= 0.7:
            why_selected.append(
                localize_reason("significant_recent_probability_movement", language)
            )
        if n_liq[idx] >= 0.7:
            why_selected.append(
                localize_reason("relatively_strong_liquidity", language)
            )
        if item.get("category_source") == "inferred":
            why_selected.append(
                localize_reason("category_inferred_from_text_and_tag_context", language)
            )
        if not why_selected:
            why_selected.append(
                localize_reason("selected_by_combined_radar_score", language)
            )

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

    results.sort(key=lambda signal: signal.signal_score, reverse=True)
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


def build_output(
    tag_reports: List[TagReport], config: RadarConfig, language: str
) -> Dict[str, Any]:
    all_signals: List[MarketSignal] = []
    for report in tag_reports:
        all_signals.extend(report.selected_signals)

    all_signals.sort(key=lambda signal: signal.signal_score, reverse=True)
    global_signals = unique_top_signals(
        all_signals, per_event_limit=1, global_limit=config.max_global_signals
    )

    return {
        "meta": {
            "generated_at": utc_now_iso(),
            "language": language,
            "mode": config.mode,
            "source": "Polymarket Gamma API + optional CLOB public book",
            "config": {
                "tags": config.tags,
                "exclude_categories": sorted(config.exclude_categories),
                "order": config.order,
                "limit_per_tag": config.limit_per_tag,
                "active_only": config.active_only,
                "closed": config.closed,
                "fetch_related_tags": config.fetch_related_tags,
                "max_events_per_tag": config.max_events_per_tag,
                "max_markets_per_event": config.max_markets_per_event,
                "max_global_signals": config.max_global_signals,
                "min_probability_yes": config.min_probability_yes,
                "max_probability_yes": config.max_probability_yes,
                "min_volume24hr": config.min_volume24hr,
                "min_liquidity": config.min_liquidity,
                "end_date_grace_days": config.end_date_grace_days,
                "enable_category_inference": config.enable_category_inference,
                "enable_clob_book_enrichment": config.enable_clob_book_enrichment,
                "require_binary_yes_no_market": config.require_binary_yes_no_market,
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
    }


def format_probability(value: Optional[float]) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"


def format_change(value: Any) -> str:
    number = safe_float(value)
    return f"{number:+.4f}"


def build_human_summary(output: Dict[str, Any]) -> str:
    meta = output["meta"]
    chinese = is_chinese(meta["language"])
    lines: List[str] = []

    if chinese:
        lines.extend(
            [
                "Polymarket 热点雷达摘要",
                "=" * 80,
                f"生成时间: {meta['generated_at']}",
                f"用户语言: {meta['language']}",
                f"模式: {meta['mode']}",
                f"查询 tags: {', '.join(meta['config']['tags'])}",
                f"排序方式: {meta['config']['order']}",
                "",
                "分 tag 重点事件",
                "-" * 80,
            ]
        )
    else:
        lines.extend(
            [
                "Polymarket Radar Summary",
                "=" * 80,
                f"Generated at: {meta['generated_at']}",
                f"Language: {meta['language']}",
                f"Mode: {meta['mode']}",
                f"Tags: {', '.join(meta['config']['tags'])}",
                f"Order: {meta['config']['order']}",
                "",
                "Per-tag highlights",
                "-" * 80,
            ]
        )

    for tag_report in output["tag_reports"]:
        if chinese:
            lines.append(
                f"[{tag_report['tag']}] 扫描事件={tag_report['total_events_scanned']} 过滤后={tag_report['total_events_after_filtering']}"
            )
        else:
            lines.append(
                f"[{tag_report['tag']}] scanned={tag_report['total_events_scanned']} filtered={tag_report['total_events_after_filtering']}"
            )
        if not tag_report["selected_signals"]:
            lines.append(
                "  - 无符合条件的重点信号。"
                if chinese
                else "  - No qualifying signals."
            )
            lines.append("")
            continue
        for idx, signal in enumerate(tag_report["selected_signals"], start=1):
            lines.append(f"  {idx}. {signal['event_title']}")
            if chinese:
                lines.append(f"     question: {signal['market_question']}")
                lines.append(
                    f"     category: {signal.get('category') or 'n/a'} ({signal.get('category_source', 'missing')})"
                )
                lines.append(
                    f"     yes_prob: {format_probability(signal.get('probability_yes'))} | score={signal['signal_score']:.3f} | vol24h={safe_float(signal.get('volume24hr')):.2f}"
                )
                lines.append(
                    f"     liquidity: {safe_float(signal.get('liquidity')):.2f} | one_day_price_change: {format_change(signal.get('one_day_price_change'))} | end_date: {signal.get('end_date') or 'n/a'}"
                )
                lines.append(
                    "     why_selected: "
                    + ("; ".join(signal.get("why_selected") or []) or "n/a")
                )
            else:
                lines.append(f"     question: {signal['market_question']}")
                lines.append(
                    f"     category: {signal.get('category') or 'n/a'} ({signal.get('category_source', 'missing')})"
                )
                lines.append(
                    f"     yes_prob: {format_probability(signal.get('probability_yes'))} | score={signal['signal_score']:.3f} | vol24h={safe_float(signal.get('volume24hr')):.2f}"
                )
                lines.append(
                    f"     liquidity: {safe_float(signal.get('liquidity')):.2f} | one_day_price_change: {format_change(signal.get('one_day_price_change'))} | end_date: {signal.get('end_date') or 'n/a'}"
                )
                lines.append(
                    "     why_selected: "
                    + ("; ".join(signal.get("why_selected") or []) or "n/a")
                )
        lines.append("")

    lines.append("全局 Top signals" if chinese else "Global top signals")
    lines.append("-" * 80)
    if not output["global_summary_candidates"]:
        lines.append(
            "  - 当前没有符合条件的跨 tag 全局重点信号。"
            if chinese
            else "  - No qualifying cross-tag signals in this run."
        )
    for idx, signal in enumerate(output["global_summary_candidates"], start=1):
        lines.append(f"  {idx}. [{signal['tag_context']}] {signal['market_question']}")
        lines.append(
            f"     category: {signal.get('category') or 'n/a'} ({signal.get('category_source', 'missing')})"
        )
        lines.append(
            f"     yes_prob: {format_probability(signal.get('probability_yes'))} | score={signal['signal_score']:.3f} | vol24h={safe_float(signal.get('volume24hr')):.2f}"
        )
        lines.append(
            f"     liquidity: {safe_float(signal.get('liquidity')):.2f} | one_day_price_change: {format_change(signal.get('one_day_price_change'))} | end_date: {signal.get('end_date') or 'n/a'}"
        )
        lines.append(
            "     why_selected: "
            + ("; ".join(signal.get("why_selected") or []) or "n/a")
        )

    return "\n".join(lines)


def run_pipeline(config: RadarConfig, language: str) -> Dict[str, Any]:
    validate_order(config.order)
    client = ApiClient(config)
    tag_reports: List[TagReport] = []
    clob_enrich_budget = config.max_clob_book_requests

    for tag in config.tags:
        events = fetch_events_for_tag(client, tag, config)
        filtered_events, candidate_markets = extract_candidate_signals(
            tag, events, config
        )
        scored = score_candidates(tag, candidate_markets, config, language)
        chosen = unique_top_signals(
            scored,
            per_event_limit=config.max_markets_per_event,
            global_limit=config.max_events_per_tag,
        )

        if config.enable_clob_book_enrichment and clob_enrich_budget > 0:
            for signal in chosen:
                if clob_enrich_budget <= 0:
                    break
                if not signal.clob_token_ids:
                    continue
                book = fetch_clob_book(client, signal.clob_token_ids[0], config)
                if book:
                    signal.clob_book = book
                    clob_enrich_budget -= 1
                    time.sleep(config.sleep_between_requests_seconds)

        tag_reports.append(
            TagReport(
                tag=tag,
                total_events_scanned=len(events),
                total_events_after_filtering=len(filtered_events),
                selected_signals=chosen,
            )
        )
        time.sleep(config.sleep_between_requests_seconds)

    return build_output(tag_reports, config, language)


def load_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: Path) -> RadarConfig:
    return RadarConfig.from_dict(load_json_file(path))


def parse_runtime_input(stdin_text: str) -> Dict[str, Any]:
    text = stdin_text.strip()
    if not text:
        raise ValueError(
            'Expected JSON input on stdin, for example {"language": "zh-CN"}.'
        )
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Runtime input must be a JSON object.")
    language = payload.get("language")
    if not isinstance(language, str) or not language.strip():
        raise ValueError(
            "Runtime input must include a non-empty string field: language."
        )
    return payload


def deep_merge_dicts(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def merge_overrides(
    config_data: Dict[str, Any], overrides: Dict[str, Any]
) -> Dict[str, Any]:
    filtered = {key: value for key, value in overrides.items() if key != "language"}
    return deep_merge_dicts(config_data, filtered)


def run_self_tests() -> int:
    failures: List[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    config = load_config(DEFAULT_CONFIG_PATH)

    check(safe_float("1.25") == 1.25, "safe_float should parse numeric strings")
    check(
        safe_float("bad", default=7.0) == 7.0,
        "safe_float should return default on bad strings",
    )
    check(
        safe_json_loads_list('["Yes", "No"]') == ["Yes", "No"],
        "safe_json_loads_list should parse lists",
    )
    check(
        safe_json_loads_list("not-json") == [],
        "safe_json_loads_list should reject invalid json",
    )
    check(
        math.isclose(compute_spread(0.2, 0.7) or 0.0, 0.5),
        "compute_spread should compute ask-bid",
    )
    check(
        compute_spread(None, 0.7) is None, "compute_spread should handle missing values"
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
        "date parsing should work",
    )
    check(
        probability_passes_filters(0.5, config) is True, "mid probability should pass"
    )
    check(
        probability_passes_filters(0.001, config) is False,
        "low probability should fail",
    )
    check(
        probability_passes_filters(0.999, config) is False,
        "high probability should fail",
    )
    check(
        quality_passes_filters(2000.0, 20000.0, config) is True,
        "quality filters should allow strong markets",
    )
    check(
        quality_passes_filters(10.0, 20000.0, config) is False,
        "quality filters should reject low volume",
    )
    check(
        quality_passes_filters(2000.0, 5.0, config) is False,
        "quality filters should reject low liquidity",
    )

    check(
        event_passes_filters(
            {
                "category": "Politics",
                "title": "Fed cuts rates",
                "tags": [],
                "endDate": None,
            },
            config,
        )
        is True,
        "event_passes_filters should accept non-sports events",
    )
    check(
        event_passes_filters(
            {"category": "Sports", "title": "NBA finals", "tags": [], "endDate": None},
            config,
        )
        is False,
        "event_passes_filters should reject sports",
    )
    check(
        event_passes_filters(
            {"category": "Politics", "title": "NBA odds", "tags": [], "endDate": None},
            config,
        )
        is False,
        "event_passes_filters should reject keywords",
    )

    outcomes, prices, prob_yes, prob_no = parse_market_probabilities(
        {"outcomes": '["Yes", "No"]', "outcomePrices": '["0.61", "0.39"]'}
    )
    check(
        outcomes == ["Yes", "No"], "parse_market_probabilities should return outcomes"
    )
    check(prices == [0.61, 0.39], "parse_market_probabilities should return prices")
    check(
        prob_yes == 0.61 and prob_no == 0.39,
        "parse_market_probabilities should map yes/no",
    )

    inferred_category, inferred_source = infer_category(
        gamma_category=None,
        tag_context="economy",
        event_title="Fed decision in March",
        market_question="Will the Fed cut rates?",
        tags=[],
        config=config,
    )
    check(
        inferred_category == "Economy",
        "infer_category should provide a fallback category",
    )
    check(
        inferred_source in {"inferred", "tag_fallback"},
        "infer_category should record source",
    )

    merged_config = merge_overrides(
        {
            "tag_priority": {"economy": 1.0, "tech": 0.8},
            "rescore_weights": {"volume24hr": 0.45, "volume": 0.15},
        },
        {"tag_priority": {"tech": 0.95}, "rescore_weights": {"volume": 0.25}},
    )
    check(
        merged_config
        == {
            "tag_priority": {"economy": 1.0, "tech": 0.95},
            "rescore_weights": {"volume24hr": 0.45, "volume": 0.25},
        },
        "merge_overrides should deep merge nested dictionaries",
    )

    strict_config_data = load_json_file(DEFAULT_CONFIG_PATH)
    strict_config_data["require_binary_yes_no_market"] = True
    strict_config = RadarConfig.from_dict(strict_config_data)
    _, strict_candidates = extract_candidate_signals(
        "crypto",
        [
            {
                "id": "event-1",
                "title": "Binary market",
                "slug": "binary-market",
                "category": "Crypto",
                "tags": [],
                "liquidity": 25000,
                "volume": 10000,
                "volume24hr": 5000,
                "openInterest": 1000,
                "endDate": None,
                "markets": [
                    {
                        "id": "market-binary",
                        "question": "Will Bitcoin reach $120k?",
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.61", "0.39"]',
                        "volume24hr": 5000,
                        "volume": 10000,
                        "liquidity": 25000,
                        "oneDayPriceChange": 0.08,
                    },
                    {
                        "id": "market-non-binary",
                        "question": "Bitcoin Up or Down today?",
                        "outcomes": '["Up", "Down"]',
                        "outcomePrices": '["0.51", "0.49"]',
                        "volume24hr": 5000,
                        "volume": 10000,
                        "liquidity": 25000,
                        "oneDayPriceChange": 0.08,
                    },
                ],
            }
        ],
        strict_config,
    )
    check(
        len(strict_candidates) == 1
        and strict_candidates[0]["market_id"] == "market-binary",
        "extract_candidate_signals should drop non-binary markets when configured",
    )

    summary_text = build_human_summary(
        {
            "meta": {
                "generated_at": "2026-03-13T00:00:00+00:00",
                "language": "zh-CN",
                "mode": "radar",
                "config": {"tags": ["economy"], "order": "volume24hr"},
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
                            "why_selected": ["近 24 小时市场活跃度高"],
                        }
                    ],
                }
            ],
            "global_summary_candidates": [],
        }
    )
    check("why_selected:" in summary_text, "summary should include why_selected")
    check(
        "one_day_price_change:" in summary_text,
        "summary should include one_day_price_change",
    )
    check("end_date:" in summary_text, "summary should include end_date")
    check("liquidity:" in summary_text, "summary should include liquidity")

    empty_summary_text = build_human_summary(
        {
            "meta": {
                "generated_at": "2026-03-13T00:00:00+00:00",
                "language": "en-US",
                "mode": "radar",
                "config": {"tags": ["crypto"], "order": "volume24hr"},
            },
            "tag_reports": [
                {
                    "tag": "crypto",
                    "total_events_scanned": 5,
                    "total_events_after_filtering": 0,
                    "selected_signals": [],
                }
            ],
            "global_summary_candidates": [],
        }
    )
    check(
        "No qualifying signals." in empty_summary_text,
        "summary should explain empty tag results",
    )
    check(
        "No qualifying cross-tag signals in this run." in empty_summary_text,
        "summary should explain empty global results",
    )

    if failures:
        for failure in failures:
            write_stderr(f"SELF-TEST FAILED: {failure}")
        return 1

    print("Self-tests passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket radar skill tool")
    parser.add_argument(
        "--self-test", action="store_true", help="Run built-in self tests and exit"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to the default JSON config file",
    )
    parser.add_argument(
        "--dump-structured",
        action="store_true",
        help="Include the structured radar payload together with the summary for debugging",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_tests()

    try:
        runtime_input = parse_runtime_input(sys.stdin.read())
        config_path = (
            Path(runtime_input.get("config_path") or args.config).expanduser().resolve()
        )
        config_data = load_json_file(config_path)
        overrides = runtime_input.get("config_overrides")
        if overrides is not None:
            if not isinstance(overrides, dict):
                raise ValueError(
                    "config_overrides must be a JSON object when provided."
                )
            config_data = merge_overrides(config_data, overrides)
        config = RadarConfig.from_dict(config_data)
        output = run_pipeline(config, runtime_input["language"])
        summary = build_human_summary(output)
        payload: Dict[str, Any] = {"summary": summary}
        if args.dump_structured:
            payload["structured_output"] = output
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    except requests.HTTPError as exc:
        write_stderr(f"HTTP error: {exc}")
        return 1
    except requests.RequestException as exc:
        write_stderr(f"Network error: {exc}")
        return 1
    except json.JSONDecodeError as exc:
        write_stderr(f"Invalid JSON input: {exc}")
        return 1
    except Exception as exc:
        write_stderr(f"Unhandled error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
