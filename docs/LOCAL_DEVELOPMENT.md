# Local Development & Requirements Validation

This guide helps you validate package compatibility locally before deploying to Render.

## Quick Start

### Windows

```bash
# Activate existing environment and install requirements
setup_env.bat
```

### macOS/Linux

```bash
# Activate existing environment and install requirements
bash setup_env.sh
```

---

## What These Scripts Do

### `setup_env.bat` / `setup_env.sh`

**Activates your existing `.venv` and:**
1. Checks that `.venv` exists
2. Activates it
3. Upgrades pip, setuptools, wheel
4. Installs all packages from `requirements.txt`
5. Prints next steps

**You'll see:**
```
======================================
  Bordle Environment Setup
======================================

✅ Activating virtual environment...
📦 Upgrading pip...
📦 Installing requirements from requirements.txt...

======================================
✅ Setup complete!
======================================

Your virtual environment is ready:
  - Located in: .\.venv
  - Currently: ACTIVATED

Next steps:
  1. Validate packages: python scripts/validate_requirements.py
  2. Run the app: python app.py
```

---

## Validate Package Compatibility

After setup, validate that all packages work together:

```bash
python scripts/validate_requirements.py
```

**Output example:**

```
============================================================
  Validating Requirements Compatibility
============================================================

📦 Checking package compatibility...
✅ All packages are compatible!

📋 Would install 65 packages:
   Collecting ansible-core==2.17.2
   Collecting anyio==4.9.0
   ... and 63 more

============================================================
✅ PASS: Requirements are compatible
============================================================
```

**If conflicts found:**
```
❌ Dependency resolution failed!

STDOUT:
...conflicting version errors...

💡 Tips:
  1. Try: pip install pipdeptree
     Then: pipdeptree --warn fail -r requirements.txt
  2. Or run: pip-compile requirements.txt
     (Install pip-tools: pip install pip-tools)
```

---

## Run the App Locally

Once validated, run the app:

```bash
# Activate environment (if not already active)
source venv/bin/activate          # macOS/Linux
# or
venv\Scripts\activate.bat         # Windows

# Run the app
python app.py

# Test PostgreSQL connection
python scripts/test_postgres_integration.py
```

---

## Pre-Commit Hook (Optional)

Automatically validate `requirements.txt` before commits:

### Setup (One-time)

```bash
# macOS/Linux
bash scripts/setup_precommit.sh

# Windows: Manually add to .git/hooks/pre-commit (script above)
```

### How it works

Every time you try to commit, if `requirements.txt` changed:
1. Validation runs automatically
2. If conflicts found → commit blocked
3. Fix the issue and try again

```bash
# This will run validation first
git commit -m "Update requirements"

# If validation passes
# → Commit succeeds ✅

# If validation fails
# → Commit blocked ❌
# → Fix and try again

# To skip (not recommended):
git commit --no-verify
```

---

## Development Workflow

1. **Initial Setup**
   ```bash
   setup_env.bat  # or setup_env.sh
   ```

2. **Make changes** to `requirements.txt` or code

3. **Validate locally**
   ```bash
   python scripts/validate_requirements.py
   ```

4. **Test locally**
   ```bash
   python app.py
   # Visit http://localhost:5000
   ```

5. **Commit & Push**
   ```bash
   git add requirements.txt
   git commit -m "Update requirements"
   # Pre-commit hook runs validation
   git push origin feature-branch
   ```

6. **Deploy to Render**
   - Render automatically builds and deploys
   - No surprises! ✅

---

## Troubleshooting

### "venv is not recognized"

Make sure you're in the project directory:
```bash
cd c:\bordle
setup_env.bat
```

If `.venv` doesn't exist, create it first:
```bash
python -m venv .venv
setup_env.bat
```

### "requirements.txt has conflicts"

**Option 1: Use pip-tools**
```bash
pip install pip-tools
pip-compile requirements.txt
# This creates requirements.txt with pinned sub-dependencies
```

**Option 2: Check with pipdeptree**
```bash
pip install pipdeptree
pipdeptree --warn fail -r requirements.txt
# Shows which packages conflict
```

**Option 3: Downgrade conflicting packages**
- Update specific versions in `requirements.txt`
- Run validation again

### "Build is still failing on Render"

1. **Validate locally first:**
   ```bash
   python scripts/validate_requirements.py
   ```

2. **Check exact error** in Render logs

3. **Common fixes:**
   - Downgrade problematic package (like we did with `pyproj`, `greenlet`)
   - Use `--only-binary` flags in `render.yaml`
   - Increase build timeout in `render.yaml`

---

## Environment Deactivation

When done developing:

```bash
# Exit the virtual environment
deactivate

# You're back to your system Python
```

To activate again:
```bash
source .venv/bin/activate          # macOS/Linux
# or
.venv\Scripts\activate.bat         # Windows
```

---

## Verify Everything Works

**Checklist before pushing:**

- [ ] Run: `python scripts/validate_requirements.py` → ✅ PASS
- [ ] Run: `python app.py` → App starts, no errors
- [ ] Run: `python scripts/test_postgres_integration.py` → ✅ All tests pass
- [ ] Visit: http://localhost:5000 → App loads
- [ ] Play a game → Works correctly
- [ ] Check logs → No errors

Only after all ✅ should you commit and push!

---

## Files Reference

| File | Purpose |
|------|---------|
| `setup_env.bat` | Windows setup script |
| `setup_env.sh` | macOS/Linux setup script |
| `scripts/validate_requirements.py` | Validate package compatibility |
| `scripts/setup_precommit.sh` | Install pre-commit hook (optional) |
| `.git/hooks/pre-commit` | Auto-validation on commit (optional) |

---

## Quick Commands

```bash
# Setup (activate .venv and install requirements)
setup_env.bat              # Windows
bash setup_env.sh          # macOS/Linux

# Validate
python scripts/validate_requirements.py

# Run app
python app.py

# Test database
python scripts/test_postgres_integration.py

# Deactivate environment
deactivate

# Activate manually
source .venv/bin/activate          # macOS/Linux
.venv\Scripts\activate.bat         # Windows

# Create pre-commit hook
bash scripts/setup_precommit.sh
```
