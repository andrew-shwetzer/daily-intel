"""Signal collector: fetches RSS feeds, scores with Claude, stores in Supabase."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import feedparser
from anthropic import Anthropic

if TYPE_CHECKING:
    from daily_intel.config import Config, Source

logger = logging.getLogger("daily_intel")


def collect_all(config: Config, use_db: bool = True) -> list[dict]:
    """Collect signals from all configured sources.

    Args:
        config: Daily Intel configuration.
        use_db: If True, dedup against DB and store results.
                If False, return scored signals in memory (magic moment mode).

    Returns:
        List of scored signal dicts.
    """
    all_signals = []

    for source in config.sources:
        try:
            raw_entries = _fetch_source(source)
            logger.info(f"Fetched {len(raw_entries)} entries from {source.name}")
        except Exception as e:
            logger.warning(f"Failed to fetch {source.name}: {e}")
            continue

        # Dedup against DB if using database
        if use_db:
            from daily_intel.db import signal_exists
            raw_entries = [e for e in raw_entries if not signal_exists(config, e["url"])]

        if not raw_entries:
            continue

        # Score in batches of 5
        for i in range(0, len(raw_entries), 5):
            batch = raw_entries[i : i + 5]
            scored = _score_batch(config, batch, source)
            for signal in scored:
                if signal["relevance_score"] >= config.scoring.min_relevance:
                    if use_db:
                        from daily_intel.db import insert_signal
                        insert_signal(config, signal)
                    all_signals.append(signal)

    logger.info(f"Collected {len(all_signals)} signals above threshold")
    return all_signals


def _fetch_source(source: Source) -> list[dict]:
    """Fetch and normalize entries from an RSS source."""
    feed = feedparser.parse(source.url)

    if feed.bozo and not feed.entries:
        raise ValueError(f"Feed parse error: {feed.bozo_exception}")

    entries = []
    for entry in feed.entries[:20]:  # Cap at 20 per source per cycle
        url = entry.get("link", "")
        if not url:
            continue

        published = entry.get("published_parsed") or entry.get("updated_parsed")
        published_at = None
        if published:
            try:
                published_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
            except (ValueError, TypeError):
                pass

        entries.append({
            "title": entry.get("title", "").strip(),
            "url": url.strip(),
            "raw_content": (
                entry.get("summary", "") or entry.get("description", "")
            )[:2000],
            "source_name": source.name,
            "source_type": source.source_type,
            "category": source.category,
            "published_at": published_at,
        })

    return entries


def _score_batch(config: Config, entries: list[dict], source: Source) -> list[dict]:
    """Score a batch of entries using Claude."""
    client = Anthropic()

    signals_text = "\n\n".join(
        f"[{i+1}] Title: {e['title']}\nSource: {e['source_name']}\nContent: {e['raw_content'][:500]}"
        for i, e in enumerate(entries)
    )

    prompt = f"""Score these signals for a "{config.niche}" intelligence system.
Company context: {config.description}

For EACH signal, rate:
- relevance (1-10): How relevant to {config.niche}? 9-10=breaking/critical, 7-8=important, 5-6=adjacent, 3-4=loose, 1-2=irrelevant
- urgency (1-5): 5=breaking now, 4=this week, 3=recent trend, 2=evergreen, 1=low
- content_potential (1-5): 5=multiple content pieces, 4=strong single, 3=supporting, 2=minor, 1=archive

Signals:
{signals_text}

Return ONLY a JSON array with one object per signal:
[{{"index": 1, "relevance_score": N, "urgency": N, "content_potential": N, "category": "...", "summary": "2 sentences max", "content_angle": "suggested hook or null"}}]"""

    try:
        response = client.messages.create(
            model=config.scoring.scoring_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        scores = json.loads(text)
    except Exception as e:
        logger.warning(f"Scoring failed for batch: {e}")
        return []

    scored_signals = []
    for score_data in scores:
        idx = score_data.get("index", 0) - 1
        if idx < 0 or idx >= len(entries):
            continue

        entry = entries[idx]
        entry.update({
            "relevance_score": score_data.get("relevance_score", 1),
            "urgency": score_data.get("urgency", 1),
            "content_potential": score_data.get("content_potential", 1),
            "summary": score_data.get("summary", ""),
            "content_angle": score_data.get("content_angle"),
            "category": score_data.get("category", entry["category"]),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })
        scored_signals.append(entry)

    return scored_signals
