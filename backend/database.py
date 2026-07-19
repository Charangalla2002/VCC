"""
database.py – Async SQLAlchemy 2.0 engine, session factory, and dependency.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase

from db_dialect import create_engine_from_url, normalize_database_url

load_dotenv()

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# The dialect is chosen purely from DATABASE_URL. It defaults to a SQLite file at
# the repo root so the app runs on a bare laptop; point it at postgresql://... and
# everything switches over. normalize_database_url() also makes a relative SQLite
# path absolute, so the backend (cwd=backend/) and the detection process
# (cwd=repo root) resolve to the same file.
# No argument: let normalize_database_url() apply the full precedence chain
# (VCC_DATABASE_URL -> this repo's .env -> ambient DATABASE_URL -> default).
# Passing os.getenv("DATABASE_URL") here would hand it the ambient value directly
# and bypass that chain, which is how a foreign DATABASE_URL took over.
DATABASE_URL: str = normalize_database_url()

engine = create_engine_from_url(DATABASE_URL)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models)
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session and close it when the request is done."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
