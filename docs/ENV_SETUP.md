# Environment & Database Configuration

## Files Created

- **`services/game_database_config.py`** - Centralized configuration handling
- **`.env.example`** - Template for environment variables (commit to git)
- **`docs/RENDER_DEPLOYMENT.md`** - Full Render deployment guide
- **`.gitignore`** - Already configured, keeps `.env` secret

## Quick Start

### For Local Development

```bash
# 1. Copy template (if you haven't already)
cp .env.example .env

# 2. Edit .env (will use SQLite by default)
# No database setup needed - SQLite works out of the box

# 3. Run the app
python app.py
```

### For Render Deployment

1. **Create PostgreSQL database on Render dashboard**
   - Note the connection details

2. **Link it to your web service**
   - Go to Web Service → Database tab → Link database
   - Render auto-injects `DATABASE_URL`

3. **Set environment variables in Render dashboard**
   ```
   FLASK_ENV=production
   DB_TYPE=postgres
   SECRET_KEY=<your-secret-key>
   ```

4. **Deploy** - that's it! No database setup code needed.

## How It Works

### Automatic Environment Detection

```
Local machine
└─ FLASK_ENV=development → SQLite (no setup)
   
Render (staging/production)  
└─ FLASK_ENV=production → PostgreSQL (DATABASE_URL auto-set by Render)
```

### Connection Priority

1. `DATABASE_URL` (Render's automatic variable)
2. `POSTGRES_DSN` (manual PostgreSQL connections)
3. SQLite (fallback, requires no setup)

## Key Features

✅ **Single codebase** for all environments  
✅ **No secrets in code** - all in environment variables  
✅ **Works offline** - SQLite for local development  
✅ **Zero setup** on Render - just link the database  
✅ **Same config structure** across dev/staging/production  

## Environment Variables Needed

### Local Development
- Optional: Set nothing, SQLite works automatically
- Optional: `FLASK_ENV=development` (default)
- Optional: `SECRET_KEY` for sessions

### Render Production
- `FLASK_ENV=production` (set in Render dashboard)
- `DB_TYPE=postgres` (set in Render dashboard)
- `DATABASE_URL` (auto-set by Render when linking database)
- `SECRET_KEY` (set in Render dashboard)
- Any API keys or email credentials (set in Render dashboard)

## File Structure

```
bordle/
├── app.py                 ← Uses FLASK_ENV to determine behavior
├── .env                   ← Local only (in .gitignore) ← DON'T COMMIT
├── .env.example           ← Template (safe to commit)
├── .gitignore             ← Protects .env from git
├── requirements.txt       ← All dependencies listed
├── docs/
│   ├── RENDER_DEPLOYMENT.md   ← Full deployment guide
│   └── ...other docs
└── services/
    ├── game_database_config.py           ← Central config (NEW)
    └── game_database_connections.py  ← Handles DATABASE_URL
```

## Existing Code Already Supports This

Your `game_database_connections.py` already has the right logic:
- Checks for `DATABASE_URL` ✓
- Checks for `POSTGRES_DSN` ✓  
- Falls back to SQLite ✓
- Uses psycopg2 for Postgres ✓

The new `game_database_config.py` just makes it more explicit and maintainable.
