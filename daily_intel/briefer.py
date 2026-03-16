"""Brief generator: synthesizes signals into editorial intelligence briefs."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from anthropic import Anthropic
from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from daily_intel.config import Config

logger = logging.getLogger("daily_intel")

TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_brief(
    config: Config,
    signals: list[dict] | None = None,
    use_db: bool = True,
) -> dict:
    """Generate a daily intelligence brief.

    Args:
        config: Daily Intel configuration.
        signals: Pre-scored signals (magic moment mode). If None, queries DB.
        use_db: If True, query and update database.

    Returns:
        Dict with keys: html, markdown, slack_blocks, metadata
    """
    if signals is None and use_db:
        from daily_intel.db import get_undelivered_signals
        signals = get_undelivered_signals(config, hours=24)

    if not signals:
        logger.info("No signals to brief on")
        return {"html": "", "markdown": "", "slack_blocks": {}, "metadata": {"signal_count": 0}}

    # Group by priority
    p1 = [s for s in signals if _composite(s) >= config.scoring.p1_threshold]
    p2 = [s for s in signals if config.scoring.p2_threshold <= _composite(s) < config.scoring.p1_threshold]
    p3 = [s for s in signals if config.scoring.p3_threshold <= _composite(s) < config.scoring.p2_threshold]
    competitor_signals = [s for s in signals if "competitor" in s.get("category", "").lower()]

    # Generate editorial synthesis with Claude
    editorial = _generate_editorial(config, signals, p1, competitor_signals)

    # Build template context
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    context = {
        "brief_date": today,
        "brief_number": "",  # Set by caller if tracking
        "signal_count": len(signals),
        "p1_count": len(p1),
        "p2_count": len(p2),
        "competitor_posts": len(competitor_signals),
        "content_ideas": len(editorial.get("content_ideas", [])),
        "editorial_headline": editorial.get("editorial_headline", "Today's Intelligence"),
        "editorial_body": editorial.get("editorial_body", ""),
        "editorial_body_short": editorial.get("editorial_body_short", ""),
        "p1_signals": p1,
        "p2_signals": p2,
        "p3_signals": p3,
        "competitor_activity": editorial.get("competitor_activity", []),
        "content_ideas_list": editorial.get("content_ideas", []),
        "data_points": editorial.get("data_points", []),
        "niche": config.niche,
    }

    # Render HTML
    html = _render_html(context)

    # Render markdown
    markdown = _render_markdown(context)

    # Build Slack blocks
    slack_blocks = _build_slack_blocks(context)

    # Store brief in DB
    if use_db:
        from daily_intel.db import insert_brief, mark_delivered
        insert_brief(config, {
            "brief_date": today,
            "signal_count": len(signals),
            "html_content": html,
            "markdown_content": markdown,
            "slack_content": json.dumps(slack_blocks),
        })
        signal_ids = [s["id"] for s in signals if "id" in s]
        if signal_ids:
            mark_delivered(config, signal_ids, today)

    return {
        "html": html,
        "markdown": markdown,
        "slack_blocks": slack_blocks,
        "metadata": {
            "signal_count": len(signals),
            "p1_count": len(p1),
            "p2_count": len(p2),
            "p3_count": len(p3),
            "editorial_headline": editorial.get("editorial_headline", ""),
        },
    }


def _composite(signal: dict) -> int:
    """Calculate composite score."""
    return (
        signal.get("urgency", 0)
        * signal.get("relevance_score", 0)
        * signal.get("content_potential", 0)
    )


def _generate_editorial(
    config: Config, all_signals: list[dict], p1: list[dict], competitor_signals: list[dict]
) -> dict:
    """Use Claude to generate editorial synthesis."""
    client = Anthropic()

    signals_summary = json.dumps(
        [
            {
                "title": s.get("title", ""),
                "summary": s.get("summary", ""),
                "category": s.get("category", ""),
                "source": s.get("source_name", ""),
                "score": _composite(s),
                "content_angle": s.get("content_angle"),
            }
            for s in all_signals[:30]  # Cap context
        ],
        indent=2,
    )

    prompt = f"""You are the editor of a daily intelligence newsletter about "{config.niche}".
Context: {config.description}

Write like the best intelligence analysts: sharp, opinionated, action-oriented.
Connect dots between signals. Identify what matters and why.

Voice: Authoritative but not stuffy. Data-driven. Occasionally contrarian.
Think Morning Brew meets CIA Presidential Daily Brief.

Given today's {len(all_signals)} signals ({len(p1)} urgent), produce:

