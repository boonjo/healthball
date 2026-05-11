#!/usr/bin/env python3
"""
Transition Healthball to the next Arsenal season.

Usage (run from backend/):
    python new_season.py 26/27

What it does automatically:
  seed.py
    - Bumps SQUAD_SEASON, PREV_SEASON, SQUAD_UPDATED
    - Bumps every player's age by 1
    - Adds "26/27": 0 to each SEASON_APPS entry
    - Inserts a blank INJURIES_2627 = [] block
    - Appends INJURIES_2627 to ALL_INJURIES
  model/train.py
    - Bumps CURRENT_SEASON_YEAR

Remaining manual steps are printed after the script runs.
"""

import re
import sys
from datetime import date
from pathlib import Path

HERE         = Path(__file__).parent
SEED_PATH    = HERE / "seed.py"
TRAIN_PATH   = HERE / "model" / "train.py"
FETCH_PATH   = HERE / "etl" / "fetch_minutes.py"


def parse_season(raw: str) -> tuple[str, int]:
    """'26/27' → ('26/27', 2027)"""
    parts = raw.strip().split("/")
    if len(parts) != 2 or not all(len(p) == 2 and p.isdigit() for p in parts):
        sys.exit(f"ERROR: season must be YY/YY format, got {raw!r}")
    season_str = f"{parts[0]}/{parts[1]}"
    year = 2000 + int(parts[1])
    return season_str, year


def safe(season: str) -> str:
    """'26/27' → '2627'"""
    return season.replace("/", "")


def next_season(season: str) -> str:
    """'26/27' → '27/28'"""
    a, b = season.split("/")
    return f"{int(a)+1:02d}/{int(b)+1:02d}"


def bump_age(m: re.Match) -> str:
    """Increment the age field in a SQUAD tuple."""
    return m.group(1) + str(int(m.group(3)) + 1) + m.group(4)


def update_seed(seed: str, new_s: str, old_s: str, year: int) -> str:
    today = date.today().isoformat()

    # 1. SQUAD_SEASON
    seed = re.sub(
        r'(SQUAD_SEASON\s+=\s+)"[^"]+"',
        f'\\1"{new_s}"',
        seed,
    )

    # 2. PREV_SEASON (old current becomes new prev)
    seed = re.sub(
        r'(PREV_SEASON\s+=\s+)"[^"]+"',
        f'\\1"{old_s}"',
        seed,
    )

    # 3. SQUAD_UPDATED
    seed = re.sub(
        r'(SQUAD_UPDATED\s+=\s+)"[^"]+"',
        f'\\1"{today}"',
        seed,
    )

    # 4. Bump every player age by 1.
    # Pattern: ("Player name",  "POS",  <age>, "Nationality"
    # Only SQUAD tuples begin with a quoted name followed by an ALL-CAPS position code.
    seed = re.sub(
        r'("([^"]+)",\s+"[A-Z]+",\s+)(\d+)(,\s+")',
        bump_age,
        seed,
    )

    # 5. Add new season key to every SEASON_APPS entry.
    # Each entry ends with:  "25/26": <N>}
    # Becomes:               "25/26": <N>, "26/27": 0}
    seed = re.sub(
        '"' + re.escape(old_s) + r'": (\d+)}',
        f'"{old_s}": ' + r'\1' + f', "{new_s}": 0}}',
        seed,
    )

    # 6. Insert blank INJURIES block before the marker line.
    new_safe = safe(new_s)
    new_block = (
        f"\nINJURIES_{new_safe} = [\n"
        f"    # Add injury rows for {new_s} here as they occur\n"
        f"    # (player_id, season, injury_type, from, to, days_out, games_missed, min_before, min_total)\n"
        f"]\n"
    )
    marker = "# __NEXT_INJURIES_BLOCK__"
    if marker in seed:
        seed = seed.replace(marker, new_block + marker)
    else:
        sys.exit("ERROR: marker '# __NEXT_INJURIES_BLOCK__' not found in seed.py — do not remove it")

    # 7. Append new season to ALL_INJURIES.
    seed = re.sub(
        r"(ALL_INJURIES = .+)$",
        lambda m: m.group(1) + f" + INJURIES_{new_safe}" if f"INJURIES_{new_safe}" not in m.group(1) else m.group(1),
        seed,
        flags=re.MULTILINE,
    )

    return seed


def update_train(train: str, year: int) -> str:
    return re.sub(
        r"(CURRENT_SEASON_YEAR\s+=\s+)\d+",
        f"\\g<1>{year}",
        train,
    )


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python new_season.py <new-season>   e.g. 26/27")

    new_s, new_year = parse_season(sys.argv[1])

    seed  = SEED_PATH.read_text()
    train = TRAIN_PATH.read_text()
    fetch = FETCH_PATH.read_text()

    # Derive the current (outgoing) season from the file
    m = re.search(r'SQUAD_SEASON\s+=\s+"([^"]+)"', seed)
    if not m:
        sys.exit("ERROR: SQUAD_SEASON not found in seed.py")
    old_s = m.group(1)

    if old_s == new_s:
        sys.exit(f"ERROR: seed.py is already on season {new_s}")

    old_safe = safe(old_s)
    new_safe = safe(new_s)

    print(f"\nTransitioning  {old_s}  →  {new_s}\n")

    seed  = update_seed(seed, new_s, old_s, new_year)
    train = update_train(train, new_year)
    fetch = update_train(fetch, new_year)  # same CURRENT_SEASON_YEAR constant

    SEED_PATH.write_text(seed)
    TRAIN_PATH.write_text(train)
    FETCH_PATH.write_text(fetch)

    print(f"  seed.py              SQUAD_SEASON → {new_s!r}")
    print(f"  seed.py              PREV_SEASON  → {old_s!r}")
    print(f"  seed.py              SQUAD_UPDATED → {date.today().isoformat()!r}")
    print(f"  seed.py              All ages bumped +1")
    print(f"  seed.py              SEASON_APPS + SEASON_MINUTES — added \"{new_s}\": 0 for every player")
    print(f"  seed.py              INJURIES_{new_safe} = [] block inserted")
    print(f"  seed.py              ALL_INJURIES now includes INJURIES_{new_safe}")
    print(f"  model/train.py       CURRENT_SEASON_YEAR → {new_year}")
    print(f"  etl/fetch_minutes.py CURRENT_SEASON_YEAR → {new_year}")

    print(f"""
Manual steps still needed
─────────────────────────
1. SEASON_APPS + SEASON_MINUTES "{old_s}" values — verify/correct the final
   counts/minutes for the just-ended season (FBref fetch_minutes.py gets
   minutes automatically, but final SEASON_APPS app counts need manual check).

2. SQUAD career_apps — update total career appearances for all players
   (check Transfermarkt or Wikipedia for the end-of-season totals).

3. INJURIES_{old_safe} ongoing rows — close any injuries that were still
   ongoing at season end: fill injury_to, days_out, games_missed and set
   currently_injured=False on the player in SQUAD.

4. Transfers — remove departed players, add new signings with their injury
   history. If the squad size or order changes, update the ID constants too.

5. currently_injured flags — set True for anyone injured at the new
   season's start, and add their opening injury row to INJURIES_{new_safe}.

Then run:  bash refresh.sh

During {new_s}:
  New injury?   Add row to INJURIES_{new_safe}, set currently_injured=True, run refresh.sh
  Player back?  Fill that row's end dates, set currently_injured=False, run refresh.sh
  After big run of games? Update SEASON_APPS "{new_s}": <value> with accumulated apps.
""")


if __name__ == "__main__":
    main()
