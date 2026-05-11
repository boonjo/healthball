"""
Fetches Arsenal squad minutes played and updates players.recent_minutes in the DB.

Two modes:
  Automated (default):  Calls Understat JSON API for 24/25 + 25/26 season minutes.
                        Exits cleanly on failure — seed.py estimates remain.
  Manual CSV:           python etl/fetch_minutes.py --csv <path>
                        Load a manually-downloaded FBref squad stats CSV.

How to get a FBref CSV when automated fetch fails:
  1. Go to fbref.com → Arsenal → "Squad & Player Stats" → "All Competitions"
  2. In the table header click "Share & Export" → "Get table as CSV"
  3. Copy the text into a .csv file (or save the download directly)
  4. Run: python etl/fetch_minutes.py --csv ~/Downloads/arsenal_stats.csv
     (repeat for each season; pass the combined total if only one file is available)

FBref CSV expected columns: 'Player', 'Min'. Alerts if FBref renames them.

Understat API: https://understat.com/main/getTeamData/{team}/{season_start_year}
Returns JSON with top-level key "players", each having "player_name" and "time" (minutes).

Seasonal config: update CURRENT_SEASON_YEAR each summer (new_season.py handles it).
"""
import argparse
import os
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

UNDERSTAT_API = "https://understat.com/main/getTeamData/{team}/{season}"

load_dotenv(Path(__file__).parent.parent / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))

# UPDATE THIS each summer alongside train.py (new_season.py handles it)
CURRENT_SEASON_YEAR = 2026  # 2026 = 25/26 season

# Pinned FBref CSV column names. If FBref renames these, the script will alert
# rather than silently loading wrong data. Update here after fixing the mapping.
FBREF_PLAYER_COL = "Player"
FBREF_MINUTES_COL = "Min"

# Pinned Understat JSON keys expected in each player object.
UNDERSTAT_EXPECTED_KEYS = {"player_name", "time"}

# Warn if fewer than this many squad members were matched.
# 22-player squad: 18 = threshold below which something is likely wrong.
MIN_MATCH_COUNT = 18

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
REQUEST_DELAY = 3


# Explicit substitutions before NFKD — for letters that have no ASCII decomposition
# (e.g. Ø has no combining form, so encode+ignore drops it entirely).
_CHAR_SUBS = str.maketrans("ØøÐðÞþŁłÆæŒœ", "OoDdTtLlAaOo")

# Players whose name in Understat differs from seed.py after normalization.
# Key: normalized seed.py name → value: normalized Understat name.
NAME_ALIASES: dict[str, str] = {
    "gabriel magalhaes": "gabriel",  # Understat omits the surname
}


def normalize(name: str) -> str:
    """Strip diacritics and lowercase. 'Martin Ødegaard' → 'martin odegaard'"""
    name = name.translate(_CHAR_SUBS)
    nfkd = unicodedata.normalize("NFKD", name)
    return nfkd.encode("ascii", "ignore").decode().lower().strip()


# ── Automated mode (Understat JSON API) ──────────────────────────────────────

