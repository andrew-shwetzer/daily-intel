# Reality Engine

An AI-powered intelligence monitoring system that watches your industry, scores signals with Claude, and delivers daily newsletter briefs via email and Slack.

Built for [n8n](https://n8n.io) + [Supabase](https://supabase.com) + [Claude API](https://docs.anthropic.com).

## What It Does

1. **Collects** signals from 50+ sources: RSS feeds, Google News, Reddit, page change monitors, and web scrapers
2. **Scores** every signal with Claude AI on relevance, urgency, and content potential (3-axis composite scoring)
3. **Generates** a daily editorial intelligence brief, synthesizing the top signals into actionable insights
4. **Delivers** via HTML email newsletter and Slack digest
5. **Tracks** competitors, content ideas, and data points over time
6. **Self-monitors** with a health check workflow that alerts on failures

## Architecture

```
RSS Feeds ──┐
Google News ─┤
Reddit RSS ──┼──▶ n8n Workflows ──▶ Claude AI Scoring ──▶ Supabase
Page Monitors┤                                               │
Web Scrapers─┘                                               │
                                                              ▼
                                              Daily Brief Generator
                                                    │         │
                                                    ▼         ▼
                                              HTML Email   Slack Digest
```

### 6 n8n Workflows

| Workflow | Trigger | Sources |
|----------|---------|---------|
| WF1: RSS Aggregator | Every 4h | Blog feeds, industry sites, regulatory |
| WF2: News Monitor | Every 4h | Google News RSS keyword streams |
| WF3: Social Monitor | Every 12h | Reddit search feeds |
| WF4: Weekly Scraper | Weekly | Sites without RSS |
| WF5: Brief Generator | Daily 6AM | Supabase query > Claude synthesis > Email + Slack |
| WF6: Health Check | Daily 11PM | n8n execution API > Slack alerts |

### Signal Scoring

Each signal is scored on 3 dimensions (1-5 each):

- **Urgency:** 5 = breaking now, 1 = low priority
- **Relevance:** 5 = core topic, 1 = tangential
- **Content Potential:** 5 = multiple formats possible, 1 = archive only

**Composite = Urgency x Relevance x Content Potential** (max 125)

| Score | Priority | Action |
|-------|----------|--------|
| 75-125 | P1 | Act today |
| 30-74 | P2 | This week |
| 10-29 | P3 | Backlog |
| < 10 | Archive | Skip |

## Prerequisites

- [n8n](https://n8n.io) instance (self-hosted or cloud)
- [Supabase](https://supabase.com) project
- [Anthropic API key](https://console.anthropic.com) (for Claude scoring + brief generation)
- Slack workspace + webhook/bot (for digest delivery)
- Gmail or SMTP credentials (for email delivery)

## Setup

### 1. Database

Apply the schema migration to your Supabase project:

```bash
# Via Supabase CLI
supabase db push migrations/001_initial_schema.sql

# Or paste into Supabase SQL Editor
```

This creates tables for signals, competitors, content pipeline, daily briefs, sources, and feedback.

### 2. Configure Your Instance

Copy the example config and customize for your niche:

```bash
mkdir -p ~/.reality-engine/instances/your-niche
cp examples/config.example.yaml ~/.reality-engine/instances/your-niche/config.yaml
cp examples/sources.example.yaml ~/.reality-engine/instances/your-niche/sources.yaml
cp examples/competitors.example.yaml ~/.reality-engine/instances/your-niche/competitors.yaml
```

Edit each file for your industry, competitors, and sources.

### 3. Seed Sources

After editing your sources config, generate a seed SQL or insert sources via the Supabase API.

### 4. Build n8n Workflows

Follow the detailed build guide in [`n8n-workflows/README.md`](n8n-workflows/README.md). Each workflow has a node-by-node specification with AI prompts included.

### 5. n8n Credentials

| Credential | Type | Used By |
|-----------|------|---------|
| `supabase` | Supabase (Postgres) | All workflows |
| `anthropic-claude` | HTTP Header Auth | WF1, WF2, WF3, WF5 |
| `slack` | Slack OAuth2 | WF5, WF6 |
| `gmail` | Gmail OAuth2 | WF5 |

## File Structure

```
reality-engine/
  README.md                      # This file
  LICENSE                        # MIT
  migrations/
    001_initial_schema.sql       # Supabase schema (tables, indexes, functions)
  n8n-workflows/
    README.md                    # Node-by-node build guide for all 6 workflows
  templates/
    newsletter.html              # HTML email template (Handlebars)
    slack-digest.json            # Slack Block Kit template
  examples/
    config.example.yaml          # Instance configuration
    sources.example.yaml         # Monitored sources
    competitors.example.yaml     # Competitor profiles
  skill/
    SKILL.md                     # Claude Code skill definition (optional)
```

## Claude Code Integration (Optional)

If you use [Claude Code](https://docs.anthropic.com/en/docs/claude-code), copy `skill/SKILL.md` to `~/.claude/skills/reality-engine/SKILL.md` to get interactive commands:

- `/reality-engine` - guided setup for a new instance
- `/reality-engine your-niche status` - check health
- `/reality-engine your-niche brief` - generate on-demand brief
- `/reality-engine your-niche tune` - adjust config

## Customization

### Adding Sources

Add entries to your `sources.yaml` and insert into the `sources` table. The RSS aggregator workflow pulls active sources from the database, so new sources are picked up automatically.

### Adjusting Scoring

Edit the AI scoring prompt in WF1 (see `n8n-workflows/README.md`) to match your niche. The prompt defines what scores 9-10 vs 1-2 for your industry.

### Newsletter Design

The HTML template in `templates/newsletter.html` uses a dark HUD aesthetic. Modify the CSS to match your brand.

### Feedback Loop

Use the `feedback` table to log "more of this" / "less of this" preferences. Include feedback history in the AI scoring prompt to tune relevance over time.

## License

MIT
