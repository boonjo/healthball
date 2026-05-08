"""
Computes injury-risk scores and writes them to the DB.

Features per player:
  - currently_injured  (1 if active injury as of run date)
  - age
  - debut_age          (professional debut age — earlier = more load on young body)
  - career_apps        (total career appearances — physical mileage)
  - recent_apps        (appearances in 24/25 + 25/26 — current workload)
  - total_injuries     (career injury count, including ongoing)
  - avg_days_out       (mean; ongoing injuries use days elapsed so far)
  - recent_injuries    (injuries in last 2 seasons)
  - ligament_count     (cruciate / ligament / achilles — highest severity)
  - muscle_count       (hamstring / thigh / adductor / calf / groin / muscle)
  - days_since_last    (365-based recency weight; 365 if currently injured)

Scoring: pure weighted formula — more reliable and interpretable with a small squad.
Risk levels: high ≥ 60 · medium ≥ 20 · low < 20
"""
import os
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DEV_DATABASE_URL")
engine = create_engine(DATABASE_URL)

SEVERE_TYPES = {"cruciate ligament", "ligament", "acl", "achilles"}
MUSCLE_TYPES = {"hamstring", "thigh", "adductor", "calf", "groin", "muscle"}

# UPDATE THIS at the start of each new season (e.g. 26/27 → 2027)
CURRENT_SEASON_YEAR = 2026


def season_year(season: str) -> int:
    """'25/26' → 2026"""
    try:
        return 2000 + int(season.split("/")[-1])
    except (ValueError, IndexError):
        return 0


def build_features(players: pd.DataFrame, injuries: pd.DataFrame) -> pd.DataFrame:
    today = date.today()
    rows = []
    for _, p in players.iterrows():
        pid = p["player_id"]
        age = p["age"] or 25
        currently_injured = int(bool(p.get("currently_injured", False)))
        debut_age = float(p.get("debut_age") or 19)
        career_apps = int(p.get("career_apps") or 0)
        recent_apps = int(p.get("recent_apps") or 0)

        inj = injuries[injuries["player_id"] == pid].copy()
        completed = inj[inj["injury_to"].notna()]
        ongoing = inj[inj["injury_to"].isna()]

        total_injuries = len(inj)

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

        types_lower = inj["injury_type"].str.lower()
        ligament_count = int(types_lower.apply(
            lambda t: any(s in t for s in SEVERE_TYPES)
        ).sum())
        muscle_count = int(types_lower.apply(
            lambda t: any(s in t for s in MUSCLE_TYPES)
        ).sum())

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
            "recent_apps":      recent_apps,
            "total_injuries":   total_injuries,
            "avg_days_out":     round(avg_days_out, 1),
            "recent_injuries":  recent_injuries,
            "ligament_count":   ligament_count,
            "muscle_count":     muscle_count,
            "days_since_last":  round(days_since_last, 1),
        })

    return pd.DataFrame(rows)


def score_formula(row) -> float:
    """Weighted formula score (0–100)."""
    score = 0.0

    # ── Current availability ─────────────────────────────────────────────────
    # Active injury: the player is provably unavailable right now
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
    # Each year before 18 adds 1.5 pts (max 4.5 for age-15 debut)
    score += min(max(0.0, 18.0 - float(row["debut_age"])) * 1.5, 4.5)

    # ── Career mileage — cumulative physical wear ────────────────────────────
    # Peaks at ~430 apps (≈5 pts); linearly scaled
    score += min(float(row["career_apps"]) / 430.0 * 5.0, 5.0)

    # ── Recent workload — fatigue risk from high game volume ─────────────────
    # Penalty kicks in above 70 games across 2 seasons (35/season); max 6 pts
    score += min(max(0.0, float(row["recent_apps"]) - 70.0) * 0.5, 6.0)

    # ── Career injury history ────────────────────────────────────────────────
    score += min(float(row["total_injuries"]) * 4.0, 20.0)

    # ── Injury severity ──────────────────────────────────────────────────────
    score += float(row["ligament_count"]) * 10.0   # cruciate / achilles
    score += float(row["muscle_count"]) * 4.0      # hamstring / muscle

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

    feature_cols = [
        "currently_injured", "age", "debut_age", "career_apps", "recent_apps",
        "total_injuries", "avg_days_out", "recent_injuries",
        "ligament_count", "muscle_count", "days_since_last",
    ]

    scores = features_df.apply(score_formula, axis=1).values

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM risk_scores"))
        for i, row in features_df.iterrows():
            s = float(np.clip(scores[i], 0, 100))
            level = risk_level(s)
            conn.execute(
                text("""
                    INSERT INTO risk_scores (player_id, risk_score, risk_level, features)
                    VALUES (:pid, :score, :level, :features)
                """),
                {
                    "pid":      int(row["player_id"]),
                    "score":    round(s, 1),
                    "level":    level,
                    "features": json.dumps({k: float(row[k]) for k in feature_cols}),
                },
            )
    print("Risk scores written to DB.")

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
