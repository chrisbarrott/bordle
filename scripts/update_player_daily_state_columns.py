import sqlite3
import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FOLDER = os.path.join(BASE_DIR, '..', 'db')
DB_PATH = os.path.join(DB_FOLDER, 'games.db')
CSV_PATH = os.path.join(DB_FOLDER, 'games.csv')

# Connect to DB
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get existing columns
cursor.execute("PRAGMA table_info(player_daily_state)")

cursor.execute(
    "ALTER TABLE player_daily_state ADD COLUMN hard_mode INTEGER DEFAULT 0"
)
print("✅ Added column: hard_mode")


cursor.execute(
    "ALTER TABLE player_daily_state ADD COLUMN game_result_recorded INTEGER DEFAULT 0"
)
print("✅ Added column: game_result_recorded")


conn.commit()
print("🎉 Migration complete")

conn.close()

