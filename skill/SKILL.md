---
name: daily-intel
description: |
  Build your own AI-powered intelligence newsletter. Monitors any niche via RSS, scores signals
  with Claude, and delivers a daily editorial brief to your inbox or Slack. Full auto-setup:
  asks 6 questions, researches your niche, provisions Supabase, generates config, shows a live
  sample brief, and sets up cron. Everything runs on your machine. Supports personal mode
  (Gmail/Slack delivery) and audience mode (Beehiiv drafts for newsletter publishers).
argument-hint: "[new | <slug> status | <slug> brief | <slug> tune | list]"
model: claude-opus-4-6
user_invocable: true
---

# /daily-intel -- Your Personal Intelligence Newsletter

You build a custom AI-powered intelligence newsletter for any niche in one session. 6 questions, then everything is auto-provisioned: database, sources, config, cron schedule. The user sees a live sample brief before committing.

## When NOT to Use

- One-off research questions (use `/research`)
- Niches with fewer than 3 identifiable sources (not enough signal volume)

## Architecture

```
~/.daily-intel/
  instances/
    <slug>/
      config.yaml          <- full configuration (generated)
      briefs/              <- archived briefs
        YYYY-MM-DD.md
```

The Python package `daily_intel` runs on the user's machine via cron:
- `daily-intel collect` - fetch RSS, score with Claude, store in Supabase
- `daily-intel brief` - generate editorial brief, deliver via Gmail/Slack/Beehiiv
- `daily-intel run` - collect + brief (full daily cycle)
- `daily-intel health` - check system status
- `daily-intel preview` - generate a brief without storing anything

## Command Routing

```python
if no args or args == "new":
    -> ONBOARDING (6 questions + auto-setup)
elif args == "list":
    -> list instances
elif args[0] matches existing instance:
    if args[1] == "status": -> show health
    elif args[1] == "brief": -> run preview command
    elif args[1] == "tune": -> interactive config adjustment
    else: -> show help
else:
    -> "Instance not found"
```

---

## ONBOARDING FLOW (6 Questions)

When the user runs `/daily-intel` or `/daily-intel new`, run this conversational flow. Be warm, direct, and helpful. Suggest smart defaults.

### Prerequisites Check

Before starting, verify:
1. `ANTHROPIC_API_KEY` is set. If not: "You'll need an Anthropic API key. Get one at console.anthropic.com, then set it: `export ANTHROPIC_API_KEY=sk-...`"
2. The `daily-intel` Python package is installed. Check with: `python -m daily_intel --help`. If not installed: "Let's install the package first: `pip install -e /path/to/daily-intel`"

### Question 1: Mode
"Is this for your own intelligence, or are you building a newsletter for an audience?"

Options:
- **Personal** ("I want to stay on top of my niche"): mode = `personal`, delivery defaults to Gmail
- **Audience** ("I want to publish a newsletter for subscribers"): mode = `audience`, delivery defaults to Beehiiv

Save as `mode`.

### Question 2: Your Niche
"What niche or industry do you want to monitor? Be specific."

Examples to help them narrow:
- Not "technology" but "AI developer tools"
- Not "healthcare" but "telehealth platforms for mental health"
- Not "finance" but "DeFi lending protocols"

Save as `niche`.

### Question 3: Your Role
"What do you do in this space? One line is fine."

This tunes relevance scoring. A founder monitoring competitors needs different signals than a content creator looking for trends.

Save as `description`.

### Question 4: Competitors
"Who are your top 3 competitors? Drop names, URLs, or say 'find them for me'."

If "find them for me": deploy a research agent (subagent_type: general-purpose, model: sonnet) to research the niche and find 5-8 competitors with URLs, blog URLs, RSS feeds. Validate each RSS feed with a test fetch.

Save as `competitors`.

### Question 5: Delivery
"Where should your daily brief go?"

Delivery options depend on mode:

**Personal mode:**
- **Gmail** (default): "What's your Gmail address? You'll need a Google App Password (not your regular password). I'll show you how to set that up."
- **Any SMTP**: "Got a custom mail server? Drop the smtp_host and smtp_port and I'll configure it."
- **Slack**: "Drop a Slack webhook URL, or I can walk you through creating one."
- **Both Gmail and Slack**: Collect both.

**Audience mode:**
- **Beehiiv** (default): "Drop your Beehiiv API key and publication ID. I'll set it up to auto-create drafts -- you publish from your Beehiiv dashboard when ready."
- **Slack** (in addition to Beehiiv): "Want a Slack ping when a new draft is ready? Drop a Slack webhook URL."

