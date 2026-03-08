#!/usr/bin/env python
"""
Validate that all packages in requirements.txt are compatible.

This script:
1. Checks if pip can resolve all dependencies without conflicts
2. Shows any version conflicts that would occur in production
3. Can be run locally before commit, or in CI/CD pipeline

Usage:
    python scripts/validate_requirements.py
    
Exit codes:
    0 - All packages compatible
    1 - Conflicts found
"""

import subprocess
import sys
import tempfile
from pathlib import Path

def validate_requirements():
    """Check if requirements.txt has compatible packages."""
    
    req_file = Path(__file__).parent.parent / "requirements.txt"
    
    if not req_file.exists():
        print(f"❌ requirements.txt not found at {req_file}")
        return False
    
    print("\n" + "="*60)
    print("  Validating Requirements Compatibility")
    print("="*60 + "\n")
    
    # Try to resolve dependencies using pip-compile (if available)
    print("📦 Checking package compatibility...")
    
    try:
        # Use pip to check if all dependencies can be resolved
        # This simulates the install without actually installing
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "-r", str(req_file)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print("❌ Dependency resolution failed!\n")
            print("STDOUT:")
            print(result.stdout)
            print("\nSTDERR:")
            print(result.stderr)
            return False
        else:
            print("✅ All packages are compatible!")
            
            # Extract and show what would be installed
            output_lines = result.stdout.split('\n')
            installing = [line for line in output_lines if 'Collecting' in line or 'Requirement already' in line]
            
            if installing:
                print(f"\n📋 Would install {len(set(installing))} packages:")
                for line in sorted(set(installing))[:5]:  # Show first 5
                    print(f"   {line}")
                if len(set(installing)) > 5:
                    print(f"   ... and {len(set(installing)) - 5} more")
            
            return True
            
    except subprocess.TimeoutExpired:
        print("❌ Validation timed out (took longer than 60 seconds)")
        print("   This might indicate complex dependency resolution")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

def main():
    """Run validation."""
    success = validate_requirements()
    
    print("\n" + "="*60)
    if success:
        print("✅ PASS: Requirements are compatible")
        print("="*60 + "\n")
        return 0
    else:
        print("❌ FAIL: Requirements have conflicts")
        print("="*60 + "\n")
        print("💡 Tips:")
        print("  1. Try: pip install pipdeptree")
        print("     Then: pipdeptree --warn fail -r requirements.txt")
        print("  2. Or run: pip-compile requirements.txt")
        print("     (Install pip-tools: pip install pip-tools)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
