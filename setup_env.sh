#!/bin/bash
# Activate existing virtual environment and install requirements (macOS/Linux)

set -e

echo "======================================"
echo "  Bordle Environment Setup"
echo "======================================"
echo ""

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found at .venv"
    echo "Please create it first with: python3 -m venv .venv"
    echo ""
    exit 1
fi

# Activate venv
echo "✅ Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install requirements
echo "📦 Installing requirements from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "======================================"
echo "✅ Setup complete!"
echo "======================================"
echo ""
echo "Your virtual environment is ready:"
echo "  - Located in: ./.venv"
echo "  - Currently: ACTIVATED"
echo ""
echo "Next steps:"
echo "  1. Validate packages: python scripts/validate_requirements.py"
echo "  2. Run the app: python app.py"
echo "  3. Run tests: python scripts/test_postgres_integration.py"
echo ""
echo "To deactivate: deactivate"