def fetch_season_understat(season_start: int) -> dict[str, int]:
    """
    Returns {normalized_player_name: minutes} for one season via Understat API.
    Returns {} on any failure — caller falls back to seed estimates.

    API: GET https://understat.com/main/getTeamData/Arsenal/{season_start}
    Returns JSON with top-level "players" list; each player has "player_name" and "time".
    """
    season_str = f"{season_start}/{str(season_start + 1)[-2:]}"
    url = UNDERSTAT_API.format(team="Arsenal", season=season_start)
    referer_headers = {**HEADERS, "Referer": f"https://understat.com/team/Arsenal/{season_start}"}
    print(f"  Fetching {season_str} from Understat API...")

    try:
        resp = requests.get(url, headers=referer_headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  Request failed: {e}")
        return {}
    except ValueError as e:
        print(f"  Failed to parse JSON response: {e}")
        return {}

    players = data.get("players", [])
    if not players:
        print(f"  No players in API response for {season_str}.")
        return {}

    # Validate pinned keys — alert rather than silently loading wrong data
    missing = UNDERSTAT_EXPECTED_KEYS - set(players[0].keys())
    if missing:
        print(f"  WARNING: Understat JSON missing expected keys: {missing}")
        print(f"  Understat may have changed their API structure.")
        print(f"  Update UNDERSTAT_EXPECTED_KEYS in fetch_minutes.py after verifying new keys.")
        return {}

    result = {normalize(p["player_name"]): int(p["time"]) for p in players}
    print(f"  Got {len(result)} players.")
    return result


def fetch_automated() -> dict[str, int]:
    """Fetch from Understat for prev + current season. Returns {} on total failure."""
    prev_start = CURRENT_SEASON_YEAR - 2  # 2024 for 25/26 season
    curr_start = CURRENT_SEASON_YEAR - 1  # 2025 for 25/26 season

    prev = fetch_season_understat(prev_start)
    time.sleep(REQUEST_DELAY)
    curr = fetch_season_understat(curr_start)

    if not prev and not curr:
        print("  No data fetched from Understat — keeping seed.py estimates.")
        return {}

    combined: dict[str, int] = {}
    for d in (prev, curr):
        for name, mins in d.items():
            combined[name] = combined.get(name, 0) + mins

    return combined


# ── Manual CSV mode (FBref) ───────────────────────────────────────────────────

def fetch_csv(csv_path: str) -> dict[str, int]:
    """
    Load minutes from a manually-downloaded FBref squad stats CSV.
    Validates pinned column names before parsing; exits with a clear error if
    FBref has renamed them so stale/wrong data is never silently loaded.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"  ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    try:
        df = pd.read_csv(path, comment="#")
    except Exception as e:
        print(f"  ERROR: Could not read CSV: {e}")
        sys.exit(1)

    df.columns = df.columns.str.strip()

    # Pin column names — alert if FBref renames them rather than loading wrong data
    expected = {FBREF_PLAYER_COL, FBREF_MINUTES_COL}
    missing_cols = expected - set(df.columns)
    if missing_cols:
        print(f"  ERROR: CSV is missing expected columns: {missing_cols}")
        print(f"  Columns found: {sorted(df.columns.tolist())}")
        print(
            f"  FBref may have renamed columns. Update FBREF_PLAYER_COL / "
            f"FBREF_MINUTES_COL in fetch_minutes.py."
        )
        sys.exit(1)

    result: dict[str, int] = {}
    for _, row in df.iterrows():
        if pd.isna(row[FBREF_PLAYER_COL]) or pd.isna(row[FBREF_MINUTES_COL]):
            continue
        try:
            key = normalize(str(row[FBREF_PLAYER_COL]))
            minutes = int(str(row[FBREF_MINUTES_COL]).replace(",", ""))
            result[key] = result.get(key, 0) + minutes
        except (ValueError, TypeError):
            continue

    print(f"  Loaded {len(result)} players from CSV.")
    return result


# ── DB update (shared) ────────────────────────────────────────────────────────

def update_db(season_minutes: dict[str, int], allow_decrease: bool = False) -> None:
    """
    Update players.recent_minutes for matched players.

    Understat covers Premier League only (~50% of Arsenal's game time once cups and
    European games are included). seed.py SEASON_MINUTES estimates all competitions,
    so by default we only write Understat data when it's HIGHER than the current value
    — i.e. the player played more than estimated. Pass allow_decrease=True (e.g. for
    a full FBref CSV that covers all comps) to always overwrite.

    Warns explicitly if fewer than MIN_MATCH_COUNT players are matched.
    """
    with engine.connect() as conn:
        players = pd.read_sql(
            text("SELECT player_id, name, recent_minutes FROM players"), conn
        )

    updated = 0
    skipped_lower = 0
    with engine.begin() as conn:
        for _, p in players.iterrows():
            key = normalize(str(p["name"]))
            key = NAME_ALIASES.get(key, key)  # apply alias if defined
            total = season_minutes.get(key, 0)
            if total <= 0:
                continue
            current = int(p["recent_minutes"] or 0)
            if not allow_decrease and total < current:
                skipped_lower += 1
                continue
            conn.execute(
                text("UPDATE players SET recent_minutes = :m WHERE player_id = :pid"),
                {"m": total, "pid": int(p["player_id"])},
            )
            updated += 1

    total_players = len(players)
    found = updated + skipped_lower
    print(f"  Matched {found}/{total_players} players in Understat.")
    if skipped_lower:
        print(
            f"  Kept seed.py estimate for {skipped_lower} — "
            f"Understat (PL only) was lower than the all-competition estimate."
        )
    if updated:
        print(f"  Updated {updated} player(s) where Understat exceeded the seed estimate.")

    if allow_decrease:
        # CSV mode: every matched player should be updated — warn if low.
        if updated < MIN_MATCH_COUNT:
            print(
                f"  WARNING: Only {updated}/{total_players} players updated from CSV "
                f"(minimum expected: {MIN_MATCH_COUNT})."
            )
            print(f"  Check that column names match FBREF_PLAYER_COL / FBREF_MINUTES_COL.")
    else:
        # Understat mode: not finding a player at all is a concern; being lower is expected.
        not_found = total_players - found
        if not_found > 4:
            print(
                f"  WARNING: {not_found} players not found in Understat at all "
                f"(name mismatch likely). Check NAME_ALIASES in fetch_minutes.py."
            )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update players.recent_minutes from Understat (default) or FBref CSV (--csv)."
    )
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help="Path to a manually-downloaded FBref squad stats CSV (skips Understat fetch).",
    )
    args = parser.parse_args()

    if args.csv:
        print(f"=== Loading minutes from CSV: {args.csv} ===")
        data = fetch_csv(args.csv)
        # FBref covers all competitions — trust it in both directions.
        update_db(data, allow_decrease=True)
    else:
        print("=== Fetching minutes from Understat ===")
        data = fetch_automated()
        if not data:
            sys.exit(0)
        # Understat is PL-only; never let it reduce a seed.py all-comp estimate.
        update_db(data, allow_decrease=False)
    print("Done.")


if __name__ == "__main__":
    main()
