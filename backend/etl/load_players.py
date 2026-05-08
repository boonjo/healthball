"""
Upserts Arsenal player metadata from players_to_scrape.csv into the players table.
Run this before load_injuries.py.
"""
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

PLAYERS_CSV = os.path.join(os.path.dirname(__file__), "players_to_scrape.csv")

# Static metadata not available from Transfermarkt injury page — Arsenal 2025-26 squad
PLAYER_META = {
    # Goalkeepers
    "David Raya":           {"age": 30, "nationality": "Spain"},
    "Kepa Arrizabalaga":    {"age": 30, "nationality": "Spain"},
    # Defenders
    "Ben White":            {"age": 28, "nationality": "England"},
    "William Saliba":       {"age": 24, "nationality": "France"},
    "Gabriel Magalhães":    {"age": 28, "nationality": "Brazil"},
    "Riccardo Calafiori":   {"age": 23, "nationality": "Italy"},
    "Jurriën Timber":       {"age": 24, "nationality": "Netherlands"},
    "Cristhian Mosquera":   {"age": 21, "nationality": "Spain"},
    "Myles Lewis-Skelly":   {"age": 19, "nationality": "England"},
    # Midfielders
    "Declan Rice":          {"age": 26, "nationality": "England"},
    "Martin Ødegaard":      {"age": 26, "nationality": "Norway"},
    "Mikel Merino":         {"age": 29, "nationality": "Spain"},
    "Martin Zubimendi":     {"age": 26, "nationality": "Spain"},
    "Christian Nørgaard":   {"age": 31, "nationality": "Denmark"},
    # Forwards
    "Bukayo Saka":          {"age": 23, "nationality": "England"},
    "Gabriel Martinelli":   {"age": 24, "nationality": "Brazil"},
    "Kai Havertz":          {"age": 26, "nationality": "Germany"},
    "Viktor Gyökeres":      {"age": 27, "nationality": "Sweden"},
    "Gabriel Jesus":        {"age": 28, "nationality": "Brazil"},
    "Leandro Trossard":     {"age": 31, "nationality": "Belgium"},
    "Noni Madueke":         {"age": 23, "nationality": "England"},
    "Eberechi Eze":         {"age": 27, "nationality": "England"},
}


def main() -> None:
    df = pd.read_csv(PLAYERS_CSV)
    with engine.begin() as conn:
        for _, row in df.iterrows():
            name = row["player_name"]
            meta = PLAYER_META.get(name, {})
            conn.execute(
                text(
                    """
                    INSERT INTO players (name, position, age, nationality, tm_id)
                    VALUES (:name, :position, :age, :nationality, :tm_id)
                    ON CONFLICT (tm_id) DO UPDATE SET
                        name        = EXCLUDED.name,
                        position    = EXCLUDED.position,
                        age         = EXCLUDED.age,
                        nationality = EXCLUDED.nationality,
                        scraped_at  = NOW()
                    """
                ),
                {
                    "name": name,
                    "position": row["position"],
                    "age": meta.get("age"),
                    "nationality": meta.get("nationality"),
                    "tm_id": int(row["tm_id"]),
                },
            )
            print(f"Upserted {name}")

    print("Done.")


if __name__ == "__main__":
    main()
