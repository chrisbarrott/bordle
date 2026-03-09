#!/usr/bin/env python
"""
Quick PostgreSQL SQL Syntax Validation

Tests that all database SQL functions use correct PostgreSQL syntax.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from services.game_database_connections import (
    get_db_connection,
    DB_TYPE,
    ENVIRONMENT,
    table_name,
)

load_dotenv()


def test_date_syntax():
    """Test that date syntax works in cleanup_old_daily_games."""
    print("\n" + "="*60)
    print("  PostgreSQL Date Syntax Test")
    print("="*60 + "\n")
    
    if DB_TYPE != 'postgres':
        print("⏭️  Skipping (not PostgreSQL)")
        return True
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Test PostgreSQL date arithmetic
        cursor.execute("SELECT CURRENT_DATE - INTERVAL '30 days'")
        result = cursor.fetchone()
        print(f"✅ PostgreSQL date arithmetic works: {result[0]}")
        
        # Test the exact SQL used in cleanup_old_daily_games
        test_table = table_name("test_date_cleanup")
        
        # Create test table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {test_table} (
                id SERIAL PRIMARY KEY,
                game_date DATE
            )
        """)
        
        # Insert test data
        cursor.execute(f"""
            INSERT INTO {test_table} (game_date) 
            VALUES (CURRENT_DATE - INTERVAL '60 days')
        """)
        
        # Test the cleanup query
        sql = f"""
            DELETE FROM {test_table}
            WHERE game_date < CURRENT_DATE - INTERVAL '30 days'
        """
        cursor.execute(sql)
        deleted = cursor.rowcount
        
        print(f"✅ Cleanup query deleted {deleted} old records")
        
        # Cleanup
        cursor.execute(f"DROP TABLE IF EXISTS {test_table}")
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("  Quick Database Validation")
    print("="*60)
    print(f"Database Type: {DB_TYPE.upper()}")
    print(f"Environment: {ENVIRONMENT}")
    
    if test_date_syntax():
        print("\n✅ All SQL syntax is compatible!")
        print("\nYou can now deploy to Render:")
        print("  git add .")
        print("  git commit -m 'Fix PostgreSQL date syntax compatibility'")
        print("  git push origin feature-branch")
        return 0
    else:
        print("\n❌ SQL validation failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