Save as `delivery`.

### Question 6: Schedule
"What time should your brief arrive? (default: 6:00 AM)"

Also ask timezone if not obvious from system. Save as `schedule`.

---

## AUTO-SETUP (After 6 Questions)

### Step 1: Research Sources

Deploy 2 research agents in parallel:

**Agent A -- Industry Sources:**
"For the niche '{niche}', find 15-20 monitoring sources. Include:
- Industry blogs with RSS feeds (check /feed, /rss, /blog/feed)
- Google News RSS keyword streams (construct URLs)
- Reddit communities (construct search RSS URLs)
- Regulatory/legal sources if relevant
- Trade publications

For each: name, URL, RSS feed URL, category, and whether you verified the feed loads.
Return as YAML list. Never fabricate URLs."

**Agent B -- Competitor Intelligence:**
"For these competitors in the '{niche}' space: {competitor_list}
For each competitor: find their blog URL, check for RSS feed (/feed, /rss, /blog/feed, /atom.xml),
find their LinkedIn company page. Verify each URL loads.
Return as YAML list."

### Step 2: Validate Sources

After research agents return, validate ALL discovered RSS feeds by actually fetching them:
```python
import feedparser
feed = feedparser.parse(url)
# Keep only feeds that return entries and don't have bozo errors
```

Remove dead feeds. Report: "Found X sources, Y validated, Z removed (dead feeds)."

### Step 3: Magic Moment

**This is the key experience.** Before provisioning anything permanent, show the user what their newsletter will look like with real data.

1. Fetch the top 10 validated RSS feeds
2. Collect the most recent entries
3. Score them with Claude using the user's niche context
4. Generate an editorial brief
5. Display the markdown brief right in the terminal

Say: "Here's a preview of what your daily brief will look like, using live data from your sources:"

Then display the brief.

Then ask: "Like what you see? Ready to set up the full system?"

If yes, continue. If they want adjustments (more sources, different categories, different voice), adjust and re-preview.

### Step 4: Provision Supabase

Use the Supabase MCP tools:

1. `list_organizations` - get org ID
2. `list_projects` - check if user has an existing project they want to use
3. If new project needed:
   a. `get_cost` with type "project"
   b. Show cost to user, ask for confirmation
   c. `confirm_cost` to get confirmation ID
   d. `create_project` with name "daily-intel-{slug}", region closest to user
   e. Poll `get_project` until status is active (may take 2-3 minutes)
4. `get_project_url` - get the API URL
5. `get_publishable_keys` - get the anon key
6. `apply_migration` with the schema SQL from migrations/001_initial_schema.sql
7. Seed sources using `execute_sql` with INSERT statements generated from validated sources

**Important:** The service role key is NOT available via MCP. Tell the user:
"Your Supabase project is set up. You'll need to grab the service role key from your Supabase dashboard (Settings > API > service_role key) and set it as an environment variable:
`export SUPABASE_SERVICE_KEY=your-key-here`"

Also have them set: `export SUPABASE_URL=https://xxx.supabase.co`

### Step 5: Generate Config

Generate `~/.daily-intel/instances/{slug}/config.yaml` with all discovered sources, competitors, delivery settings, scoring config, and mode baked in.

The config must include `mode: personal` or `mode: audience` at the top level.

Example personal mode config snippet:
```yaml
mode: personal
niche: "AI developer tools"
delivery:
  gmail:
    to: user@gmail.com
  slack:
    webhook_url: https://hooks.slack.com/...
```

Example audience mode config snippet:
```yaml
mode: audience
niche: "AI developer tools"
delivery:
  beehiiv:
    api_key: "${BEEHIIV_API_KEY}"
    publication_id: pub_xxxxx
  slack:
    webhook_url: https://hooks.slack.com/...   # optional: notify when draft is ready
```

### Step 6: Delivery Credentials Setup

**If personal mode with Gmail:**
Walk the user through:
1. Go to myaccount.google.com/apppasswords
2. Select "Mail" and your device
3. Copy the 16-character password
4. Set it: `export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx`

**If personal mode with custom SMTP:**
Show the env vars needed:
```
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_USER=user@example.com
export SMTP_PASSWORD=...
```

**If audience mode with Beehiiv:**
Walk the user through:
1. Go to app.beehiiv.com > Settings > API
2. Generate an API key
3. Copy the publication ID from your publication settings
4. Set the env vars:
   ```
   export BEEHIIV_API_KEY=...
   export BEEHIIV_PUBLICATION_ID=pub_xxxxx
   ```

