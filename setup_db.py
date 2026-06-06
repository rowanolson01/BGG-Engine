import sqlite3
import pandas as pd
from pathlib import Path

# Paths
DATA_DIR = Path("data")
DB_PATH = Path("data/bgg.db")

def load_csv(filename):
    print(f"Loading {filename}...")
    return pd.read_csv(DATA_DIR / filename)

def setup_database():
    # Load all 4 CSVs
    games = load_csv("games.csv")
    mechanics = load_csv("mechanics.csv")
    themes = load_csv("themes.csv")
    subcategories = load_csv("subcategories.csv")

    # Create SQLite db and write tables
    print("Creating database...")
    conn = sqlite3.connect(DB_PATH)

    games.to_sql("games", conn, if_exists="replace", index=False)
    mechanics.to_sql("mechanics", conn, if_exists="replace", index=False)
    themes.to_sql("themes", conn, if_exists="replace", index=False)
    subcategories.to_sql("subcategories", conn, if_exists="replace", index=False)

    print(f"Done. Tables created:")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for row in cursor.fetchall():
        print(f"  - {row[0]}")

    conn.close()
    print(f"Database saved to {DB_PATH}")

if __name__ == "__main__":
    setup_database()