1. EDITORIAL HEADLINE: One compelling line capturing today's most important theme.
2. EDITORIAL BODY: 3-4 sentences connecting the biggest signals. What story do they tell?
3. EDITORIAL SHORT: 1-2 sentences for Slack digest.
4. CONTENT IDEAS: 5 specific content ideas. For each: hook (opening line), format (carousel/video/text/blog), why_now.
5. COMPETITOR ACTIVITY: If any competitor signals exist, 2-3 sentences on what they reveal.
6. DATA POINTS: 2-3 specific numbers or stats that could anchor content.

Signals: {signals_summary}

Return JSON:
{{
  "editorial_headline": "string",
  "editorial_body": "string",
  "editorial_body_short": "string",
  "content_ideas": [{{"hook": "", "format": "", "why_now": "", "number": 1}}],
  "competitor_activity": [{{"name": "", "action": ""}}],
  "data_points": [{{"stat": "", "context": ""}}]
}}"""

    try:
        response = client.messages.create(
            model=config.scoring.brief_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extract JSON from response (handle code blocks, preamble)
        match = re.search(r'(\{[\s\S]*\})', text)
        if match:
            text = match.group(1)
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Editorial generation failed: {e}")
        return {
            "editorial_headline": f"{config.niche} Daily Brief",
            "editorial_body": f"Today we collected {len(all_signals)} signals.",
            "editorial_body_short": f"{len(all_signals)} signals collected.",
            "content_ideas": [],
            "competitor_activity": [],
            "data_points": [],
        }


def _render_html(context: dict) -> str:
    """Render HTML brief using Jinja2 template."""
    try:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        template = env.get_template("brief.html")
        return template.render(**context)
    except Exception as e:
        logger.warning(f"HTML rendering failed: {e}")
        return _render_markdown(context)


def _render_markdown(context: dict) -> str:
    """Render markdown brief."""
    lines = [
        f"# {context['niche']} Intelligence Brief",
        f"**{context['brief_date']}** | {context['signal_count']} signals",
        "",
        f"## {context['editorial_headline']}",
        "",
        context["editorial_body"],
        "",
    ]

    if context["p1_signals"]:
        lines.append("## Act Today (P1)")
        lines.append("")
        for s in context["p1_signals"]:
            lines.append(f"### {s.get('title', 'Untitled')}")
            lines.append(f"{s.get('summary', '')}")
            if s.get("content_angle"):
                lines.append(f"> Content angle: {s['content_angle']}")
            lines.append(f"*{s.get('source_name', '')}* | Score: {_composite(s)}")
            lines.append("")

    if context["p2_signals"]:
        lines.append("## This Week (P2)")
        lines.append("")
        for s in context["p2_signals"]:
            lines.append(f"- **{s.get('title', '')}** ({s.get('source_name', '')}): {s.get('summary', '')}")
        lines.append("")

    if context.get("content_ideas_list"):
        lines.append("## Content Ideas")
        lines.append("")
        for idea in context["content_ideas_list"]:
            lines.append(f"{idea.get('number', '-')}. **{idea.get('hook', '')}** ({idea.get('format', '')})")
            lines.append(f"   Why now: {idea.get('why_now', '')}")
        lines.append("")

    if context.get("data_points"):
        lines.append("## Data Points")
        lines.append("")
        for dp in context["data_points"]:
            lines.append(f"- **{dp.get('stat', '')}** - {dp.get('context', '')}")

    return "\n".join(lines)


def _build_slack_blocks(context: dict) -> dict:
    """Build Slack Block Kit message."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Intelligence Brief - {context['brief_date']}"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{context['signal_count']} signals | {context['p1_count']} urgent",
                }
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{context['editorial_headline']}*\n\n{context.get('editorial_body_short', '')}",
            },
        },
    ]

    if context["p1_signals"]:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":red_circle: *ACT TODAY*"},
        })
        for s in context["p1_signals"][:5]:
            title = s.get("title", "Untitled")
            url = s.get("url", "")
            summary = s.get("summary", "")
            source = s.get("source_name", "")
            link = f"<{url}|{title}>" if url else title
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{link}*\n{summary}\n`{source}` | Score: `{_composite(s)}`",
                },
            })

    if context.get("content_ideas_list"):
        blocks.append({"type": "divider"})
        ideas_text = "\n".join(
            f"{idea.get('number', '-')}. {idea.get('hook', '')}" for idea in context["content_ideas_list"][:5]
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":bulb: *Content Ideas*\n{ideas_text}"},
        })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"Daily Intel | {context['niche']}"}],
    })

    return {"blocks": blocks}
