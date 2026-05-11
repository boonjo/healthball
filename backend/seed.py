"""
Arsenal squad seeder — manages all historical data.

Wipes all data and re-seeds from scratch every time it runs.
All squad and injury data lives here. Edit this file to keep it current.

HOW TO MAINTAIN
===============
New injury mid-season:
  Add a row to INJURIES_<current_season> with injury_to=None, days_out=None,
  games_missed=None. Set currently_injured=True on the player in SQUAD.

Player returns from injury:
  Fill injury_to, days_out, games_missed on the ongoing row.
  Set currently_injured=False on the player.

New season: run  python new_season.py 26/27
  The script handles ages, season strings, a blank INJURIES block, and
  CURRENT_SEASON_YEAR in train.py. Manual steps it prints after running:
    - Fill this season's SEASON_APPS final values
    - Update career_apps for all players
    - Handle transfers
    - Close ongoing injuries from last season

Loan changes:
  Remove loanee from SQUAD (and their INJURIES_* rows) on departure.
  Add them back when they return.

Player IDs are determined by insertion order in SQUAD (first entry = 1).
The constants below must match that order — update them if the list changes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).parent / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))

# ── Season config ─────────────────────────────────────────────────────────────
# new_season.py updates these automatically — do not rename them
SQUAD_SEASON  = "25/26"
PREV_SEASON   = "24/25"
SQUAD_UPDATED = "2026-05-08"  # date squad stats (age, career_apps) were last verified

# ── Player ID constants ───────────────────────────────────────────────────────
# Must match SQUAD insertion order below. Update if list changes.
RAYA          = 1
KEPA          = 2
WHITE         = 3
SALIBA        = 4
GABRIEL       = 5
CALAFIORI     = 6
TIMBER        = 7
MOSQUERA      = 8
LEWIS_SKELLY  = 9
RICE          = 10
ODEGAARD      = 11
MERINO        = 12
ZUBIMENDI     = 13
NORGAARD      = 14
SAKA          = 15
MARTINELLI    = 16
HAVERTZ       = 17
GYKERES       = 18
JESUS         = 19
TROSSARD      = 20
MADUEKE       = 21
EZE           = 22

# ── Per-season appearances ────────────────────────────────────────────────────
# recent_apps is computed as PREV_SEASON + SQUAD_SEASON — no manual summing needed.
# At end of each season: fill in the final value for SQUAD_SEASON (currently ~0 placeholders
# for in-progress seasons, real values once the season ends).
# new_season.py adds the new season key (= 0) for all players automatically.
SEASON_APPS = {
    #               24/25  25/26
    RAYA:         {"24/25": 38, "25/26": 38},
    KEPA:         {"24/25": 10, "25/26": 10},
    WHITE:        {"24/25": 20, "25/26": 28},
    SALIBA:       {"24/25": 35, "25/26": 35},
    GABRIEL:      {"24/25": 36, "25/26": 37},
    CALAFIORI:    {"24/25": 18, "25/26": 29},
    TIMBER:       {"24/25": 35, "25/26": 23},
    MOSQUERA:     {"24/25": 28, "25/26": 29},
    LEWIS_SKELLY: {"24/25":  5, "25/26": 35},
    RICE:         {"24/25": 44, "25/26": 45},
    ODEGAARD:     {"24/25": 30, "25/26": 40},
    MERINO:       {"24/25": 37, "25/26": 27},
    ZUBIMENDI:    {"24/25": 36, "25/26": 37},
    NORGAARD:     {"24/25": 30, "25/26": 31},
    SAKA:         {"24/25": 37, "25/26": 40},
    MARTINELLI:   {"24/25": 35, "25/26": 35},
    HAVERTZ:      {"24/25": 45, "25/26": 46},
    GYKERES:      {"24/25": 47, "25/26": 48},
    JESUS:        {"24/25": 10, "25/26": 30},
    TROSSARD:     {"24/25": 38, "25/26": 40},
    MADUEKE:      {"24/25": 34, "25/26": 34},
    EZE:          {"24/25": 33, "25/26": 33},
}

# ── Per-season minutes played ─────────────────────────────────────────────────
# Estimated total minutes across all competitions (league + cups + European + internationals).
# GK minutes ≈ apps × 90; outfield starters ≈ apps × 82–88; rotation ≈ apps × 65–75.
# Update at end of each season with actual totals (source: Transfermarkt / FBref).
# new_season.py adds the new season key (= 0) for all players automatically.
SEASON_MINUTES = {
    #               24/25   25/26
    RAYA:         {"24/25": 3420, "25/26": 3420},   # GK: 38 × 90
    KEPA:         {"24/25":  900, "25/26":  900},   # GK backup: 10 × 90
    WHITE:        {"24/25": 1640, "25/26": 2296},   # starter: ×82
    SALIBA:       {"24/25": 3080, "25/26": 3080},   # starter: 35 × 88
    GABRIEL:      {"24/25": 3132, "25/26": 3219},   # starter: ×87
    CALAFIORI:    {"24/25": 1350, "25/26": 2175},   # injury-hit: ×75
    TIMBER:       {"24/25": 2800, "25/26": 1840},   # post-ACL: ×80
    MOSQUERA:     {"24/25": 1820, "25/26": 1885},   # rotation: ×65
    LEWIS_SKELLY: {"24/25":  375, "25/26": 2625},   # breakthrough: ×75
    RICE:         {"24/25": 3872, "25/26": 3960},   # starter: ×88
    ODEGAARD:     {"24/25": 2520, "25/26": 3360},   # ×84 (missed ankle spell)
    MERINO:       {"24/25": 2886, "25/26": 2106},   # ×78 (shoulder + foot)
    ZUBIMENDI:    {"24/25": 2952, "25/26": 3034},   # starter: ×82
    NORGAARD:     {"24/25": 2160, "25/26": 2232},   # rotation: ×72
    SAKA:         {"24/25": 3256, "25/26": 3520},   # starter: ×88
    MARTINELLI:   {"24/25": 2975, "25/26": 2975},   # starter: ×85
    HAVERTZ:      {"24/25": 3600, "25/26": 3680},   # high-volume: ×80
    GYKERES:      {"24/25": 3854, "25/26": 3936},   # high-volume: ×82
    JESUS:        {"24/25":  720, "25/26": 2160},   # injury-hit: ×72
    TROSSARD:     {"24/25": 2584, "25/26": 2720},   # rotation: ×68
    MADUEKE:      {"24/25": 2380, "25/26": 2380},   # rotation: ×70
    EZE:          {"24/25": 2475, "25/26": 2475},   # rotation: ×75
}

# ── Squad ─────────────────────────────────────────────────────────────────────
# Columns: name, position, age, nationality, tm_id, currently_injured, debut_age, career_apps
# (recent_apps is computed from SEASON_APPS above — do not add it here)
#
# debut_age   — age at first senior professional appearance (any club)
# career_apps — total career appearances, all clubs + internationals
#
# Excluded (on loan): Oleksandr Zinchenko (Nottingham Forest),
#                     Fabio Vieira (Hamburger SV)

SQUAD = [
    # 1  debut: Blackburn 2013 (age 17)
    ("David Raya",         "GK",  30, "Spain",       208136, False, 17, 410),
    # 2  debut: Athletic Club B 2013 (age 19)
    ("Kepa Arrizabalaga",  "GK",  30, "Spain",       192279, False, 19, 340),
    # 3  debut: Newport County loan 2017 (age 19)
    ("Ben White",          "RB",  28, "England",     335721, False, 19, 310),
    # 4  debut: Saint-Étienne Sep 2018 (age 17)
    ("William Saliba",     "CB",  24, "France",      495666, False, 17, 280),
    # 5  debut: Avai loan 2017 (age 21)
    ("Gabriel Magalhães",  "CB",  28, "Brazil",      424028, False, 21, 300),
    # 6  debut: Roma 2021 (age 18)
    ("Riccardo Calafiori", "LB",  23, "Italy",       502821, False, 18, 150),
    # 7  debut: Utrecht 2019 (age 18) — currently injured (groin, since 2026-03-14)
    ("Jurriën Timber",     "LB",  24, "Netherlands", 558773, True,  18, 175),
    # 8  debut: Valencia 2022 (age 18)
    ("Cristhian Mosquera", "CB",  21, "Spain",       646750, False, 18,  80),
    # 9  debut: Arsenal Sep 2024 (age 17)
    ("Myles Lewis-Skelly", "LB",  19, "England",     890721, False, 17,  40),
    # 10 debut: West Ham 2017 (age 18)
    ("Declan Rice",        "CM",  26, "England",     357662, False, 18, 434),
    # 11 debut: Strømsgodset Apr 2014 (age 15)
    ("Martin Ødegaard",    "CAM", 26, "Norway",      316264, False, 15, 430),
    # 12 debut: Osasuna 2015 (age 20) — currently injured (fractured foot, since 2026-02-01)
    ("Mikel Merino",       "CM",  29, "Spain",       301386, True,  20, 310),
    # 13 debut: Real Sociedad B 2019 (age 20)
    ("Martin Zubimendi",   "CM",  26, "Spain",       423440, False, 20, 230),
    # 14 debut: Brøndby 2013 (age 18)
    ("Christian Nørgaard", "CM",  31, "Denmark",     148367, False, 18, 460),
    # 15 debut: Arsenal Nov 2018 (age 17)
    ("Bukayo Saka",        "IW",  23, "England",     433177, False, 17, 330),
    # 16 debut: Ituano Mar 2018 (age 16)
    ("Gabriel Martinelli", "LW",  24, "Brazil",      534272, False, 16, 230),
    # 17 debut: Leverkusen Oct 2016 (age 17)
    ("Kai Havertz",        "CAM", 26, "Germany",     387150, False, 17, 380),
    # 18 debut: Brommapojkarna 2015 (age 17)
    ("Viktor Gyökeres",    "CF",  27, "Sweden",      325443, False, 17, 427),
    # 19 debut: Palmeiras Mar 2015 (age 17)
    ("Gabriel Jesus",      "CF",  28, "Brazil",      363205, False, 17, 400),
    # 20 debut: KRC Genk 2013 (age 18)
    ("Leandro Trossard",   "WF",  31, "Belgium",     384156, False, 18, 380),
    # 21 debut: PSV 2021 (age 19)
    ("Noni Madueke",       "RW",  23, "England",     503987, False, 19, 140),
    # 22 debut: QPR 2017 (age 19)
    ("Eberechi Eze",       "CAM", 27, "England",     479999, False, 19, 280),
]

assert len(SQUAD) == 22, "Update player ID constants if squad size changes"

# ── Injuries ──────────────────────────────────────────────────────────────────
# Columns: player_id, season, injury_type,
#          injury_from, injury_to (None = ongoing),
#          days_out (None = ongoing), games_missed (None = ongoing),
#          minutes_before, minutes_total

# Stable history — only edit to correct mistakes
INJURIES_PRE_2425 = [
    # Kepa
    (KEPA,      "19/20", "Shoulder Injury",           "2020-02-15", "2020-04-30", 75, 10,   0,  900),
    (KEPA,      "22/23", "Thigh Muscle Injury",       "2023-02-01", "2023-03-05", 32,  5,   0,  450),
    (KEPA,      "23/24", "Muscle Injury",             "2024-01-10", "2024-02-01", 22,  3,   0,  270),
    # Ben White
    (WHITE,     "23/24", "Hamstring Injury",          "2024-01-10", "2024-02-14", 35,  5,   0,  450),
    # Saliba
    (SALIBA,    "22/23", "Back Problems",             "2023-03-01", "2023-03-22", 21,  3,   0,  270),
    # Gabriel Magalhães
    (GABRIEL,   "21/22", "Achilles Tendon",           "2022-01-05", "2022-02-10", 36,  5,   0,  450),
    (GABRIEL,   "23/24", "Knee Injury",               "2024-03-15", "2024-04-30", 46,  7,   0,  630),
    # Timber
    (TIMBER,    "23/24", "Cruciate Ligament Injury",  "2023-08-12", "2024-06-01", 294, 40,  0, 3600),
    # Mosquera
    (MOSQUERA,  "23/24", "Ankle Injury",              "2024-02-01", "2024-02-14", 13,  2,   0,  180),
    # Ødegaard
    (ODEGAARD,  "21/22", "Knee Injury",               "2021-11-15", "2021-12-01", 16,  2,   0,  180),
    # Merino
    (MERINO,    "22/23", "Ankle Injury",              "2023-01-10", "2023-02-05", 26,  4,   0,  360),
    # Zubimendi
    (ZUBIMENDI, "23/24", "Muscle Injury",             "2024-04-01", "2024-04-15", 14,  2,   0,  180),
    # Nørgaard
    (NORGAARD,  "21/22", "Achilles Tendon",           "2022-03-01", "2022-04-15", 45,  6,   0,  540),
    (NORGAARD,  "23/24", "Knee Problems",             "2024-02-10", "2024-03-01", 20,  3,   0,  270),
    # Saka
    (SAKA,      "21/22", "Knee Problems",             "2021-11-03", "2021-11-20", 17,  2,   0,  180),
    # Martinelli
    (MARTINELLI,"22/23", "Ankle Injury",              "2022-12-20", "2023-01-15", 26,  4,   0,  360),
    (MARTINELLI,"23/24", "Hamstring Injury",          "2024-03-10", "2024-04-05", 26,  4,   0,  360),
    # Havertz
    (HAVERTZ,   "23/24", "Knee Problems",             "2024-04-20", "2024-05-05", 15,  2,   0,  180),
    # Gyökeres
    (GYKERES,   "22/23", "Muscle Injury",             "2023-01-10", "2023-01-24", 14,  2,   0,  180),
    # Jesus
    (JESUS,     "22/23", "Cruciate Ligament Injury",  "2022-12-09", "2023-06-15", 187, 26,  0, 2340),
    (JESUS,     "23/24", "Hamstring Injury",          "2023-09-20", "2023-10-20", 30,  4,   0,  360),
    # Trossard
    (TROSSARD,  "21/22", "Hamstring Injury",          "2021-11-20", "2021-12-15", 25,  4,   0,  360),
    # Madueke
    (MADUEKE,   "23/24", "Muscle Injury",             "2023-11-01", "2023-11-20", 19,  3,   0,  270),
    # Eze
    (EZE,       "21/22", "Hamstring Injury",          "2021-10-02", "2021-11-10", 39,  5,   0,  450),
    (EZE,       "23/24", "Cruciate Ligament Injury",  "2024-04-26", "2024-09-20", 147, 20,  0, 1800),
]

INJURIES_2425 = [
    (RAYA,      "24/25", "Knee Problems",             "2024-10-15", "2024-10-29", 14,  2,   0,  180),
    (WHITE,     "24/25", "Groin Injury",              "2024-11-03", "2024-11-21", 18,  3, 450,  720),
    (CALAFIORI, "24/25", "Hamstring Injury",          "2024-11-20", "2024-12-10", 20,  3,   0,  270),
    (CALAFIORI, "24/25", "Muscle Injury",             "2025-02-14", "2025-03-05", 19,  3, 270,  540),
    (TIMBER,    "24/25", "Muscle Injury",             "2024-11-25", "2024-12-10", 15,  2,   0,  180),
    (RICE,      "24/25", "Hamstring Injury",          "2025-03-01", "2025-03-22", 21,  3,   0,  270),
    (ODEGAARD,  "24/25", "Ankle Ligament Injury",     "2024-11-05", "2025-01-20", 76, 10,   0,  900),
    (MERINO,    "24/25", "Shoulder Injury",           "2024-08-14", "2024-09-30", 47,  7,   0,  630),
    (SAKA,      "24/25", "Hamstring Injury",          "2024-12-22", "2025-02-10", 50,  7,   0,  630),
    (JESUS,     "24/25", "Knee Injury",               "2024-10-15", "2024-12-01", 47,  7, 360,  990),
    (TROSSARD,  "24/25", "Muscle Injury",             "2024-10-25", "2024-11-12", 18,  3,   0,  270),
    (MADUEKE,   "24/25", "Hamstring Injury",          "2025-01-15", "2025-02-10", 26,  4,   0,  360),
]

INJURIES_2526 = [
    # injury_to=None → ongoing; fill in when player returns
    (TIMBER,    "25/26", "Groin Injury",              "2026-03-14", None,         None, None, 0, None),
    (MERINO,    "25/26", "Fractured Foot",            "2026-02-01", None,         None, None, 0, None),
    (JESUS,     "25/26", "Thigh Muscle Injury",       "2025-09-05", "2025-10-10", 35,   5,   0,  450),
]

# new_season.py inserts the next block here automatically — do not move this marker
# __NEXT_INJURIES_BLOCK__

ALL_INJURIES = INJURIES_PRE_2425 + INJURIES_2425 + INJURIES_2526

# ── DB write ──────────────────────────────────────────────────────────────────

with engine.begin() as conn:
    conn.execute(text("TRUNCATE risk_scores, injuries, players RESTART IDENTITY CASCADE"))
print("Tables cleared.")

with engine.begin() as conn:
    for pid_1based, p in enumerate(SQUAD, start=1):
        name, pos, age, nat, tmid, ci, debut_age, career_apps = p
        recent_apps = (
            SEASON_APPS.get(pid_1based, {}).get(PREV_SEASON,   0) +
            SEASON_APPS.get(pid_1based, {}).get(SQUAD_SEASON,  0)
        )
        recent_minutes = (
            SEASON_MINUTES.get(pid_1based, {}).get(PREV_SEASON,   0) +
            SEASON_MINUTES.get(pid_1based, {}).get(SQUAD_SEASON,  0)
        )
        conn.execute(text("""
            INSERT INTO players
              (name, position, age, nationality, tm_id,
               currently_injured, debut_age, career_apps, recent_apps, recent_minutes)
            VALUES
              (:name, :position, :age, :nationality, :tm_id,
               :ci, :debut_age, :career_apps, :recent_apps, :recent_minutes)
        """), dict(name=name, position=pos, age=age, nationality=nat, tm_id=tmid,
                   ci=ci, debut_age=debut_age, career_apps=career_apps,
                   recent_apps=recent_apps, recent_minutes=recent_minutes))
print(f"Inserted {len(SQUAD)} players.")

with engine.begin() as conn:
    for inj in ALL_INJURIES:
        conn.execute(text("""
            INSERT INTO injuries
              (player_id, season, injury_type, injury_from, injury_to,
               days_out, games_missed, minutes_before, minutes_total)
            VALUES
              (:pid, :season, :itype, :ifrom, :ito, :days, :games, :mbefore, :mtotal)
        """), {
            "pid":     inj[0], "season": inj[1], "itype": inj[2],
            "ifrom":   inj[3], "ito":    inj[4], "days":  inj[5],
            "games":   inj[6], "mbefore":inj[7], "mtotal":inj[8],
        })
print(f"Inserted {len(ALL_INJURIES)} injury records.")
print(f"\nSquad season: {SQUAD_SEASON}  |  Stats verified: {SQUAD_UPDATED}")
