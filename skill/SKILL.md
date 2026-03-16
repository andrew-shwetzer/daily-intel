---
name: daily-intel
description: |
  Build your own AI-powered intelligence newsletter. Monitors any niche via RSS, scores signals
  with Claude, and delivers a daily editorial brief to your inbox or Slack. Full auto-setup:
  asks 5 questions, researches your niche, provisions Supabase, generates config, shows a live
  sample brief, and sets up cron. Everything runs on your machine.
argument-hint: "[new | <slug> status | <slug> brief | <slug> tune | list]"
model: claude-opus-4-6
user_invocable: true
---

# /daily-intel -- Your Personal Intelligence Newsletter

You build a custom AI-powered intelligence newsletter for any niche in one session. 5 questions, then everything is auto-provisioned: database, sources, config, cron schedule. The user sees a live sample brief before committing.

## When NOT to Use

- One-off research questions (use `/research`)
- Niches with fewer than 3 identifiable sources (not enough signal volume)
- Building a public newsletter product (this is for personal/team intelligence)

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
- `daily-intel brief` - generate editorial brief, deliver via Gmail/Slack
- `daily-intel run` - collect + brief (full daily cycle)
- `daily-intel health` - check system status
- `daily-intel preview` - generate a brief without storing anything

## Command Routing

```python
if no args or args == "new":
    -> ONBOARDING (5 questions + auto-setup)
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

## ONBOARDING FLOW (5 Questions)

When the user runs `/daily-intel` or `/daily-intel new`, run this conversational flow. Be warm, direct, and helpful. Suggest smart defaults.

### Prerequisites Check

Before starting, verify:
1. `ANTHROPIC_API_KEY` is set. If not: "You'll need an Anthropic API key. Get one at console.anthropic.com, then set it: `export ANTHROPIC_API_KEY=sk-...`"
2. The `daily-intel` Python package is installed. Check with: `python -m daily_intel --help`. If not installed: "Let's install the package first: `pip install -e /path/to/daily-intel`"

### Question 1: Your Niche
"What niche or industry do you want to monitor? Be specific."

Examples to help them narrow:
- Not "technology" but "AI developer tools"
- Not "healthcare" but "telehealth platforms for mental health"
- Not "finance" but "DeFi lending protocols"

Save as `niche`.

### Question 2: Your Role
"What do you do in this space? One line is fine."

This tunes relevance scoring. A founder monitoring competitors needs different signals than a content creator looking for trends.

Save as `description`.

### Question 3: Competitors
"Who are your top 3 competitors? Drop names, URLs, or say 'find them for me'."

If "find them for me": deploy a research agent (subagent_type: general-purpose, model: sonnet) to research the niche and find 5-8 competitors with URLs, blog URLs, RSS feeds. Validate each RSS feed with a test fetch.

Save as `competitors`.

### Question 4: Delivery
"Where should your daily brief go?"

Options:
- **Gmail** (most common for personal): "What's your Gmail address? You'll need a Google App Password (not your regular password). I'll show you how to set that up."
- **Slack**: "Drop a Slack webhook URL, or I can walk you through creating one."
- **Both**: Collect both.

Save as `delivery`.

### Question 5: Schedule
"What time should your brief arrive? (default: 6:00 AM)"

Also ask timezone if not obvious from system. Save as `schedule`.

---

## AUTO-SETUP (After 5 Questions)

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

Generate `~/.daily-intel/instances/{slug}/config.yaml` with all discovered sources, competitors, delivery settings, and scoring config baked in.

### Step 6: Gmail App Password Setup (if Gmail delivery)

Walk the user through:
1. Go to myaccount.google.com/apppasswords
2. Select "Mail" and your device
3. Copy the 16-character password
4. Set it: `export GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx`

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

```
Your Daily Intel is live!

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

---

## TUNE (Adjust Config)

Interactive adjustment of any config parameter:
- Add/remove sources (with RSS validation)
- Add/remove competitors
- Change delivery channels or schedule
- Adjust scoring thresholds
- Change brief voice/style

After changes, re-validate affected sources and update config.yaml.

---

## STATUS

Read config and display:
- Instance name, niche, source count, competitor count
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
| Supabase project not ready | get_project shows non-active status | Wait and retry (up to 5 minutes) |

---

## Critical Constraints

- All instance data stored in ~/.daily-intel/instances/<slug>/
- Python package must be installed locally
- User owns all infrastructure (Supabase project, API keys, cron)
- Never store API keys in config files. Always use environment variables.
- Never fabricate sources. Every RSS feed must be validated before adding to config.
- The magic moment preview must use REAL data, not mock data.
