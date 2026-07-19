"""
create_db.py - Create the application database if it does not exist yet.

Dialect-aware:
  * SQLite   - there is no server and no CREATE DATABASE; the file springs into
               existence on first connect. We just make sure the parent directory
               exists and report the path.
  * Postgres - connect to the maintenance 'postgres' database and issue
               CREATE DATABASE.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_dialect import normalize_database_url, sqlite_file_path  # noqa: E402


async def create_database():
    load_dotenv()

    # No argument: use the full precedence chain rather than the ambient variable,
    # which on a shared machine may belong to an entirely different project. This
    # function creates databases, so pointing it at the wrong server matters.
    db_url = normalize_database_url()
    url = make_url(db_url)

    # ---- SQLite -----------------------------------------------------------
    if url.get_backend_name() == "sqlite":
        path = sqlite_file_path(db_url)
        if path is None:
            print("SQLite in-memory database selected - nothing to create.")
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            print(f"SQLite database already exists at {path}")
        else:
            # Touch it so the file is present with the expected permissions;
            # the schema itself is created by the backend on startup.
            open(path, "a").close()
            print(f"SQLite database created at {path}")
        return

    # ---- PostgreSQL -------------------------------------------------------
    import asyncpg

    db_name = url.database
    user = url.username
    password = url.password
    host = url.host
    port = url.port or 5432

    print(f"Attempting to create database '{db_name}' at {host}:{port}...")

    try:
        # Connect to the default 'postgres' database to create the new one
        conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database='postgres'
        )

        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )

        if not exists:
            print(f"Database '{db_name}' does not exist. Creating it now...")
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Database '{db_name}' created successfully!")
        else:
            print(f"Database '{db_name}' already exists.")

        await conn.close()
    except asyncpg.exceptions.InvalidPasswordError:
        print("\n" + "="*60)
        print("DATABASE AUTHENTICATION ERROR")
        print("="*60)
        print(f"Failed to connect to PostgreSQL as user '{user}'.")
        print("The password in backend/.env does not match your PostgreSQL password.")
        print("Please edit backend/.env, update the DATABASE_URL with your correct PostgreSQL password, and try again.")
        print("="*60 + "\n")
        sys.exit(1)
    except Exception as e:
        print(f"\nError connecting to PostgreSQL: {e}")
        print("Ensure PostgreSQL is running and the credentials in backend/.env are correct.\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(create_database())
