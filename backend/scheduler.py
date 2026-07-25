"""
scheduler.py - APScheduler AsyncIOScheduler for periodic background jobs.

The mv_* analytics views used to be PostgreSQL MATERIALIZED VIEWs refreshed here
on a timer. They are now PLAIN VIEWS on both PostgreSQL and SQLite (see
db_dialect.py), which are always current, so there is nothing left to refresh -
the refresh job has been removed and refresh_materialized_views() is a no-op kept
only so existing callers and tests keep working.
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from database import engine
from db_dialect import VIEW_NAMES

logger = logging.getLogger(__name__)

# Retained for backwards compatibility with existing .env files. No longer
# drives a job: the analytics views are plain views and never need refreshing.
MV_REFRESH_INTERVAL_MINUTES: int = int(
    os.getenv("MV_REFRESH_INTERVAL_MINUTES", "5")
)

MATERIALIZED_VIEWS = VIEW_NAMES


async def refresh_materialized_views() -> None:
    """No-op: the mv_* views are plain views and are always up to date.

    Kept as a stable entry point. It verifies the views are actually readable so
    that calling it still exercises something meaningful rather than silently
    doing nothing.
    """
    async with engine.connect() as conn:
        for view in VIEW_NAMES:
            await conn.execute(text(f"SELECT 1 FROM {view} LIMIT 1"))
    logger.debug("Analytics views are plain views - nothing to refresh.")

async def check_camera_status() -> None:
    """Mark cameras inactive if they haven't sent events in 2 minutes."""
    from sqlalchemy import update
    from models import Camera, CameraStatus
    from datetime import datetime, timezone, timedelta
    
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
    async with engine.begin() as conn:
        stmt = update(Camera).where(
            Camera.status == CameraStatus.active.value,
            (Camera.last_seen_at == None) | (Camera.last_seen_at < cutoff)
        ).values(status=CameraStatus.inactive.value)
        await conn.execute(stmt)

async def clean_old_logs() -> None:
    """Enforce a 2-month log retention policy for audit logs and login logs."""
    from sqlalchemy import delete
    from datetime import datetime, timezone, timedelta
    from models import AuditLog, LoginLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    logger.info("Cleaning up audit logs and login history older than 60 days (cutoff: %s)...", cutoff)
    
    try:
        async with engine.begin() as conn:
            # Delete old login logs
            res1 = await conn.execute(delete(LoginLog).where(LoginLog.timestamp < cutoff))
            # Delete old audit logs
            res2 = await conn.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff))
            logger.info("Log cleanup complete. Removed %d login logs and %d audit logs.", res1.rowcount, res2.rowcount)
    except Exception as e:
        logger.error("Failed to clean up old logs: %s", e)


def create_scheduler() -> AsyncIOScheduler:
    """Build and return a configured AsyncIOScheduler (not yet started)."""
    scheduler = AsyncIOScheduler()
    # No mv_refresh job: the analytics views are plain views and never go stale.
    scheduler.add_job(
        check_camera_status,
        trigger="interval",
        minutes=1,
        id="check_camera_status",
        replace_existing=True,
    )
    scheduler.add_job(
        clean_old_logs,
        trigger="interval",
        hours=24,
        id="clean_old_logs",
        replace_existing=True,
    )
    return scheduler

