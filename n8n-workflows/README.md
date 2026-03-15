# Reality Engine -- n8n Workflow Build Guide

## Overview

6 workflows that collect signals from 50+ sources, score them with Claude AI, store in Supabase, and generate daily newsletter + Slack digest.

## Prerequisites

- n8n instance (self-hosted or cloud)
- Supabase project with `001_initial_schema.sql` migration applied
- Slack workspace with a dedicated channel + webhook/bot
- Gmail or SMTP credentials for email delivery
- Anthropic API key (for Claude AI scoring)

## Credentials Needed in n8n

| Credential | Type | Used By |
|-----------|------|---------|
| `supabase` | Supabase (Postgres) | All workflows |
| `anthropic-claude` | HTTP Header Auth | WF1, WF2, WF3, WF5 |
| `slack` | Slack OAuth2 | WF5, WF6 |
| `gmail` | Gmail OAuth2 | WF5 |

---

## WF1: RSS Feed Aggregator

**Trigger:** Schedule -- every 4 hours
**Sources:** RSS feeds (competitor blogs, industry, regulatory)

### Node Chain

```
1. [Schedule Trigger] every 4h

2. [Supabase] query sources WHERE source_type IN ('rss') AND active = true
   -> returns list of RSS feed URLs

3. [Loop Over Items] for each source:

4.   [RSS Feed Read] url = {{$json.url}}
     -> returns feed items

5.   [Set] normalize fields:
     title = {{$json.title}}
     url = {{$json.link}}
     source_name = {{$json.source_name}}  (from sources table)
     source_type = 'rss'
     category = {{$json.category}}  (from sources table)
     published_at = {{$json.pubDate}}
     raw_content = {{$json.contentSnippet}}

6. [Merge] combine all items from loop

7. [Remove Duplicates] mode: "Across Executions", compare field: url

8. [HTTP Request] POST to Claude API
   URL: https://api.anthropic.com/v1/messages
   Headers: x-api-key = {{$credentials.anthropic}}, anthropic-version = 2023-06-01
   Body: {
     "model": "claude-haiku-4-5-20251001",
     "max_tokens": 300,
     "messages": [{"role": "user", "content": "...scoring prompt..."}]
   }
   -> returns {score, category, summary, content_angle}

9. [Set] parse AI response, set relevance_score, summary, content_angle

10. [IF] relevance_score >= 6

11.  [Supabase] INSERT INTO signals (title, url, source_name, source_type,
     category, published_at, raw_content, summary, relevance_score,
     urgency, content_potential, content_angle)
     ON CONFLICT (url_hash) DO NOTHING

12.  [IF] relevance_score >= 9
       -> [Slack] send urgent alert to your channel
```

### AI Scoring Prompt

Customize this for your niche. Replace the scoring criteria with what matters in your industry.

```
Score this signal for a [YOUR INDUSTRY] intelligence system.

Rate relevance 1-10:
- 9-10: Breaking industry news, major policy changes, critical developments
- 7-8: Important updates, competitor launches, regulatory shifts
- 5-6: Adjacent topics with a clear angle to our industry
- 3-4: Loosely related business/marketing news
- 1-2: Not relevant

Rate urgency 1-5: 5=breaking now, 4=this week, 3=recent trend, 2=evergreen, 1=low
Rate content_potential 1-5: 5=multiple content pieces, 4=strong single piece, 3=supporting, 2=minor, 1=archive

Title: {title}
Source: {source_name}
Content: {raw_content}

Return ONLY valid JSON:
{"relevance_score": N, "urgency": N, "content_potential": N, "category": "...", "summary": "2 sentences max", "content_angle": "suggested hook or null"}
```

---

## WF2: Google News Monitor

**Trigger:** Schedule -- every 4 hours
**Sources:** Google News RSS keyword streams

### Node Chain

```
1. [Schedule Trigger] every 4h

2. [Supabase] query sources WHERE source_type = 'news_rss' AND active = true

3-12. Same as WF1 (loop, read, normalize, dedup, score, store)
```

Identical to WF1 but queries `news_rss` source type. Can be combined into WF1 by querying both types.

---

## WF3: Social/Community Monitor

**Trigger:** Schedule -- every 12 hours
**Sources:** Reddit RSS search feeds

Same as WF1 but:
- source_type = 'reddit_rss'
- Lower relevance threshold (>= 5 instead of >= 6)
- Additional AI instruction: "Extract the specific pain point or question being asked. What language does the poster use to describe their problem?"

---

## WF4: Weekly Scraper

**Trigger:** Schedule -- weekly (Sunday 10pm)
**Sources:** Scrape targets without RSS

### Node Chain

