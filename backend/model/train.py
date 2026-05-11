"""
Computes injury-risk scores and writes them to the DB.

Features per player (10 numeric + 1 categorical):
  - currently_injured  (1 if active injury as of run date)
  - age
  - debut_age          (professional debut age — earlier = more load on young body)
  - career_apps        (total career appearances — physical mileage)
  - recent_minutes     (minutes played in 24/25 + 25/26 — workload proxy)
  - total_injuries     (career injury count, including ongoing)
  - severity_score     (taxonomy-weighted sum of career injury severity)
  - avg_days_out       (mean; ongoing injuries use days elapsed so far)
  - recent_injuries    (injuries in last 2 seasons)
  - days_since_last    (365-based recency weight; 365 if currently injured)
  - position_group     (GK / CB / FB / WB / CM / AM / WF / IW / Wide / CF — drives multipliers)

Scoring: weighted additive formula with position-adjusted multipliers on severity
and workload components. Score capped at 100.
Risk levels: high ≥ 60 · medium ≥ 20 · low < 20

Time-series: scores are APPENDED each run (not replaced). API queries fetch the
latest row per player via LATERAL. Run train.py any time to update scores.
"""
import math
import os
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

# ── Injury taxonomy ───────────────────────────────────────────────────────────
# Evaluated in order — first match wins. Each injury gets one category weight.
# (keywords, category_label, weight_per_injury)
INJURY_TAXONOMY = [
    (["cruciate", "acl"],              "structural_acl",       15.0),
    (["achilles"],                     "structural_achilles",  12.0),
    (["ligament"],                     "structural_ligament",   8.0),
    (["fracture", "broken"],           "bone",                  6.0),
    (["hamstring"],                    "muscle_hamstring",       5.0),
    (["adductor", "groin"],            "muscle_adductor",       4.5),
    (["thigh", "quad"],                "muscle_quad",           4.0),
    (["calf"],                         "muscle_calf",           4.0),
    (["muscle"],                       "muscle_generic",        3.5),
    (["knee"],                         "joint_knee",            3.0),
    (["ankle"],                        "joint_ankle",           2.5),
    (["shoulder"],                     "joint_shoulder",        2.0),
    (["back", "hip"],                  "joint_back",            1.5),
]
INJURY_OTHER_WEIGHT = 1.0  # fallback for unmatched types

# ── Position groups and multipliers ──────────────────────────────────────────
# Maps the position column value to a group, then to (severity_mult, workload_mult).
# severity_mult: wide/forward positions sustain more muscle injuries → higher weight.
# workload_mult: GK minutes are less physically demanding than outfield → lower weight.
POSITION_GROUPS = {
    "GK":  "GK",
    "CB":  "CB",
    "RB":  "FB",  "LB": "FB",
    "WB":  "WB",
    "CM":  "CM",
    "CAM": "AM",
    "IW":  "IW",
    "RW":  "Wide", "LW": "Wide",
    "WF":  "WF",
    "CF":  "CF",
}

# (severity_mult, workload_mult)
POSITION_MULTIPLIERS = {
    "GK":   (0.55, 0.65),
    "CB":   (0.85, 0.85),
    "FB":   (1.20, 1.10),
    "WB":   (1.25, 1.20),
    "CM":   (1.00, 1.00),
    "AM":   (1.00, 1.00),
    "IW":   (1.20, 1.15),
    "WF":   (1.10, 1.00),
    "Wide": (1.30, 1.15),
    "CF":   (1.15, 1.00),
}

# Half-life ~4.6 yrs: 1yr→86%, 3yr→64%, 5yr→47%, 10yr→22%. Floor at 0.20.
SEVERITY_DECAY_RATE = 0.15

# UPDATE THIS at the start of each new season (e.g. 26/27 → 2027)
CURRENT_SEASON_YEAR = 2026


def season_year(season: str) -> int:
    """'25/26' → 2026"""
    try:
        return 2000 + int(season.split("/")[-1])
    except (ValueError, IndexError):
        return 0


def classify_injury(injury_type: str) -> float:
    """Return taxonomy weight for a single injury type string."""
    lower = injury_type.lower()
    for keywords, _, weight in INJURY_TAXONOMY:
        if any(k in lower for k in keywords):
            return weight
    return INJURY_OTHER_WEIGHT


