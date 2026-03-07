# Bordle on Render - Deployment Guide

## Database Setup on Render

### 1. Create PostgreSQL Database on Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → Select "PostgreSQL"
3. Fill in:
   - **Name**: `bordle-db` (or similar)
   - **Database**: `bordle` (or your preferred name)
   - **User**: `bordle` (or your preferred user)
   - **Region**: Same as your web service for best performance
   - **PostgreSQL Version**: 15 or higher
4. Click "Create Database"

Render will automatically provide connection details. Copy the **External Database URL** - this will be your `DATABASE_URL`.

### 2. Configure Web Service Environment Variables

In your Render Web Service dashboard:

1. Go to **Environment** section
2. Add the following environment variables:

```
FLASK_ENV=production
DB_TYPE=postgres
```

That's it! Render automatically sets `DATABASE_URL` when you link a PostgreSQL database to your service.

### 3. Database Linking (Alternative to Manual Setup)

Instead of copying the connection string, you can let Render auto-link:

1. In your Web Service settings, go to "Database" tab
2. Link your PostgreSQL database
3. Render automatically injects `DATABASE_URL` into your environment

### Environment Variables Summary

| Variable | Value | Where Set |
|----------|-------|-----------|
| `FLASK_ENV` | `production` | Render Environment Dashboard |
| `DB_TYPE` | `postgres` | Render Environment Dashboard |
| `DATABASE_URL` | Auto-set by Render | Set when linking database to service |
| `SECRET_KEY` | Your secret key | Render Environment Dashboard |

## Local Development

### Using SQLite (No Database Setup Needed)

```bash
# .env file (create locally only, don't commit)
FLASK_ENV=development
DB_TYPE=sqlite
```

Then run:
```bash
pip install -r requirements.txt
python app.py
```

### Using PostgreSQL Locally (Optional)

If you want to test with PostgreSQL locally:

```bash
# Install PostgreSQL locally
# Create a database: createdb bordle_dev

# .env file
FLASK_ENV=development
DB_TYPE=postgres
DATABASE_URL=postgresql://username:password@localhost:5432/bordle_dev
```

## How It Works

### Database Connection Logic

The app detects your environment and uses the correct database:

```python
# config.py determines DB_TYPE based on FLASK_ENV
FLASK_ENV=development  → uses SQLite (no setup needed)
FLASK_ENV=staging      → uses PostgreSQL (uses DATABASE_URL)
FLASK_ENV=production   → uses PostgreSQL (uses DATABASE_URL)
```

### Connection String Handling

1. First checks for `DATABASE_URL` (Render's automatic variable)
2. Falls back to `POSTGRES_DSN` if set (for manual PostgreSQL)
3. Uses SQLite as final fallback

Render's `DATABASE_URL` uses the `postgres://` scheme, so the code automatically converts it to `postgresql://` for compatibility with modern psycopg2.

## Troubleshooting

### "No Postgres DSN configured" Error

- **Development**: Make sure `DB_TYPE=sqlite` in your `.env`
- **Production**: Verify database is linked in Render dashboard → Database tab
- **Production**: Check `DATABASE_URL` exists in Environment variables

### Connection Timeout

- Database may still be initializing (can take 1-2 minutes)
- Check database status in Render dashboard
- Verify your region matches your web service region

### Database Not Found

- Verify database name in Render matches your app's expectations
- Check that web service is linked to the correct database

## First Deployment Checklist

- [ ] PostgreSQL database created on Render
- [ ] Web service linked to PostgreSQL (Database tab)
- [ ] `FLASK_ENV=production` set in Environment variables
- [ ] `DB_TYPE=postgres` set in Environment variables  
- [ ] `SECRET_KEY` set to a strong random value
- [ ] Git push triggers deployment
- [ ] Check deployment logs for errors

## Security Notes

✅ **Good Practice**:
- Passwords stored only in Render Environment variables
- `.env` file added to `.gitignore`
- `DATABASE_URL` never appears in code

❌ **Don't Do**:
- Commit `.env` files to git
- Hardcode database credentials in Python files
- Use the same password across environments
