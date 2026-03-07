# Render Deployment Issues & Solutions

## Build Hanging on "Preparing metadata"

**Problem:** Build gets stuck on:
```
Preparing metadata (pyproject.toml): started
Preparing metadata (pyproject.toml): still running...
```

**Root Cause:** 
Render's build environment is attempting to compile heavy GIS libraries from source (`geopandas`, `fiona`, `shapely`, `pyproj`). These require C/C++ compilation which is:
- Time-consuming
- Resource-intensive on Render's constrained build servers
- Prone to timeouts

**Solution 1: Extend Build Timeout (Easiest)**

Render now uses `render.yaml` to configure services. The file includes:
```yaml
buildTimeout: 3600  # 60 minutes (default is 30)
```

This gives the compiler more time to finish.

**Solution 2: Use Render's Pre-compiled Wheels**

Instead of compiling, Render should use pre-built binary wheels. Create a `.buildpacks` file:

```
https://github.com/gaffneyc/buildpack-python-fiona.git
https://github.com/heroku/heroku-buildpack-python.git
```

However, the simpler approach is using `render.yaml` with extended timeout.

**Solution 3: Separate Dev Dependencies**

If build time is still an issue:

```bash
# Production dependencies only (faster)
requirements.txt

# Optional dev tools (only for local development)
requirements-dev.txt
```

On Render, only use `requirements.txt`:
```yaml
buildCommand: pip install -r requirements.txt
```

---

## Files Added for Render Support

| File | Purpose |
|------|---------|
| `render.yaml` | Render service configuration with extended timeout |
| `pyproject.toml` | Python project metadata (helps pip build) |
| `requirements-dev.txt` | Development dependencies (not used on Render) |

---

## Deployment Steps

### 1. Push to GitHub

```bash
git add .
git commit -m "Add Render deployment config"
git push origin feature-branch
```

### 2. Deploy on Render

1. **Connect GitHub repo** to Render
2. **Create new Web Service** → Connect GitHub
3. **Select your repository and branch**
4. **Configure:**
   - Name: `bordle` (or similar)
   - Environment: `Python`
   - Build command: (optional if using render.yaml)
   - Start command: `gunicorn app:app` (optional if using render.yaml)
5. **Add environment variables:**
   - `FLASK_ENV=production`
   - `DB_TYPE=postgres`
   - `SECRET_KEY=<your-secret>`
6. **Link PostgreSQL database** (if not already linked)
7. **Deploy!**

The `render.yaml` file will automatically configure timeouts and build settings.

---

## If Build Still Hangs

**Common fixes in order:**

1. **Check Render logs** 
   - Deployments → [Your Service] → Logs
   - Look for `gcc` or `clang` commands that are still running

2. **Increase timeout further**
   - Edit `render.yaml`: change `buildTimeout: 3600` to `7200` (2 hours)

3. **Check disk space**
   - Render build environment might be out of space
   - Try deploying after deleting unused branches/images

4. **Clear build cache**
   - In Render dashboard: Deployments → Clear build cache
   - Redeploy

5. **Check for processes taking too long**
   - `geopandas` can be very slow to install
   - If hanging persists, consider using a slimmer geospatial library or caching compiled wheels

---

## Production Optimization

For faster deployments in the future:

1. **Use binary wheels** instead of compilation
   ```bash
   pip install --only-binary=:all: package-name
   ```

2. **Cache build artifacts** on Render (if available)

3. **Consider using conda** instead of pip for scientific packages
   - Create `environment.yml` instead of `requirements.txt`

4. **Pin versions** for reproducibility
   - All your packages already have pinned versions ✓

---

## Verify Deployment

Once deployed on Render:

1. **Check PostgreSQL connection**
   ```bash
   Visit https://your-render-url/health or play a game
   ```

2. **Check logs for errors**
   ```
   Service → Logs → Look for "Database connected" or errors
   ```

3. **Test the app**
   - Visit your Render URL
   - Play a game
   - Check that stats are saved to PostgreSQL

---

## Environment Variables for Render

| Variable | Value | Where |
|----------|-------|-------|
| `FLASK_ENV` | `production` | Render Dashboard |
| `DB_TYPE` | `postgres` | Render Dashboard |
| `SECRET_KEY` | Your secret key | Render Dashboard |
| `DATABASE_URL` | Auto-set by Render | Set when linking PostgreSQL |
| Other (emails, API keys) | Your values | Render Dashboard |

---

## CI/CD with Render

Render automatically deploys when you git push:

1. **Push to branch**
   ```bash
   git push origin feature-branch
   ```

2. **Render detects push** and starts build

3. **Build times:**
   - First deploy: 5-10 minutes (including dependency download)
   - Subsequent: 2-5 minutes (some caching)
   - With 60-min timeout: Usually finishes in 5-15 minutes

---

## Local Development

For faster iteration:

```bash
# Install production dependencies
pip install -r requirements.txt

# Or install with dev tools
pip install -r requirements.txt requirements-dev.txt

# Run locally
python app.py
```

No need to install `ansible-core` locally if you're not using it.
