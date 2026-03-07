"""
Database and application configuration.

For Render deployment:
- Render automatically provides DATABASE_URL env var for PostgreSQL
- Set FLASK_ENV to 'development', 'staging', or 'production'
- No additional configuration needed beyond deploying the app

For local development:
- Create a .env file with the variables from .env.example
- python-dotenv will automatically load these
"""

import os
from typing import Literal

# Load environment variables
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    FLASK_ENV: Literal["development", "staging", "production"] = os.getenv(
        "FLASK_ENV", "development"
    )
    DB_TYPE: Literal["sqlite", "postgres"] = os.getenv("DB_TYPE", "sqlite").lower()


class DevelopmentConfig(Config):
    """Development configuration - uses SQLite by default."""

    DB_TYPE = "sqlite"
    DEBUG = True


class StagingConfig(Config):
    """Staging configuration - uses PostgreSQL on Render."""

    DB_TYPE = "postgres"
    DEBUG = False


class ProductionConfig(Config):
    """Production configuration - uses PostgreSQL on Render."""

    DB_TYPE = "postgres"
    DEBUG = False


def get_config() -> Config:
    """Return appropriate config based on FLASK_ENV."""
    env = os.getenv("FLASK_ENV", "development").lower()

    config_map = {
        "development": DevelopmentConfig,
        "staging": StagingConfig,
        "production": ProductionConfig,
    }

    return config_map.get(env, DevelopmentConfig)()


def get_database_url() -> str:
    """
    Get the database connection string.

    For Render: Uses DATABASE_URL env var (automatically set)
    For local: Uses POSTGRES_DSN if set, otherwise uses SQLite path
    """
    # Check for Render's DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Render uses 'postgres://' but psycopg2 prefers 'postgresql://'
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    # Fallback to explicit POSTGRES_DSN
    postgres_dsn = os.getenv("POSTGRES_DSN")
    if postgres_dsn:
        return postgres_dsn

    # Return None - caller should handle SQLite fallback
    return None


# Current configuration instance
current_config = get_config()
