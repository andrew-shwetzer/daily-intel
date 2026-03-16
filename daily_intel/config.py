"""Configuration loader and validator."""

import os
from pathlib import Path
from dataclasses import dataclass, field

import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".daily-intel"


@dataclass
class Source:
    name: str
    url: str
    source_type: str  # rss, news_rss, reddit_rss, scrape
    category: str
    frequency: str = "4h"


@dataclass
class Competitor:
    name: str
    url: str = ""
    blog_rss: str = ""
    linkedin: str = ""
    services: list = field(default_factory=list)
    notes: str = ""


@dataclass
class DeliveryConfig:
    method: str = "gmail"  # gmail, slack, substack
    gmail_address: str = ""
    slack_webhook_url: str = ""
    substack_api_key: str = ""
    substack_publication_id: str = ""
    brief_time: str = "06:00"
    timezone: str = "America/New_York"
    collect_interval_hours: int = 4


@dataclass
class ScoringConfig:
    min_relevance: int = 6
    scoring_model: str = "claude-haiku-4-5-20251001"
    brief_model: str = "claude-sonnet-4-6"
    p1_threshold: int = 75
    p2_threshold: int = 30
    p3_threshold: int = 10


@dataclass
class DatabaseConfig:
    supabase_url: str = ""
    supabase_key: str = ""


@dataclass
class Config:
    instance_id: str = "default"
    niche: str = ""
    company: str = ""
    description: str = ""
    sources: list = field(default_factory=list)
    competitors: list = field(default_factory=list)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    categories: list = field(default_factory=list)

    @classmethod
    def load(cls, config_path: Path) -> "Config":
        """Load config from YAML file, resolving env vars."""
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        source_fields = {f.name for f in Source.__dataclass_fields__.values()}
        competitor_fields = {f.name for f in Competitor.__dataclass_fields__.values()}
        sources = [Source(**{k: v for k, v in s.items() if k in source_fields}) for s in raw.get("sources", [])]
        competitors = [Competitor(**{k: v for k, v in c.items() if k in competitor_fields}) for c in raw.get("competitors", [])]

        delivery_raw = raw.get("delivery", {})
        delivery = DeliveryConfig(
            method=delivery_raw.get("method", "gmail"),
            gmail_address=delivery_raw.get("gmail_address", ""),
            slack_webhook_url=_resolve_env(delivery_raw.get("slack_webhook_url", "")),
            substack_api_key=_resolve_env(delivery_raw.get("substack_api_key", "")),
            substack_publication_id=delivery_raw.get("substack_publication_id", ""),
            brief_time=delivery_raw.get("brief_time", "06:00"),
            timezone=delivery_raw.get("timezone", "America/New_York"),
            collect_interval_hours=delivery_raw.get("collect_interval_hours", 4),
        )

        scoring_raw = raw.get("scoring", {})
        scoring = ScoringConfig(
            min_relevance=scoring_raw.get("min_relevance", 6),
            scoring_model=scoring_raw.get("scoring_model", "claude-haiku-4-5-20251001"),
            brief_model=scoring_raw.get("brief_model", "claude-sonnet-4-6"),
            p1_threshold=scoring_raw.get("p1_threshold", 75),
            p2_threshold=scoring_raw.get("p2_threshold", 30),
            p3_threshold=scoring_raw.get("p3_threshold", 10),
        )

        db_raw = raw.get("database", {})
        database = DatabaseConfig(
            supabase_url=_resolve_env(db_raw.get("supabase_url", "")),
            supabase_key=_resolve_env(db_raw.get("supabase_key", "")),
        )

        # Derive instance_id from config path directory name
        instance_id = config_path.parent.name if config_path.parent.name != "." else "default"

        return cls(
            instance_id=instance_id,
            niche=raw.get("niche", ""),
            company=raw.get("company", ""),
            description=raw.get("description", ""),
            sources=sources,
            competitors=competitors,
            delivery=delivery,
            scoring=scoring,
            database=database,
            categories=raw.get("categories", []),
        )

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        if not self.niche:
            errors.append("niche is required")
        if not self.sources:
            errors.append("at least one source is required")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            errors.append("ANTHROPIC_API_KEY environment variable not set")
        if self.delivery.method == "gmail" and not self.delivery.gmail_address:
            errors.append("gmail_address required when delivery method is gmail")
        return errors


def _resolve_env(value: str) -> str:
    """If value starts with $, resolve as environment variable."""
    if isinstance(value, str) and value.startswith("$"):
        return os.environ.get(value[1:], "")
    return value
