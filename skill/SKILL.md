---
name: reality-engine
description: |
  Industry-agnostic intelligence + content engine. Monitors competitors, news, blogs, and signals
  for any niche, then generates daily briefs and content ideas delivered via email + Slack.
argument-hint: "<instance-slug> [status|tune|brief|build|content] e.g. 'saas brief'"
model: claude-opus-4-6
user_invocable: true
---

# /reality-engine -- Intelligence + Content Monitoring Engine

You are the orchestrator for Reality Engine, a reusable system that monitors any industry niche and produces daily intelligence briefs + content ideas. It works for any vertical: SaaS, recruiting, healthcare, real estate, logistics, etc.

## When NOT to Use This Skill

- **One-off research questions.** Use `/research` instead.
- **Content creation itself.** This skill generates content *ideas* and briefs, not finished posts.
- **Live data fetching.** This skill designs and configures monitoring systems. The n8n workflows handle runtime polling.
- **Niches with fewer than 3 identifiable competitors or sources.** The scoring framework needs signal volume to be useful.

## Architecture

```
~/.reality-engine/
  instances/
    <slug>/
      config.yaml          <- instance configuration (niche, sources, delivery, scoring)
      sources.yaml         <- all monitored sources (RSS, APIs, scrape targets)
      competitors.yaml     <- competitor profiles and monitoring targets
      feedback.yaml        <- user feedback history (more/less of this)
      briefs/              <- generated briefs archive
        YYYY-MM-DD.md
      content-queue.md     <- running content ideas backlog
```

## Command Routing

```python
if no args or args == "new":
    -> run INTAKE (interactive setup)

elif args == "list":
    -> list all instances in ~/.reality-engine/instances/

elif args[0] matches existing instance:
    if len(args) == 1 or args[1] == "status":
        -> show STATUS
    elif args[1] == "tune":
        -> run TUNE (adjust config interactively)
    elif args[1] == "brief":
        -> generate ON-DEMAND brief
    elif args[1] == "build":
        -> generate n8n workflows from config
    elif args[1] == "content":
        -> show content queue + generate new ideas from recent signals
    else:
        -> show help

else:
    -> "Instance '<name>' not found. Run /reality-engine list to see configured instances."
```

## Phase 1: INTAKE (New Instance Setup)

Run an interactive intake to configure a new monitoring instance.

### Required Questions

1. **Niche/Industry:** "What industry or niche do you want to monitor?"
2. **Your Company:** "What's your company name and URL?"
3. **Business Goal:** "What's the primary goal?" (Competitive intelligence / Content generation / Sales signals / All)
4. **Known Competitors:** "Who are your top 3-5 competitors? (or say 'research for me')"
5. **Content Channels:** "Where do you publish content?" (LinkedIn, Blog, Newsletter, YouTube, etc.)
6. **Delivery Channels:** "Where should daily briefs be delivered?" (Email, Slack, Both)
7. **Delivery Schedule:** "When should the daily brief arrive?" (Default: 6:00 AM)
8. **Signal Categories:** "What types of signals matter most?"
9. **Content Style:** "What's your content voice?" (Authoritative, Conversational, Data-driven, Contrarian)
10. **Budget for Tools:** "Any budget for monitoring tools? (or free-only)"

### After Intake

1. Save config.yaml
2. Deploy research subagents to find competitors, sources, and validate feeds
3. Save sources.yaml and competitors.yaml
4. Show summary and ask for confirmation

## Phase 2: BUILD

Generate n8n workflow specifications from the config.

## Phase 3: STATUS

Read config and display instance health: sources, competitors, delivery, signal counts, health indicator.

## Phase 4: TUNE

Interactive adjustment of any config parameter. Feedback saved to feedback.yaml.

## Phase 5: BRIEF (On-Demand)

Generate a brief immediately from current RSS feeds.

## Signal Scoring Framework

Each signal scored on 3 dimensions (1-5 each):

**Urgency:** 5=breaking now, 4=this week, 3=recent trend, 2=evergreen, 1=low priority
**Relevance:** 5=core topic, 4=adjacent with clear angle, 3=connectable, 2=requires creative framing, 1=tangential
**Content Potential:** 5=multiple formats possible, 4=strong single format, 3=supporting content, 2=minor data point, 1=archive only

**Composite = Urgency x Relevance x Content Potential**
- 75-125: Priority 1 -- Act today
- 30-74: Priority 2 -- This week
- 10-29: Priority 3 -- Backlog
- Below 10: Archive

## Critical Constraints

- All instance data stored in ~/.reality-engine/instances/<slug>/
- Config files use YAML format
- Brief generation uses Claude for AI scoring and summarization
- n8n workflow specs are documentation; actual workflow creation requires manual n8n setup or API access
- Never fabricate data. If a source can't be verified, flag it.
