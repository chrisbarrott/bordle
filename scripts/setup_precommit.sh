#!/bin/bash
# Install pre-commit hook to validate requirements.txt before commit
# 
# Usage:
#   bash scripts/setup_precommit.sh
#
# This prevents committing incompatible requirements
# To bypass: git commit --no-verify

set -e

HOOK_DIR=".git/hooks"
HOOK_FILE="$HOOK_DIR/pre-commit"

echo "Setting up pre-commit hook..."

# Create hooks directory if it doesn't exist
mkdir -p "$HOOK_DIR"

# Create pre-commit hook
cat > "$HOOK_FILE" << 'EOF'
#!/bin/bash
# Pre-commit hook: Validate requirements.txt

# Check if requirements.txt was modified
if git diff --cached --name-only | grep -q "requirements.txt"; then
    echo "🔍 Validating requirements.txt..."
    
    if python scripts/validate_requirements.py; then
        echo "✅ Pre-commit validation passed"
    else
        echo "❌ Pre-commit validation failed"
        echo "Fix requirements.txt conflicts and try again"
        echo "   or use: git commit --no-verify (not recommended)"
        exit 1
    fi
fi

exit 0
EOF

# Make hook executable
chmod +x "$HOOK_FILE"

echo "✅ Pre-commit hook installed!"
echo ""
echo "How it works:"
echo "  - Before each commit, requirements.txt is validated"
echo "  - If conflicts found, commit is blocked"
echo "  - Run: python scripts/validate_requirements.py"
echo "    to test locally first"
echo ""
echo "To bypass: git commit --no-verify"