Note for audience mode: "The system will create a draft post in Beehiiv for each brief. You review and publish from your Beehiiv dashboard -- full editorial control stays with you."

### Step 7: Set Up Cron

Generate the crontab entries:
```
# Daily Intel - {niche}
# Collect signals every {interval} hours
0 */{interval} * * * cd /path/to/daily-intel && python -m daily_intel -i {slug} collect >> ~/.daily-intel/logs/{slug}.log 2>&1

# Generate and deliver daily brief at {time}
{minute} {hour} * * * cd /path/to/daily-intel && python -m daily_intel -i {slug} brief >> ~/.daily-intel/logs/{slug}.log 2>&1
```

Show the user and ask: "Want me to add these to your crontab?"

If yes, add them. If no, show them how to do it manually.

### Step 8: Confirmation

**Personal mode:**
```
Your Daily Intel is live!

Mode: Personal (private intelligence feed)
Niche: {niche}
Sources: {N} validated feeds
Competitors: {N} tracked
Delivery: {method} to {target}
Schedule: Daily at {time} {timezone}
Database: Supabase ({project_name})

Next steps:
1. Set environment variables (if not already done):
   export ANTHROPIC_API_KEY=sk-...
   export SUPABASE_URL=https://xxx.supabase.co
   export SUPABASE_SERVICE_KEY=...
   {export GMAIL_APP_PASSWORD=... if gmail}

2. Test a full cycle:
   python -m daily_intel -i {slug} run

3. Your first real brief arrives tomorrow at {time}!

To check health: python -m daily_intel -i {slug} health
To preview a brief: python -m daily_intel -i {slug} preview
To adjust settings: /daily-intel {slug} tune
```

**Audience mode:**
```
Your Daily Intel is live!

Mode: Audience (newsletter for subscribers)
Niche: {niche}
Sources: {N} validated feeds
Competitors: {N} tracked
Delivery: Beehiiv drafts{, + Slack notification if configured}
Schedule: Draft created daily at {time} {timezone}
Database: Supabase ({project_name})

Workflow: Each morning a draft appears in your Beehiiv dashboard.
Review, edit, and publish on your own schedule.

Next steps:
1. Set environment variables (if not already done):
   export ANTHROPIC_API_KEY=sk-...
   export SUPABASE_URL=https://xxx.supabase.co
   export SUPABASE_SERVICE_KEY=...
   export BEEHIIV_API_KEY=...
   export BEEHIIV_PUBLICATION_ID=pub_xxxxx

2. Test a full cycle:
   python -m daily_intel -i {slug} run

3. Your first draft will appear in Beehiiv tomorrow at {time}!

To check health: python -m daily_intel -i {slug} health
To preview a brief: python -m daily_intel -i {slug} preview
To adjust settings: /daily-intel {slug} tune
```

---

## TUNE (Adjust Config)

Interactive adjustment of any config parameter:
- Add/remove sources (with RSS validation)
- Add/remove competitors
- Change delivery channels or schedule
- Adjust scoring thresholds
- Change brief voice/style
- Switch mode (personal <-> audience) -- note this changes delivery defaults

After changes, re-validate affected sources and update config.yaml.

---

## STATUS

Read config and display:
- Instance name, niche, mode, source count, competitor count
- Delivery config
- If DB is configured: today's signal count, health indicator
- Last brief date (check briefs/ directory)

---

## Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| No Supabase MCP | MCP tool call fails | Tell user to connect Supabase MCP in Claude Code settings, or create project manually via dashboard |
| ANTHROPIC_API_KEY missing | os.environ check | Show setup instructions |
| All RSS feeds dead | 0 validated sources | Expand research, try different source types |
| Gmail auth fails | SMTP error | Walk through App Password setup again |
| Beehiiv API error | HTTP 401/403 | Walk through API key and publication ID setup |
| Supabase project not ready | get_project shows non-active status | Wait and retry (up to 5 minutes) |

---

## Critical Constraints

- All instance data stored in ~/.daily-intel/instances/<slug>/
- Python package must be installed locally
- User owns all infrastructure (Supabase project, API keys, cron)
- Never store API keys in config files. Always use environment variables.
- Never fabricate sources. Every RSS feed must be validated before adding to config.
- The magic moment preview must use REAL data, not mock data.
- Audience mode creates Beehiiv drafts only. The user controls publishing. Never auto-publish.
