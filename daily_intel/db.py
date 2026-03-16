"""Supabase database operations."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from daily_intel.config import Config

logger = logging.getLogger("daily_intel")

_client = None
_client_url = None


def get_client(config: Config):
    """Get or create Supabase client. Recreates if config URL changes."""
    global _client, _client_url
    if _client is None or _client_url != config.database.supabase_url:
        from supabase import create_client
        _client = create_client(config.database.supabase_url, config.database.supabase_key)
        _client_url = config.database.supabase_url
    return _client


def url_hash(instance_id: str, url: str) -> str:
    """MD5 hash of instance_id:URL for deduplication (matches DB generated column)."""
    return hashlib.md5(f"{instance_id}:{url}".encode()).hexdigest()


def signal_exists(config: Config, url: str) -> bool:
    """Check if a signal URL already exists in the database."""
    client = get_client(config)
    h = url_hash(config.instance_id, url)
    result = client.table("signals").select("id").eq("url_hash", h).execute()
    return len(result.data) > 0


def insert_signal(config: Config, signal: dict) -> dict | None:
    """Insert a signal into the database. Returns the inserted row or None on conflict."""
    client = get_client(config)
    signal = {**signal, "instance_id": config.instance_id}
    try:
        result = client.table("signals").upsert(
            signal,
            on_conflict="url_hash",
            ignore_duplicates=True,
        ).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Failed to insert signal: {e}")
        return None


def get_undelivered_signals(config: Config, hours: int = 24) -> list[dict]:
    """Get undelivered signals from the last N hours, scored above threshold."""
    client = get_client(config)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = (
        client.table("signals")
        .select("*")
        .eq("instance_id", config.instance_id)
        .eq("delivered", False)
        .eq("archived", False)
        .gte("relevance_score", config.scoring.min_relevance)
        .gte("collected_at", cutoff.isoformat())
        .order("composite_score", desc=True)
        .execute()
    )
    return result.data


def mark_delivered(config: Config, signal_ids: list[int], brief_date: str) -> None:
    """Mark signals as delivered for a specific brief."""
    client = get_client(config)
    client.table("signals").update(
        {"delivered": True, "brief_date": brief_date}
    ).in_("id", signal_ids).execute()


def insert_brief(config: Config, brief: dict) -> dict | None:
    """Insert a daily brief record."""
    client = get_client(config)
    brief = {**brief, "instance_id": config.instance_id}
    try:
        result = client.table("daily_briefs").upsert(
            brief, on_conflict="instance_id,brief_date", ignore_duplicates=True
        ).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Failed to insert brief: {e}")
        return None


def get_signal_count_today(config: Config) -> int:
    """Get count of signals collected today."""
    client = get_client(config)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = (
        client.table("signals")
        .select("id", count="exact")
        .eq("instance_id", config.instance_id)
        .gte("collected_at", f"{today}T00:00:00Z")
        .execute()
    )
    return result.count or 0


def get_source_stats(config: Config) -> dict:
    """Get signal counts by source type."""
    client = get_client(config)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = (
        client.table("signals")
        .select("source_type")
        .eq("instance_id", config.instance_id)
        .gte("collected_at", f"{today}T00:00:00Z")
        .execute()
    )
    stats = {}
    for row in result.data:
        st = row["source_type"]
        stats[st] = stats.get(st, 0) + 1
    return stats