```
1. [Schedule Trigger] weekly Sunday 22:00

2. [Supabase] query sources WHERE source_type = 'scrape' AND active = true

3. [Loop Over Items] for each target:

4.   [HTTP Request] GET {{$json.url}}
     Headers: User-Agent = "Mozilla/5.0..."

5.   [HTML Extract] extract article titles, URLs, dates from page

6.   [Set] normalize fields

7. [Merge] combine

8. [Remove Duplicates]

9-11. Same AI scoring + Supabase insert as WF1
```

For more complex scraping, use [Firecrawl](https://firecrawl.dev) API instead of raw HTTP Request.

---

## WF5: Daily Brief Generator (Most Complex)

**Trigger:** Schedule -- daily at your configured time
**Output:** HTML email + Slack digest

### Node Chain

```
1. [Schedule Trigger] daily at configured time

2. [Supabase] SELECT * FROM get_brief_signals(24)
   -> returns all undelivered signals from last 24h, scored >= 6

3. [Set] group signals:
   p1_signals = filter composite_score >= 75
   p2_signals = filter composite_score >= 30 AND < 75
   p3_signals = filter composite_score >= 10 AND < 30
   competitor_signals = filter category = 'Competitor Moves'

4. [HTTP Request] POST to Claude API (use a capable model for quality)
   Prompt: see Brief Generation Prompt below

5. [Set] parse Claude response into template variables

6. [HTML Template] render newsletter.html with variables

7. [Gmail/SMTP] send HTML email
   Subject: "Brief #{{brief_number}} -- {{editorial_headline}}"

8. [Slack] send Block Kit message using slack-digest.json template

9. [Supabase] INSERT INTO daily_briefs
   (brief_date, signal_count, html_content, slack_content, delivered_email, delivered_slack)

10. [Supabase] call mark_signals_delivered(signal_ids, CURRENT_DATE)
```

### Brief Generation Prompt

Customize the voice and focus for your niche:

```
You are the editor of a daily intelligence newsletter for a [YOUR INDUSTRY] company.
Your newsletter is read by the leadership team every morning.

Write like the best intelligence analysts: sharp, opinionated, and action-oriented.
Connect dots between signals. Identify what matters and why. Skip anything that
doesn't help make a decision or create content.

Voice: Authoritative but not stuffy. Data-driven. Occasionally contrarian.
Think Morning Brew meets CIA Presidential Daily Brief.

Given today's collected signals, produce:

1. EDITORIAL HEADLINE: One compelling line that captures today's most important theme.

2. EDITORIAL SYNTHESIS: 3-4 sentences connecting the biggest signals. What story do
   they tell together? What should the company do about it?

3. For each Priority 1 signal: A sharp 2-sentence summary and a specific content angle
   ("Here's the LinkedIn post hook: ...").

4. CONTENT IDEAS: 5 specific, ready-to-execute content ideas. For each:
   - A hook (the opening line)
   - The format (carousel, video, text post, blog)
   - Why now (what makes this timely)

5. COMPETITOR ACTIVITY: 2-3 sentences on what competitors published or announced.
   What does it reveal about their strategy?

6. DATA POINTS: 2-3 specific numbers or stats from today's signals that could
   anchor future content.

Today's signals (JSON):
{{signals_json}}

Respond in JSON matching this schema:
{
  "editorial_headline": "string",
  "editorial_body": "string",
  "editorial_body_short": "string (1-2 sentences for Slack)",
  "p1_signals": [{"title": "", "summary": "", "content_angle": ""}],
  "content_ideas": [{"hook": "", "format": "", "why_now": ""}],
  "competitor_summary": "string",
  "data_points": [{"stat": "", "context": ""}]
}
```

---

## WF6: Health Check

**Trigger:** Schedule -- daily at 23:00
**Purpose:** Verify workflows ran, alert on failures

### Node Chain

```
1. [Schedule Trigger] daily 23:00

2. [n8n API] GET /executions?workflowId=WF1_ID&status=error&lastHours=24
   Repeat for WF2-WF5

3. [IF] any errors found
   -> [Slack] send alert: "Reality Engine: {{workflow_name}} failed at {{time}}"

4. [Supabase] SELECT count(*) FROM signals WHERE collected_at >= CURRENT_DATE
   -> signal_count_today

5. [IF] signal_count_today == 0
   -> [Slack] send alert: "Zero signals collected today. Check feeds."

6. [Weekly: IF day = Sunday]
   -> [Supabase] aggregate weekly stats
   -> [Slack] send weekly summary:
     "Weekly: {{total_signals}} signals, {{briefs_sent}} briefs, top category: {{top_category}}"
```

---

## Monitoring

- Check Supabase dashboard for signal volume trends
- Review brief quality weekly and provide feedback via the feedback table
- Monthly: review competitor list, add/remove as needed
- Quarterly: review source list, prune dead feeds, add new ones
