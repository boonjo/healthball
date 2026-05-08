import os
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DEV_DATABASE_URL")
engine = create_engine(DATABASE_URL)

PLAYERS_CSV = os.path.join(os.path.dirname(__file__), "players_to_scrape.csv")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def clean_date(date_str: str) -> str | None:
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_days(days_str: str) -> int:
    digits = "".join(c for c in days_str if c.isdigit())
    return int(digits) if digits else 0


def scrape_player_injuries(player_name: str, url: str) -> list[dict]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Request failed for {player_name}: {e}")
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    table = soup.find("table", {"class": "items"})
    if table is None:
        print(f"  No injury table found for {player_name}")
        return []

    rows = []
    cumulative_minutes: dict[str, int] = {}

    for tr in table.find_all("tr")[1:]:
        cols = tr.find_all("td")
        if len(cols) < 6:
            continue

        season = cols[0].text.strip()
        injury_type = cols[1].text.strip()
        injury_from = clean_date(cols[2].text)
        injury_to = clean_date(cols[3].text)
        days_out = parse_days(cols[4].text)
        games_missed_str = cols[5].text.strip()
        games_missed = int(games_missed_str) if games_missed_str.isdigit() else 0

        minutes_before = cumulative_minutes.get(season, 0)
        minutes_total = minutes_before + games_missed * 90
        cumulative_minutes[season] = minutes_total

        rows.append(
            {
                "player_name": player_name,
                "season": season,
                "injury_type": injury_type,
                "days_out": days_out,
                "injury_from": injury_from,
                "injury_to": injury_to,
                "games_missed": games_missed,
                "minutes_before": minutes_before,
                "minutes_total": minutes_total,
            }
        )

    return rows


def upsert_injuries(player_name: str, injuries: list[dict]) -> None:
    with engine.begin() as conn:
        player_row = conn.execute(
            text("SELECT player_id FROM players WHERE name = :name"),
            {"name": player_name},
        ).fetchone()

        if player_row is None:
            print(f"  Player '{player_name}' not found — run load_players.py first")
            return

        player_id = player_row[0]
        conn.execute(
            text("DELETE FROM injuries WHERE player_id = :pid"),
            {"pid": player_id},
        )

        for inj in injuries:
            conn.execute(
                text(
                    """
                    INSERT INTO injuries (
                        player_id, season, injury_type, injury_from, injury_to,
                        days_out, games_missed, minutes_before, minutes_total
                    ) VALUES (
                        :player_id, :season, :injury_type, :injury_from, :injury_to,
                        :days_out, :games_missed, :minutes_before, :minutes_total
                    )
                    """
                ),
                {
                    "player_id": player_id,
                    "season": inj["season"],
                    "injury_type": inj["injury_type"],
                    "injury_from": inj["injury_from"],
                    "injury_to": inj["injury_to"],
                    "days_out": inj["days_out"],
                    "games_missed": inj["games_missed"],
                    "minutes_before": inj["minutes_before"],
                    "minutes_total": inj["minutes_total"],
                },
            )

    print(f"  Loaded {len(injuries)} injuries for {player_name}")


def main() -> None:
    df = pd.read_csv(PLAYERS_CSV)
    for _, row in df.iterrows():
        player_name = row["player_name"]
        url = row["url"]
        print(f"Scraping {player_name}...")
        injuries = scrape_player_injuries(player_name, url)
        if injuries:
            upsert_injuries(player_name, injuries)
        time.sleep(2)


if __name__ == "__main__":
    main()
