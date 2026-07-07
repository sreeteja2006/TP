"""
db.py - Shared PostgreSQL connection helper for TradePro.

All modules use get_pg_conn() to obtain a database connection.
Render automatically injects DATABASE_URL into the environment
when a PostgreSQL database is linked to the web service.
"""

import os
import psycopg2
import psycopg2.extras


def get_pg_conn():
    """Return a new psycopg2 connection using DATABASE_URL env var."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "On Render, link a PostgreSQL database to this service. "
            "Locally, set DATABASE_URL=postgresql://user:pass@host:5432/dbname"
        )
    # psycopg2 needs postgresql:// not postgres:// (Render uses the latter)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(database_url)
    return conn


def get_dict_conn():
    """Return a connection whose cursors return dict-like rows (RealDictCursor)."""
    conn = get_pg_conn()
    return conn