def build_features(players: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    today = date.today()
    rows = []
    for _, p in players.iterrows():
        pid = p["player_id"]
        age = p["age"] or 25
        currently_injured = int(bool(p.get("currently_injured", False)))
        debut_age = float(p.get("debut_age") or 19)
        career_apps = int(p.get("career_apps") or 0)
        recent_minutes = int(p.get("recent_minutes") or 0)
        position = str(p.get("position") or "CM")
        position_group = POSITION_GROUPS.get(position, "CM")

        inj = injuries[injuries["player_id"] == pid].copy()
        completed = inj[inj["injury_to"].notna()]
        ongoing = inj[inj["injury_to"].isna()]

        total_injuries = len(inj)

        # Severity score — taxonomy weight with exponential time-decay.
        # Older injuries contribute less (floor 0.20); recent ones are near full weight.
        severity_score = 0.0
        for _, inj_row in inj.iterrows():
            weight = classify_injury(str(inj_row["injury_type"]))
            if pd.notna(inj_row["injury_from"]):
                try:
                    inj_date = pd.to_datetime(inj_row["injury_from"]).date()
                    years_ago = max(0.0, (today - inj_date).days / 365.25)
                    decay = max(0.20, math.exp(-SEVERITY_DECAY_RATE * years_ago))
                except (ValueError, TypeError):
                    decay = 0.50
            else:
                decay = 0.50
            severity_score += weight * decay

        # avg days out — actual for completed, elapsed so far for ongoing
        days_list = []
        for _, row in completed.iterrows():
            if pd.notna(row["days_out"]):
                days_list.append(float(row["days_out"]))
        for _, row in ongoing.iterrows():
            if pd.notna(row["injury_from"]):
                elapsed = (today - pd.to_datetime(row["injury_from"]).date()).days
                days_list.append(float(elapsed))
        avg_days_out = float(np.mean(days_list)) if days_list else 0.0

        # recent = 25/26 and 24/25 seasons
        recent = inj[inj["season"].apply(season_year) >= CURRENT_SEASON_YEAR - 1]
        recent_injuries = len(recent)

        # Recency weight: max if currently injured, else days left inside 1-yr window
        if currently_injured:
            days_since_last = 365.0
        else:
            days_since_last = 0.0
            if not completed.empty:
                last_to = pd.to_datetime(completed["injury_to"]).max()
                if pd.notna(last_to):
                    delta = (today - last_to.date()).days
                    days_since_last = float(max(0, 365 - delta))

        rows.append({
            "player_id":        int(pid),
            "currently_injured": currently_injured,
            "age":              age,
            "debut_age":        debut_age,
            "career_apps":      career_apps,
            "recent_minutes":   recent_minutes,
            "total_injuries":   total_injuries,
            "severity_score":   round(severity_score, 1),
            "avg_days_out":     round(avg_days_out, 1),
            "recent_injuries":  recent_injuries,
            "days_since_last":  round(days_since_last, 1),
            "position_group":   position_group,
        })

    return pd.DataFrame(rows)


def score_formula(row) -> float:
    """Weighted formula score (0–100) with position-adjusted severity and workload."""
    score = 0.0
    pos_group = str(row["position_group"])
    severity_mult, workload_mult = POSITION_MULTIPLIERS.get(pos_group, (1.0, 1.0))

    # ── Current availability ─────────────────────────────────────────────────
    score += int(row["currently_injured"]) * 12

    # ── Age / physical maturity ──────────────────────────────────────────────
    age = int(row["age"])
    if age >= 32:
        score += 18
    elif age >= 30:
        score += 10
    elif age >= 28:
        score += 5

    # ── Early debut — extra load accumulated on a young body ─────────────────
    # Threshold 19: debut at 18→1.5 pts, 17→3.0 pts, ≤16→4.5 pts (max).
    score += min(max(0.0, 19.0 - float(row["debut_age"])) * 1.5, 4.5)

    # ── Career mileage — cumulative physical wear ────────────────────────────
    score += min(float(row["career_apps"]) / 430.0 * 5.0, 5.0)

    # ── Recent workload — position-adjusted; threshold 6 000 min over 2 seasons
    # Rate: 0.002 pts/min above threshold → cap of 6 pts reached at 9 000 min
    score += min(
        max(0.0, float(row["recent_minutes"]) - 6000.0) * 0.002 * workload_mult,
        6.0,
    )

    # ── Career injury history ────────────────────────────────────────────────
    score += min(float(row["total_injuries"]) * 4.0, 20.0)

    # ── Injury severity — taxonomy-weighted, position-adjusted ───────────────
    # ACL=15, Achilles=12, ligament=8, fracture=6, hamstring=5, adductor=4.5,
    # quad/calf=4, muscle_generic=3.5, knee=3, ankle=2.5, shoulder=2, back=1.5
    score += float(row["severity_score"]) * severity_mult

    # ── Average time lost per injury ─────────────────────────────────────────
    score += min(float(row["avg_days_out"]) / 5.0, 10.0)

    # ── Recent injury load (25/26 + 24/25) ───────────────────────────────────
    score += min(float(row["recent_injuries"]) * 6.0, 18.0)

    # ── Recency of last injury (0 = fit >1 yr; 12 = just returned / currently out)
    score += min(float(row["days_since_last"]) / 365.0 * 12.0, 12.0)

    return min(score, 100.0)


def risk_level(score: float) -> str:
    if score >= 60:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def main() -> None:
    with engine.connect() as conn:
        players = pd.read_sql(text("SELECT * FROM players"), conn)
        injuries = pd.read_sql(text("SELECT * FROM injuries"), conn)

    features_df = build_features(players, injuries)

    numeric_feature_cols = [
        "currently_injured", "age", "debut_age", "career_apps", "recent_minutes",
        "total_injuries", "severity_score", "avg_days_out", "recent_injuries",
        "days_since_last",
    ]

    scores = features_df.apply(score_formula, axis=1).values

    # Append scores — do NOT delete previous rows (time-series history preserved)
    with engine.begin() as conn:
        for i, row in features_df.iterrows():
            s = float(np.clip(scores[i], 0, 100))
            level = risk_level(s)
            features_dict = {k: float(row[k]) for k in numeric_feature_cols}
            features_dict["position_group"] = str(row["position_group"])
            conn.execute(
                text("""
                    INSERT INTO risk_scores (player_id, risk_score, risk_level, features)
                    VALUES (:pid, :score, :level, :features)
                """),
                {
                    "pid":      int(row["player_id"]),
                    "score":    round(s, 1),
                    "level":    level,
                    "features": json.dumps(features_dict),
                },
            )
    print("Risk scores appended to DB.")

    # Print ranked summary
    results = [
        (int(features_df.iloc[i]["player_id"]), round(float(scores[i]), 1))
        for i in range(len(scores))
    ]
    results.sort(key=lambda x: -x[1])
    print("\nRanked scores:")
    for pid, s in results:
        name = players[players["player_id"] == pid]["name"].values[0]
        print(f"  {s:5.1f}  {risk_level(s):6}  {name}")


if __name__ == "__main__":
    main()
