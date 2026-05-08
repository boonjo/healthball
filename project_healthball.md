---
name: Healthball project architecture
description: Stack, file locations, DB credentials, deployment workflow, and data maintenance for Healthball
type: project
originSessionId: d0396d22-08df-45f2-9729-3ca1b1c62430
---
Healthball is an Arsenal FC injury-risk app embedded in joonbo's portfolio at joonbo.com/healthball.

**Stack (fully free):**
- DB: Neon PostgreSQL (free tier)
- Data pipeline: Python scripts in `healthball/backend/` — no runtime server
- API: Next.js server-side API routes in `portfolio/app/api/healthball/players/`
- UI: Next.js page at `portfolio/app/healthball/` deployed to Vercel (via portfolio repo)

**Risk model:** Pure weighted formula (0–100), no ML model. 11 features.
**Risk thresholds:** high ≥ 60 · medium ≥ 20 · low < 20
**Squad:** 22 Arsenal 2025/26 players (loans Zinchenko + Vieira excluded from DB)

**Key files (healthball repo):**
- `backend/schema.sql` — DB table definitions (players, injuries, risk_scores)
- `backend/seed.py` — ALL squad + injury data; edit this to maintain data
- `backend/new_season.py` — run once each summer: `python new_season.py 26/27`
- `backend/refresh.sh` — one-command pipeline: `seed.py → train.py` (~5s)
- `backend/requirements.txt` — Python deps
- `backend/model/train.py` — computes risk scores, writes to DB (CURRENT_SEASON_YEAR updated automatically by new_season.py)
- `backend/etl/` — legacy Transfermarkt scrapers (reference only; TM blocks bots)

**Files NOT in git:**
- `backend/.env` — DB credentials (DEV_DATABASE_URL)
- `backend/model/risk_model.pkl` — stale artifact from old RF model (formula-only now)
- `backend/seed_2526.py` — dead file, superseded by seed.py (delete it)
- `backend/seed_data.sql` — dead file, superseded by seed.py (delete it)

**Portfolio files (separate repo):**
- `portfolio/app/api/healthball/players/route.ts` — GET /api/healthball/players
- `portfolio/app/api/healthball/players/[id]/route.ts` — GET /api/healthball/players/:id
- `portfolio/app/healthball/` — React UI
- `portfolio/.env.local` — contains HEALTHBALL_DATABASE_URL (never commit)

**Deployment workflow:**

1. **Database (Neon)** — one-time setup:
   - Create free project at neon.tech
   - Run `psql "$DEV_DATABASE_URL" -f schema.sql` to initialise tables
   - Run `bash refresh.sh` to populate data

2. **Data pipeline** — run locally on demand:
   ```
   cd backend && source venv/bin/activate && bash refresh.sh
   ```
   This wipes + re-seeds all data, then recomputes risk scores. Takes ~5s.
   No redeploy needed — portfolio reads from DB directly.

3. **Portfolio / API (Vercel)**:
   - Add env var in Vercel project settings: `HEALTHBALL_DATABASE_URL = <neon connection string>`
   - Deploy via `git push` to portfolio repo — no separate server needed
   - API routes are server-side; DB credentials never reach the browser

**Mid-season data updates:**
- New injury: add row to `INJURIES_2526` with `injury_to=None`, set `currently_injured=True`, run `refresh.sh`
- Player returns: fill end dates in that row, set `currently_injured=False`, run `refresh.sh`
- Appearances: update `SEASON_APPS` dict in `seed.py` for current season, run `refresh.sh`
- Squad change: add/remove from `SQUAD` list and injury lists, run `refresh.sh`

**Season transition (each summer):**
```
python new_season.py 26/27
```
Auto: bumps all ages, updates season strings, adds SEASON_APPS keys, inserts INJURIES block, updates ALL_INJURIES, bumps CURRENT_SEASON_YEAR.
Manual after: verify final apps, update career_apps, close ongoing injuries, handle transfers, flag new injuries.
Then: `bash refresh.sh`

**Why:** DB is source of truth for precomputed scores. No runtime Python server. Portfolio redeploys not required for data updates.

**How to apply:** When user asks about data refresh, injuries, or squad updates — all changes go through `seed.py` + `refresh.sh`. When asking about season transitions — use `new_season.py`.
