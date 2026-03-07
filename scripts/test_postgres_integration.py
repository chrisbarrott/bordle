#!/usr/bin/env python
"""
Test PostgreSQL Integration

This script validates that:
1. PostgreSQL is configured and reachable
2. The database is accessible
3. Tables can be created/initialized
4. Basic CRUD operations work

Usage (local):
    # First, set up .env file with your PostgreSQL connection
    DB_TYPE=postgres FLASK_ENV=development python scripts/test_postgres_integration.py

Usage (Render):
    # Render automatically sets DATABASE_URL - just run it
    python scripts/test_postgres_integration.py
"""

import os
import sys
from datetime import date

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from services.game_database_connections import (
    get_db_connection,
    get_postgres_connection,
    run_query,
    table_name,
    DB_TYPE,
    ENVIRONMENT,
)

load_dotenv()


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_connection():
    """Test that we can connect to the database."""
    print_section("1. Testing Connection")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DB_TYPE == "postgres":
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            print(f"✅ PostgreSQL Version: {version[0].split(',')[0]}")
            
            cursor.execute("SELECT current_database(), current_user;")
            db_info = cursor.fetchone()
            print(f"✅ Database: {db_info[0]}")
            print(f"✅ User: {db_info[1]}")
        else:
            print(f"✅ Using SQLite at: {os.getenv('DB_PATH', 'db/games.db')}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def test_environment():
    """Display current environment configuration."""
    print_section("2. Environment Configuration")
    
    print(f"FLASK_ENV: {ENVIRONMENT}")
    print(f"DB_TYPE: {DB_TYPE}")
    
    if DB_TYPE == "postgres":
        database_url = os.getenv("DATABASE_URL")
        postgres_dsn = os.getenv("POSTGRES_DSN")
        
        if database_url:
            # Mask password in connection string
            masked_url = database_url.split("@")[1] if "@" in database_url else database_url
            print(f"DATABASE_URL: ...@{masked_url}")
        elif postgres_dsn:
            masked_dsn = postgres_dsn.split("@")[1] if "@" in postgres_dsn else postgres_dsn
            print(f"POSTGRES_DSN: ...@{masked_dsn}")
        else:
            print("❌ No database connection string found!")
            return False
    
    print("✅ Configuration valid")
    return True


def test_table_operations():
    """Test creating, writing, and reading from a test table."""
    print_section("3. Testing Table Operations")
    
    test_table = table_name("test_connection")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Drop test table if it exists
        if DB_TYPE == "postgres":
            cursor.execute(f"DROP TABLE IF EXISTS {test_table};")
        else:
            cursor.execute(f"DROP TABLE IF EXISTS {test_table}")
        
        # Create test table
        if DB_TYPE == "postgres":
            cursor.execute(f"""
                CREATE TABLE {test_table} (
                    id SERIAL PRIMARY KEY,
                    test_value VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            cursor.execute(f"""
                CREATE TABLE {test_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        
        print(f"✅ Created test table: {test_table}")
        
        # Insert test data
        if DB_TYPE == "postgres":
            cursor.execute(f"INSERT INTO {test_table} (test_value) VALUES (%s);", ("hello_postgres",))
        else:
            cursor.execute(f"INSERT INTO {test_table} (test_value) VALUES (?);", ("hello_sqlite",))
        
        print("✅ Inserted test record")
        
        # Read test data
        if DB_TYPE == "postgres":
            cursor.execute(f"SELECT test_value FROM {test_table} LIMIT 1;")
        else:
            cursor.execute(f"SELECT test_value FROM {test_table} LIMIT 1;")
        
        result = cursor.fetchone()
        print(f"✅ Retrieved test record: {result[0]}")
        
        # Cleanup
        cursor.execute(f"DROP TABLE {test_table};")
        conn.commit()
        conn.close()
        print(f"✅ Cleaned up test table")
        return True
        
    except Exception as e:
        print(f"❌ Table operations failed: {e}")
        return False


def test_game_tables():
    """Check if game tables exist and show their record counts."""
    print_section("4. Checking Game Tables")
    
    tables_to_check = [
        "games",
        "player_stats",
        "player_results",
        "player_daily_state",
    ]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for table_base in tables_to_check:
            table = table_name(table_base)
            
            try:
                if DB_TYPE == "postgres":
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                else:
                    cursor.execute(f"SELECT COUNT(*) FROM {table};")
                
                count = cursor.fetchone()[0]
                print(f"  ✅ {table}: {count} records")
            except Exception as e:
                if "does not exist" in str(e) or "no such table" in str(e):
                    print(f"  ⚠️  {table}: Does not exist yet (will be created on first use)")
                else:
                    print(f"  ❌ {table}: Error - {e}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to check tables: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  PostgreSQL Integration Test")
    print("="*60)
    
    results = {
        "Environment": test_environment(),
        "Connection": test_connection(),
        "Table Ops": test_table_operations(),
        "Game Tables": test_game_tables(),
    }
    
    print_section("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All tests passed! PostgreSQL integration is working.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check your configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
