# Reality Engine

An AI-powered intelligence newsletter that monitors your niche and delivers a daily editorial brief to your inbox.

Tell it your industry, your competitors, and where you want the brief. It finds the sources, scores every signal with Claude AI, and synthesizes a daily newsletter, delivered to Gmail or Slack.

## How It Works

```
RSS Feeds ────┐
Google News ──┤
Reddit ───────┼── Python Script ── Claude AI Scoring ── Supabase
Competitor    │        (cron)            │                  │
  Blogs ──────┘                          │                  │
                                         ▼                  ▼
                                  Daily Brief Generator
                                      │         │
                                      ▼         ▼
                                Gmail Inbox   Slack Channel
```

1. **Collects** signals from RSS feeds, Google News, Reddit, and competitor blogs
2. **Scores** every signal with Claude on relevance, urgency, and content potential
3. **Synthesizes** the top signals into an editorial brief with content ideas
4. **Delivers** via Gmail (to yourself) or Slack webhook
5. **Stores** everything in Supabase for history and deduplication

## Quick Start (with Claude Code)

If you use [Claude Code](https://docs.anthropic.com/en/docs/claude-code), the setup is fully automated:

```bash
# 1. Clone the repo
git clone https://github.com/andrew-shwetzer/reality-engine.git
cd reality-engine

# 2. Install the package
pip install -e .

# 3. Copy the skill to Claude Code
cp -r skill/SKILL.md ~/.claude/skills/reality-engine/SKILL.md

# 4. Run the skill
# In Claude Code, type: /reality-engine
```

The skill asks 5 questions, researches your niche, provisions your database, and sets up cron. You'll see a live preview of your brief before anything is deployed.

## Manual Setup

### 1. Install

```bash
git clone https://github.com/andrew-shwetzer/reality-engine.git
cd reality-engine
pip install -e .
```

### 2. Set Environment Variables

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # Required
export SUPABASE_URL=https://xxx.supabase.co # Required
export SUPABASE_SERVICE_KEY=eyJ...          # Required (from Supabase dashboard)
export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx    # If using Gmail delivery
export SLACK_WEBHOOK_URL=https://hooks...   # If using Slack delivery
```

### 3. Create Database

Apply the schema to your Supabase project:

```bash
# Paste migrations/001_initial_schema.sql into the Supabase SQL Editor
```

### 4. Create Config

```bash
mkdir -p ~/.reality-engine/instances/my-niche
```

Create `~/.reality-engine/instances/my-niche/config.yaml`:

```yaml
niche: "Your Industry"
company: "Your Company"
description: "What you do in this space"

sources:
  - name: "Industry Blog"
    url: "https://industry-blog.com/feed/"
    source_type: "rss"
    category: "Industry News"
    frequency: "4h"
  - name: "Google News Stream"
    url: "https://news.google.com/rss/search?q=%22your+keyword%22&hl=en-US&gl=US&ceid=US:en"
    source_type: "news_rss"
    category: "Industry News"
    frequency: "4h"
  - name: "Reddit Community"
    url: "https://www.reddit.com/r/yoursub/search/.rss?q=keyword&sort=new&restrict_sr=on"
    source_type: "reddit_rss"
    category: "Community"
    frequency: "12h"

competitors:
  - name: "Competitor A"
    url: "https://competitor-a.com"
    blog_rss: "https://competitor-a.com/blog/feed/"
  - name: "Competitor B"
    url: "https://competitor-b.com"

delivery:
  method: "gmail"  # gmail, slack, or all
  gmail_address: "you@gmail.com"
  slack_webhook_url: "$SLACK_WEBHOOK_URL"  # $ prefix = read from env var
  brief_time: "06:00"
  timezone: "America/New_York"
  collect_interval_hours: 4

scoring:
  min_relevance: 6
  scoring_model: "claude-haiku-4-5-20251001"
  brief_model: "claude-sonnet-4-6"

database:
  supabase_url: "$SUPABASE_URL"
  supabase_key: "$SUPABASE_SERVICE_KEY"
```

### 5. Test

```bash
# Preview a brief without storing anything
reality-engine -i my-niche preview

# Run a full cycle (collect + brief)
reality-engine -i my-niche run

# Check health
reality-engine -i my-niche health
```

### 6. Set Up Cron

```bash
crontab -e
```

Add:
```
# Collect signals every 4 hours
0 */4 * * * cd /path/to/reality-engine && reality-engine -i my-niche collect >> ~/.reality-engine/logs/my-niche.log 2>&1

# Generate and deliver brief at 6 AM
0 6 * * * cd /path/to/reality-engine && reality-engine -i my-niche brief >> ~/.reality-engine/logs/my-niche.log 2>&1
```

## Commands

| Command | What it does |
|---------|-------------|
| `reality-engine -i <slug> collect` | Fetch RSS feeds, score with Claude, store in Supabase |
| `reality-engine -i <slug> brief` | Generate editorial brief, deliver via Gmail/Slack |
| `reality-engine -i <slug> run` | Collect + brief (full daily cycle) |
| `reality-engine -i <slug> preview` | Generate a brief without storing anything |
| `reality-engine -i <slug> health` | Check system status |
| `reality-engine list-instances` | List all configured instances |

## Signal Scoring

Each signal is scored on 3 dimensions (1-5 each):

- **Urgency:** 5 = breaking now, 1 = low priority
- **Relevance:** 5 = core to your niche, 1 = tangential
- **Content Potential:** 5 = multiple content pieces, 1 = archive only

**Composite = Urgency x Relevance x Content Potential** (max 125)

| Score | Priority | Action |
|-------|----------|--------|
| 75+ | P1 | Act today |
| 30-74 | P2 | This week |
| 10-29 | P3 | Backlog |

## Newsletter Design

The daily brief uses a dark HUD aesthetic with:
- Editorial synthesis (AI-generated headline + analysis connecting signals)
- Priority-grouped signals with content angles
- Competitor activity monitoring
- Content ideas derived from signals
- Data points for future content

Customize the template in `reality_engine/templates/brief.html`.

## Gmail App Password Setup

Gmail delivery requires an App Password (not your regular password):

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select "Mail" and your device
3. Copy the 16-character password
4. Set it: `export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx`

## Requirements

- Python 3.10+
- [Anthropic API key](https://console.anthropic.com)
- [Supabase](https://supabase.com) project (free tier works)
- Gmail account (for email delivery) or Slack workspace (for Slack delivery)

## License

MIT
