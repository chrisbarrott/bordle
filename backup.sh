#!/bin/bash
set -e

# Path to your SQLite DB in your app
DB_PATH="db/games.db"

# Make backups folder if missing
mkdir -p backups

# Timestamp for filename
STAMP=$(date +"%Y-%m-%d_%H-%M")

# Copy DB to backup folder
cp "$DB_PATH" "backups/games_$STAMP.db"

echo "Backup created: backups/games_$STAMP.db"