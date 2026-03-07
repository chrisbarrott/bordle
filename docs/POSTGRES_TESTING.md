# Testing PostgreSQL Integration

This guide walks you through testing your PostgreSQL setup locally before deploying to Render.

## Option 1: Quick Test with Render (Easiest)

If you already have a PostgreSQL database on Render:

1. **Deploy your code to Render** with these environment variables:
   ```
   FLASK_ENV=production
   DB_TYPE=postgres
   ```

2. **Check the logs** in Render Dashboard → Logs
   - Look for successful database connections
   - Any errors will show up here

3. **Test the app** by visiting your Render URL and playing a game
   - If it works, your PostgreSQL integration is good!

---

## Option 2: Test Locally with PostgreSQL (Recommended for Development)

### Step 1: Install PostgreSQL Locally

**Windows:**
- Download and install from: https://www.postgresql.org/download/windows/
- Accept default options during installation
- Remember the postgres password you set!

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Linux:**
```bash
sudo apt-get install postgresql postgresql-contrib
```

### Step 2: Create a Test Database

**Windows (using pgAdmin or Command Line):**

Open PowerShell and connect to PostgreSQL:
```powershell
psql -U postgres
```

Then create the database:
```sql
CREATE DATABASE bordle_dev;
\q
```

**macOS/Linux:**
```bash
createdb bordle_dev
```

### Step 3: Configure Your `.env` File

Edit your `.env` file in the project root:

```bash
FLASK_ENV=development
DB_TYPE=postgres
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/bordle_dev
SECRET_KEY=test-secret-key-change-in-production
```

Replace `your_password` with the PostgreSQL password you set during installation.

### Step 4: Run the Integration Test

```bash
python scripts/test_postgres_integration.py
```

Expected output:
```
============================================================
  PostgreSQL Integration Test
============================================================

============================================================
  1. Environment Configuration
============================================================
FLASK_ENV: development
DB_TYPE: postgres
DATABASE_URL: ...@localhost:5432/bordle_dev
✅ Configuration valid

============================================================
  2. Testing Connection
============================================================
✅ PostgreSQL Version: PostgreSQL 15.x (...)
✅ Database: bordle_dev
✅ User: postgres

============================================================
  3. Testing Table Operations
============================================================
✅ Created test table: development_test_connection
✅ Inserted test record
✅ Retrieved test record: hello_postgres
✅ Cleaned up test table

============================================================
  4. Checking Game Tables
============================================================
  ⚠️  development_games: Does not exist yet (will be created on first use)
  ⚠️  development_player_stats: Does not exist yet (will be created on first use)
  ⚠️  development_player_results: Does not exist yet (will be created on first use)
  ⚠️  development_player_daily_state: Does not exist yet (will be created on first use)

============================================================
  Test Summary
============================================================
Environment: ✅ PASS
Connection: ✅ PASS
Table Ops: ✅ PASS
Game Tables: ✅ PASS

Total: 4/4 passed

🎉 All tests passed! PostgreSQL integration is working.
```

### Step 5: Run the Flask App

```bash
python app.py
```

Then visit: http://localhost:5000

Try playing a game. The app will automatically create tables the first time it needs them.

Check your database:
```bash
psql -U postgres -d bordle_dev
```

Then check tables:
```sql
\dt
```

You should see tables like:
```
             List of relations
 Schema |         Name          | Type  | Owner
--------+-----------------------+-------+----------
 public | development_games     | table | postgres
 public | development_player_... | table | postgres
(...)
```

---

## Option 3: Test Without Local PostgreSQL (SQLite Fallback)

If you don't want to install PostgreSQL locally, just use SQLite:

1. **Make sure your `.env` has:**
   ```
   FLASK_ENV=development
   DB_TYPE=sqlite
   # Don't set DATABASE_URL
   ```

2. **Run the app:**
   ```bash
   python app.py
   ```

3. **It will create `db/games.db` automatically**

This works fine for local development, but you won't test the PostgreSQL integration until you deploy to Render.

---

## Option 4: Test with Docker Postgres (No Local Installation)

If you have Docker installed:

```bash
docker run --name bordle-postgres \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=bordle_dev \
  -p 5432:5432 \
  -d postgres:15
```

Then use in `.env`:
```
DATABASE_URL=postgresql://postgres:testpass@localhost:5432/bordle_dev
```

Stop it when done:
```bash
docker stop bordle-postgres
docker rm bordle-postgres
```

---

## Troubleshooting

### "No such host" Error
- **Problem:** PostgreSQL isn't running
- **Solution:** Make sure the database service is started
  - Windows: pg_ctl.exe start -D "C:\Program Files\PostgreSQL\15\data"
  - macOS: brew services start postgresql@15
  - Linux: sudo systemctl start postgresql

### "authentication failed" Error
- **Problem:** Wrong password in CONNECTION_URL
- **Solution:** Reset your postgres password or fix the URL

### "FATAL: database does not exist"
- **Problem:** The database wasn't created
- **Solution:** Run `createdb bordle_dev` (or use pgAdmin to create it)

### "psycopg2 is not installed" Error
- **Problem:** PostgreSQL driver isn't installed
- **Solution:** The pip install already includes it (`psycopg2-binary==2.9.10` in requirements.txt)
  - If still missing: `pip install psycopg2-binary`

---

## What The Test Script Does

The `test_postgres_integration.py` script:

1. **Tests Connection** - Verifies you can connect to PostgreSQL
2. **Shows Database Info** - Displays version, database name, user
3. **Tests CRUD Operations** - Creates a test table, inserts data, retrieves it
4. **Checks Game Tables** - Lists any existing game tables and record counts

All without modifying your actual game data!

---

## Next Steps

Once tests pass:

1. ✅ Run the Flask app locally with PostgreSQL
2. ✅ Play a few games to ensure everything works
3. ✅ Check the database schema with: `\dt` in psql
4. ✅ Deploy to Render with `FLASK_ENV=production` and `DB_TYPE=postgres`
5. ✅ Render automatically uses the linked PostgreSQL database

Your code is already set up to work with both SQLite and PostgreSQL seamlessly!
