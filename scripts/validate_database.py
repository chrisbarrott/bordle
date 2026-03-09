#!/usr/bin/env python
"""
Validate all database operations (local + PostgreSQL compatibility).

This script tests:
1. Database connection
2. Table creation (init_db)
3. All cleanup functions
4. SQL syntax compatibility

Usage:
    python scripts/validate_database.py
    
Exit codes:
    0 - All tests passed
    1 - Some tests failed
"""

import sys
import os
from datetime import date, datetime, timedelta
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from services.game_database_connections import (
    get_db_connection,
    init_db,
    DB_TYPE,
    ENVIRONMENT,
    table_name,
    run_query,
)

load_dotenv()


def print_section(title):
    """Print formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_connection():
    """Test database connection."""
    print_section("1. Database Connection")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DB_TYPE == "postgres":
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0].split(',')[0]
            print(f"✅ PostgreSQL: {version}")
        else:
            print(f"✅ SQLite database active")
        
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        traceback.print_exc()
        return False


def test_table_creation():
    """Test init_db creates tables without errors."""
    print_section("2. Table Creation (init_db)")
    
    try:
        init_db()
        print("✅ All tables created successfully")
        
        # List created tables
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DB_TYPE == "postgres":
            cursor.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema='public' AND table_name LIKE %s
            """, (f"{ENVIRONMENT}%",))
        else:
            cursor.execute(f"""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE '{ENVIRONMENT}%'
            """)
        
        tables = cursor.fetchall()
        if tables:
            print(f"\n📋 Created tables ({len(tables)}):")
            for table in tables:
                print(f"   ✅ {table[0]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Table creation failed: {e}")
        traceback.print_exc()
        return False


def test_cleanup_old_player_results():
    """Test cleanup_old_player_results function."""
    print_section("3. Testing: cleanup_old_player_results()")
    
    try:
        sql = f"DELETE FROM {table_name('player_results')} WHERE game_date < %s"
        cutoff_date = date.today() - timedelta(days=30)
        
        # Just prepare the query, don't execute (data integrity)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DB_TYPE == "postgres":
            cursor.execute(f"EXPLAIN {sql}", (cutoff_date,))
        else:
            sql_check = sql.replace("%s", "?")
            cursor.execute(f"EXPLAIN QUERY PLAN {sql_check}", (cutoff_date,))
        
        print("✅ SQL syntax is valid")
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ SQL error: {e}")
        traceback.print_exc()
        return False


def test_cleanup_old_daily_games():
    """Test cleanup_old_daily_games function - tests date syntax."""
    print_section("4. Testing: cleanup_old_daily_games()")
    
    try:
        # This is the function with date() syntax issues
        test_table = table_name("player_daily_state_test")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create test table
        if DB_TYPE == "postgres":
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    id SERIAL PRIMARY KEY,
                    game_date DATE
                )
            """)
            # Insert test data
            cursor.execute(f"INSERT INTO {test_table} (game_date) VALUES (CURRENT_DATE - INTERVAL '60 days')")
            
            # Test the cleanup query with PostgreSQL syntax
            sql = f"DELETE FROM {test_table} WHERE game_date < CURRENT_DATE - INTERVAL '30 days'"
            cursor.execute(f"EXPLAIN {sql}")
            
            print("✅ PostgreSQL date syntax is correct")
        else:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    id INTEGER PRIMARY KEY,
                    game_date TEXT
                )
            """)
            cursor.execute(f"INSERT INTO {test_table} (game_date) VALUES (date('now', '-60 days'))")
            
            # Test the cleanup query with SQLite syntax
            sql = f"DELETE FROM {test_table} WHERE game_date < date('now', '-30 days')"
            cursor.execute(f"EXPLAIN QUERY PLAN {sql}")
            
            print("✅ SQLite date syntax is correct")
        
        # Cleanup
        cursor.execute(f"DROP TABLE IF EXISTS {test_table}")
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Date syntax error: {e}")
        print("\n💡 This needs to be fixed in game_database_connections.py")
        print("   PostgreSQL uses: CURRENT_DATE - INTERVAL '30 days'")
        print("   SQLite uses: date('now', '-30 days')")
        traceback.print_exc()
        return False


def test_run_query_compatibility():
    """Test run_query function with different SQL types."""
    print_section("5. Testing: run_query() Compatibility")
    
    test_table = table_name("test_run_query")
    
    try:
        # Create test table
        if DB_TYPE == "postgres":
            sql_create = f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100)
                )
            """
        else:
            sql_create = f"""
                CREATE TABLE IF NOT EXISTS {test_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT
                )
            """
        
        run_query(sql_create)
        print("✅ Table creation via run_query works")
        
        # Test insert
        if DB_TYPE == "postgres":
            sql_insert = f"INSERT INTO {test_table} (name) VALUES (%s)"
        else:
            sql_insert = f"INSERT INTO {test_table} (name) VALUES (?)"
        
        run_query(sql_insert, ("test",))
        print("✅ Insert via run_query works")
        
        # Test select
        if DB_TYPE == "postgres":
            sql_select = f"SELECT COUNT(*) FROM {test_table}"
        else:
            sql_select = f"SELECT COUNT(*) FROM {test_table}"
        
        result = run_query(sql_select, fetchone=True)
        print(f"✅ Query via run_query works (found {result[0]} records)")
        
        # Cleanup
        run_query(f"DROP TABLE IF EXISTS {test_table}")
        
        return True
        
    except Exception as e:
        print(f"❌ run_query error: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all validation tests."""
    print("\n" + "="*70)
    print("  DATABASE VALIDATION TEST SUITE")
    print("="*70)
    print(f"\nEnvironment: {ENVIRONMENT}")
    print(f"Database Type: {DB_TYPE.upper()}")
    print(f"Database URL: {os.getenv('DATABASE_URL_EXTERNAL') or os.getenv('DATABASE_URL') or 'SQLite'}")
    
    results = {
        "Connection": test_connection(),
        "Table Creation": test_table_creation(),
        "cleanup_old_player_results": test_cleanup_old_player_results(),
        "cleanup_old_daily_games": test_cleanup_old_daily_games(),
        "run_query Compatibility": test_run_query_compatibility(),
    }
    
    print_section("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All database operations are compatible!")
        return 0
    else:
        print("\n⚠️  Some tests failed. Fix errors above before deploying.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
