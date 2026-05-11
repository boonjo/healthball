-- Healthball DB schema
-- Run once against Neon to initialize tables

CREATE TABLE IF NOT EXISTS players (
  player_id         SERIAL PRIMARY KEY,
  name              VARCHAR(100) NOT NULL,
  position          VARCHAR(20),
  age               INTEGER,
  nationality       VARCHAR(50),
  tm_id             INTEGER UNIQUE,
  currently_injured BOOLEAN DEFAULT FALSE,
  debut_age         FLOAT,
  career_apps       INTEGER,
  recent_apps       INTEGER,
  recent_minutes    INTEGER,
  scraped_at        TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS injuries (
  injury_id     SERIAL PRIMARY KEY,
  player_id     INTEGER REFERENCES players(player_id) ON DELETE CASCADE,
  season        VARCHAR(10),
  injury_type   VARCHAR(100),
  injury_from   DATE,
  injury_to     DATE,
  days_out      INTEGER,
  games_missed  INTEGER,
  minutes_before INTEGER,
  minutes_total  INTEGER
);

CREATE TABLE IF NOT EXISTS risk_scores (
  score_id    SERIAL PRIMARY KEY,
  player_id   INTEGER REFERENCES players(player_id) ON DELETE CASCADE,
  risk_score  FLOAT NOT NULL,
  risk_level  VARCHAR(10) NOT NULL,
  features    JSONB,
  computed_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_injuries_player   ON injuries(player_id);
CREATE INDEX IF NOT EXISTS idx_risk_player       ON risk_scores(player_id);
CREATE INDEX IF NOT EXISTS idx_risk_player_time  ON risk_scores(player_id, computed_at DESC);

-- Migration: add recent_minutes to existing installs (no-op on fresh schema)
ALTER TABLE players ADD COLUMN IF NOT EXISTS recent_minutes INTEGER;
