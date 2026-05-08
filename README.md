# Healthball

Predicting Arsenal FC player injury risk using career injury history, workload, and age — built as a portfolio project at [joonbo.com/healthball](https://joonbo.com/healthball).

## How it works

Healthball is split into two parts: a **data pipeline** that runs offline, and a **frontend** embedded in the portfolio.

```
seed.py                  — wipes and re-seeds squad + injury history
model/train.py           — computes weighted risk scores, writes to DB
      │
      ▼
Neon PostgreSQL (cloud)
      │  server-side query
      ▼
portfolio/app/api/healthball/   — Next.js API routes
      │
      ▼
portfolio/app/healthball/       — React UI at /healthball
```

There is no runtime Python server. Risk scores are precomputed and stored in the database. The portfolio's Next.js API routes query Neon directly from the server side, so DB credentials are never exposed to the browser.

> **Note on scraping:** Transfermarkt actively blocks automated requests. The ETL scrapers (`etl/load_players.py`, `etl/load_injuries.py`) are kept for reference but are not part of the current workflow. All squad and injury data is managed manually in `seed.py`.

## Architecture

| Layer | Technology | Hosting |
|-------|-----------|---------|
| Database | Neon (PostgreSQL) | Neon free tier |
| Data pipeline | Python | Run locally / on demand |
| API | Next.js API routes | Vercel (via portfolio) |
| Frontend | Next.js + Tailwind CSS | Vercel (via portfolio) |

## Project structure

```
healthball/
├── backend/
│   ├── schema.sql              # DB table definitions
│   ├── seed.py                 # All squad + injury history — edit this to maintain data
│   ├── new_season.py           # Season-transition helper (run once each summer)
│   ├── refresh.sh              # One-command pipeline: seed.py → train.py
│   ├── requirements.txt        # Python dependencies
│   ├── etl/                    # Legacy scrapers (reference only — TM blocks bots)
│   │   ├── players_to_scrape.csv
│   │   ├── load_players.py
│   │   └── load_injuries.py
│   └── model/
│       └── train.py            # Computes risk scores, writes to DB
│
└── README.md

portfolio/                      # Separate repo: joonbo.com portfolio
├── app/
│   ├── healthball/
│   │   ├── page.tsx            # /healthball page (player grid + filters + drawer)
│   │   ├── layout.tsx
│   │   └── _components/
│   │       ├── types.ts
│   │       ├── PlayerCard.tsx      # Grid card with risk bar + injury badge
│   │       ├── PlayerDrawer.tsx    # Slide-in detail panel with stats + timeline
│   │       ├── RiskGauge.tsx       # Canvas arc gauge (0–100)
│   │       └── InjuryTimeline.tsx  # Chronological injury list
│   └── api/healthball/players/
│       ├── route.ts            # GET /api/healthball/players
│       └── [id]/route.ts       # GET /api/healthball/players/:id
└── .env.local                  # HEALTHBALL_DATABASE_URL (server-side only)
```

## Database schema

```sql
players      — name, position, age, nationality, tm_id,
               currently_injured, debut_age, career_apps, recent_apps
injuries     — season, injury_type, injury_from, injury_to,
               days_out, games_missed, minutes_before, minutes_total
risk_scores  — risk_score (0–100), risk_level, features (JSONB), computed_at
```

`injury_to = NULL` marks an active (ongoing) injury. The `risk_scores` table is fully replaced each time `train.py` runs.

## Risk model

Pure weighted formula — more reliable than a trained model with only 22 players. The score (0–100) is the sum of:

| Feature | What it captures | Max pts |
|---------|-----------------|---------|
| `currently_injured` | Player is provably unavailable right now | 12 |
| `age` | Older players break down more often (penalty at 28, 30, 32) | 18 |
| `debut_age` | Earlier debut = more load accumulated on a developing body | 4.5 |
| `career_apps` | Total career appearances across all clubs — physical mileage | 5 |
| `recent_apps` | Combined apps in 24/25 + 25/26 — overload / fatigue risk | 6 |
| `total_injuries` | Career injury count | 20 |
| `ligament_count` | Cruciate / ACL / Achilles injuries | unbounded |
| `muscle_count` | Hamstring / thigh / adductor / calf injuries | unbounded |
| `avg_days_out` | Severity proxy — how long injuries sideline the player | 10 |
| `recent_injuries` | Injuries in the last 2 seasons | 18 |
| `days_since_last` | Recency weight — recent injury = higher risk | 12 |

Risk levels: **high** ≥ 60 · **medium** ≥ 20 · **low** < 20

For ongoing injuries, `avg_days_out` uses elapsed days since `injury_from` rather than the final `days_out` value.

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Neon account (free tier is enough)

### 1. Set up the Python environment

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create `backend/.env`:

```env
DEV_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

### 3. Initialise the database

```bash
psql "$DEV_DATABASE_URL" -f schema.sql
```

Or using Python if you don't have `psql`:

```bash
python - <<'EOF'
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DEV_DATABASE_URL"))
schema = open("schema.sql").read()

with engine.begin() as conn:
    for stmt in schema.split(";"):
        s = stmt.strip()
        if s:
            conn.execute(text(s))
print("Done.")
EOF
```

### 4. Seed data and compute scores

```bash
cd backend
source venv/bin/activate
bash refresh.sh
```

This wipes existing data, seeds the current squad and all injury history, then recomputes risk scores. Takes ~5 seconds.

### 5. Run the portfolio locally

Add to `portfolio/.env.local`:

```env
HEALTHBALL_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

```bash
cd portfolio
npm install
npm run dev
```

Open [http://localhost:3000/healthball](http://localhost:3000/healthball).

---

## Maintaining data

All squad and injury data lives in `backend/seed.py`. After any edit, push it to the database with:

```bash
cd backend
source venv/bin/activate
bash refresh.sh        # runs seed.py then model/train.py (~5 seconds)
```

The portfolio page reflects the update immediately — no redeploy required.

---

### Mid-season updates

**New injury**

1. Add a row to the current season's `INJURIES_<season>` list:
   ```python
   (PLAYER_ID, "25/26", "Hamstring Injury", "2026-05-01", None, None, None, 0, None),
   #                                          injury_from   ^^^  to=None → ongoing
   ```
2. Set `currently_injured=True` on the player in `SQUAD`.
3. Run `refresh.sh`.

**Player returns from injury**

1. Fill in the ongoing row's end fields:
   ```python
   (PLAYER_ID, "25/26", "Hamstring Injury", "2026-05-01", "2026-05-25", 24, 3, 0, 270),
   #                                                        injury_to     days games
   ```
2. Set `currently_injured=False` on the player in `SQUAD`.
3. Run `refresh.sh`.

**Appearances accumulate (workload tracking)**

`SEASON_APPS` in `seed.py` tracks per-player, per-season game counts. `recent_apps` is computed automatically as the sum of the last two seasons — no manual calculation needed. Update the current season's value periodically during the season and finalise it at season end:

```python
SEASON_APPS = {
    SAKA: {"24/25": 37, "25/26": 40},   # update "25/26" as games are played
    ...
}
```

**Squad changes (loan / transfer / departure)**

- Player sent on loan → remove from `SQUAD` and their `INJURIES_*` rows; add them back when they return.
- New signing → add to `SQUAD`; add a new ID constant; add any prior injury history rows.
- Player sold → remove from `SQUAD` and their injury rows.
- If the squad order or size changes, update the ID constants at the top of `seed.py` to match.

**Career appearances**

Update `career_apps` in the `SQUAD` tuple when a meaningful number of games have been played (end of season is a good time). Source: Transfermarkt or Wikipedia.

---

### New season (each summer)

Run the transition script once:

```bash
cd backend
source venv/bin/activate
python new_season.py 26/27
```

**What the script does automatically:**
- Bumps every player's age by 1
- Updates `SQUAD_SEASON`, `PREV_SEASON`, and `SQUAD_UPDATED` in `seed.py`
- Adds `"26/27": 0` to every player's `SEASON_APPS` entry
- Inserts a blank `INJURIES_2627 = []` block in `seed.py`
- Appends `INJURIES_2627` to `ALL_INJURIES`
- Updates `CURRENT_SEASON_YEAR` in `model/train.py`

**What still needs manual attention** (the script prints this checklist):
1. Verify/correct `SEASON_APPS` final values for the just-ended season
2. Update `career_apps` for all players
3. Close any ongoing injuries from last season (fill `injury_to`, `days_out`, `games_missed`; set `currently_injured=False`)
4. Handle transfers — remove departed players, add new signings
5. Set `currently_injured=True` for anyone injured at the new season's start and add their opening injury row to `INJURIES_2627`

Then run `bash refresh.sh` to push everything live.

---

### Current squad (2025/26)

22 players. On loan (excluded): Oleksandr Zinchenko (Nottingham Forest), Fabio Vieira (Hamburger SV).

Currently injured at last update (2026-05-08):
- **Jurriën Timber** — Groin injury since 2026-03-14
- **Mikel Merino** — Fractured foot since 2026-02-01

---

## Deployment

### Database (Neon)

1. Create a free project at [neon.tech](https://neon.tech).
2. Copy the connection string from the Neon dashboard.
3. Run `schema.sql` once to initialise tables.
4. Run `bash refresh.sh` to populate data.

### Portfolio / API (Vercel)

The `/healthball` page and its API routes are part of the portfolio Next.js app, deployed to Vercel.

1. In the Vercel project settings, add an environment variable:
   ```
   HEALTHBALL_DATABASE_URL = <your Neon connection string>
   ```
2. Deploy normally (`git push` or Vercel CLI). The API routes are server-side and require no separate server.

## Data source

Injury history is sourced from [Transfermarkt](https://www.transfermarkt.com) (manually verified) and cross-referenced with Wikipedia for career appearance counts and debut ages.
