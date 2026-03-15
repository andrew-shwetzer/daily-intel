-- Reality Engine — Supabase Schema
-- Migration 001: Initial schema
--
-- Creates tables for signal collection, competitor tracking,
-- content pipeline, daily briefs, source registry, and feedback.

-- ============================================
-- SIGNALS TABLE
-- Stores every collected signal from all sources
-- ============================================
CREATE TABLE IF NOT EXISTS signals (
  id              BIGSERIAL PRIMARY KEY,
  title           TEXT NOT NULL,
  url             TEXT NOT NULL,
  url_hash        TEXT GENERATED ALWAYS AS (md5(url)) STORED,
  source_name     TEXT NOT NULL,
  source_type     TEXT NOT NULL CHECK (source_type IN ('rss', 'news', 'reddit', 'api', 'scrape', 'alert')),
  category        TEXT NOT NULL,
  published_at    TIMESTAMPTZ,
  collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- AI-generated fields
  summary         TEXT,
  relevance_score SMALLINT CHECK (relevance_score BETWEEN 1 AND 10),
  urgency         SMALLINT CHECK (urgency BETWEEN 1 AND 5),
  content_potential SMALLINT CHECK (content_potential BETWEEN 1 AND 5),
  composite_score SMALLINT GENERATED ALWAYS AS (urgency * relevance_score * content_potential) STORED,
  content_angle   TEXT,

  -- Status flags
  delivered       BOOLEAN NOT NULL DEFAULT false,
  brief_date      DATE,
  content_queued  BOOLEAN NOT NULL DEFAULT false,
  archived        BOOLEAN NOT NULL DEFAULT false,

  -- Raw data
  raw_content     TEXT,
  metadata        JSONB DEFAULT '{}'
);

-- Unique constraint on URL hash to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_url_hash ON signals (url_hash);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_signals_collected_at ON signals (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_composite_score ON signals (composite_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_signals_category ON signals (category);
CREATE INDEX IF NOT EXISTS idx_signals_delivered ON signals (delivered) WHERE delivered = false;
CREATE INDEX IF NOT EXISTS idx_signals_source_type ON signals (source_type);

-- ============================================
-- COMPETITORS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS competitors (
  id                SERIAL PRIMARY KEY,
  name              TEXT NOT NULL UNIQUE,
  url               TEXT,
  blog_url          TEXT,
  rss_feed          TEXT,
  linkedin_url      TEXT,
  tier              TEXT,
  key_person        TEXT,
  services          TEXT[],
  differentiator    TEXT,
  monitoring_priority TEXT CHECK (monitoring_priority IN ('HIGH', 'MEDIUM', 'LOW')) DEFAULT 'MEDIUM',
  last_activity_at  TIMESTAMPTZ,
  notes             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- CONTENT PIPELINE TABLE
-- Ideas and posts tracked from signal to published
-- ============================================
CREATE TABLE IF NOT EXISTS content_pipeline (
  id              SERIAL PRIMARY KEY,
  title           TEXT NOT NULL,
  category        TEXT,
  format          TEXT[] DEFAULT '{}',
  status          TEXT NOT NULL CHECK (status IN ('idea', 'queued', 'drafting', 'review', 'scheduled', 'published')) DEFAULT 'idea',
  priority        SMALLINT,
  source_signal_id BIGINT REFERENCES signals(id),
  hook            TEXT,
  target_keyword  TEXT,
  body            TEXT,
  publish_date    DATE,
  platform        TEXT[],
  performance     JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_status ON content_pipeline (status);
CREATE INDEX IF NOT EXISTS idx_content_publish_date ON content_pipeline (publish_date);

-- ============================================
-- DAILY BRIEFS TABLE
-- Archive of generated newsletters
-- ============================================
CREATE TABLE IF NOT EXISTS daily_briefs (
  id              SERIAL PRIMARY KEY,
  brief_date      DATE NOT NULL UNIQUE,
  brief_number    SERIAL,
  signal_count    INTEGER,
  html_content    TEXT,
  slack_content   TEXT,
  markdown_content TEXT,
  delivered_email BOOLEAN DEFAULT false,
  delivered_slack BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- SOURCES TABLE
-- Registry of all monitored sources (drives n8n workflows)
-- ============================================
CREATE TABLE IF NOT EXISTS sources (
  id              SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  url             TEXT NOT NULL,
  source_type     TEXT NOT NULL CHECK (source_type IN ('rss', 'news_rss', 'reddit_rss', 'api', 'scrape', 'alert', 'page_monitor')),
  category        TEXT NOT NULL,
  frequency       TEXT NOT NULL,
  active          BOOLEAN DEFAULT true,
  last_checked_at TIMESTAMPTZ,
  last_signal_at  TIMESTAMPTZ,
  error_count     INTEGER DEFAULT 0,
  notes           TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- FEEDBACK TABLE
-- User feedback for tuning signal relevance
-- ============================================
CREATE TABLE IF NOT EXISTS feedback (
  id              SERIAL PRIMARY KEY,
  signal_id       BIGINT REFERENCES signals(id),
  feedback_type   TEXT CHECK (feedback_type IN ('more', 'less', 'irrelevant', 'great')),
  topic           TEXT,
  reason          TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- ROW LEVEL SECURITY
-- ============================================
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_pipeline ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;

-- Service role has full access (n8n uses service role key)
CREATE POLICY "Service role full access" ON signals FOR ALL USING (true);
CREATE POLICY "Service role full access" ON competitors FOR ALL USING (true);
CREATE POLICY "Service role full access" ON content_pipeline FOR ALL USING (true);
CREATE POLICY "Service role full access" ON daily_briefs FOR ALL USING (true);
CREATE POLICY "Service role full access" ON sources FOR ALL USING (true);
CREATE POLICY "Service role full access" ON feedback FOR ALL USING (true);

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Get today's undelivered signals sorted by score
CREATE OR REPLACE FUNCTION get_todays_signals()
RETURNS SETOF signals AS $$
  SELECT * FROM signals
  WHERE collected_at >= CURRENT_DATE
    AND delivered = false
    AND archived = false
    AND relevance_score >= 6
  ORDER BY composite_score DESC NULLS LAST;
$$ LANGUAGE sql STABLE;

-- Get signals for brief generation (last N hours)
CREATE OR REPLACE FUNCTION get_brief_signals(since_hours INTEGER DEFAULT 24)
RETURNS SETOF signals AS $$
  SELECT * FROM signals
  WHERE collected_at >= now() - (since_hours || ' hours')::interval
    AND delivered = false
    AND archived = false
    AND relevance_score >= 6
  ORDER BY composite_score DESC NULLS LAST;
$$ LANGUAGE sql STABLE;

-- Mark signals as delivered for a specific brief
CREATE OR REPLACE FUNCTION mark_signals_delivered(signal_ids BIGINT[], brief_dt DATE DEFAULT CURRENT_DATE)
RETURNS void AS $$
  UPDATE signals
  SET delivered = true, brief_date = brief_dt
  WHERE id = ANY(signal_ids);
$$ LANGUAGE sql;
