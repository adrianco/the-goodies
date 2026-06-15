"""
FunkyGibbon - Scheduled Backup Manager

DEVELOPMENT CONTEXT:
Created to provide automated, scheduled backup functionality for the
FunkyGibbon server. Ensures regular backups are created automatically
and old backups are cleaned up according to retention policies.

FUNCTIONALITY:
- Schedules periodic backups using APScheduler
- Automatically creates backups at configured intervals
- Manages backup retention (removes old backups)
- Provides start/stop control for the scheduler
- Supports configuration via settings
- Thread-safe scheduler management

PURPOSE:
Automated backup protection for FunkyGibbon deployments. Removes the
need for manual backup creation and ensures data safety through
regular, automatic backups with retention management.

DESIGN DECISIONS:
- Uses APScheduler for reliable task scheduling
- Background thread executor for non-blocking operation
- Configurable schedule interval and retention policy
- Graceful start/stop for application lifecycle integration
- Automatic cleanup of old backups based on age and count

KNOWN LIMITATIONS:
- Only supports local backups (no cloud storage)
- Scheduler runs in-process (requires server to be running)
- No notification system for backup failures
- Fixed interval scheduling (no cron-style expressions)

REVISION HISTORY:
- 2026-04-07: Initial implementation with interval-based scheduling

DEPENDENCIES:
- apscheduler: Task scheduling framework
- .backup: BackupService for creating backups
- .config: Configuration settings

USAGE:
```python
# Create and start scheduler
scheduler = BackupScheduler()
scheduler.start()

# Later, when shutting down
scheduler.stop()
```
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .backup import BackupService
from .config import settings

logger = logging.getLogger(__name__)


class BackupScheduler:
    """
    Manages scheduled automatic backups for FunkyGibbon.

    Uses APScheduler to create backups at regular intervals and
    automatically clean up old backups based on retention policies.
    """

    def __init__(
        self,
        backup_service: Optional[BackupService] = None,
        enabled: Optional[bool] = None,
        interval_hours: Optional[int] = None,
        retention_days: Optional[int] = None,
        max_count: Optional[int] = None
    ):
        """
        Initialize the backup scheduler.

        Args:
            backup_service: BackupService instance (creates one if not provided)
            enabled: Whether scheduler is enabled (defaults to config)
            interval_hours: Hours between backups (defaults to config)
            retention_days: Days to keep backups (defaults to config)
            max_count: Maximum number of backups to keep (defaults to config)
        """
        self.backup_service = backup_service or BackupService()

        # Load configuration
        self.enabled = enabled if enabled is not None else settings.backup_schedule_enabled
        self.interval_hours = interval_hours or settings.backup_schedule_interval_hours
        self.retention_days = retention_days or settings.backup_retention_days
        self.max_count = max_count or settings.backup_max_count

        # Create scheduler
        self.scheduler = BackgroundScheduler()
        self._is_running = False

        logger.info(
            f"Backup scheduler initialized: enabled={self.enabled}, "
            f"interval={self.interval_hours}h, retention={self.retention_days}d, "
            f"max_count={self.max_count}"
        )

    def start(self) -> None:
        """
        Start the backup scheduler.

        Schedules periodic backups and cleanup tasks based on configuration.
        Does nothing if scheduler is disabled or already running.
        """
        if not self.enabled:
            logger.info("Backup scheduler is disabled in configuration")
            return

        if self._is_running:
            logger.warning("Backup scheduler is already running")
            return

        # Schedule backup job
        self.scheduler.add_job(
            func=self._run_backup,
            trigger=IntervalTrigger(hours=self.interval_hours),
            id="scheduled_backup",
            name="Scheduled Database Backup",
            replace_existing=True
        )

        # Schedule cleanup job (runs daily)
        self.scheduler.add_job(
            func=self._run_cleanup,
            trigger=IntervalTrigger(hours=24),
            id="backup_cleanup",
            name="Backup Retention Cleanup",
            replace_existing=True
        )

        self.scheduler.start()
        self._is_running = True

        logger.info(
            f"Backup scheduler started - backups every {self.interval_hours} hours"
        )

        # Run initial backup immediately
        self._run_backup()

    def stop(self) -> None:
        """
        Stop the backup scheduler.

        Gracefully shuts down the scheduler and waits for any
        in-progress jobs to complete.
        """
        if not self._is_running:
            logger.info("Backup scheduler is not running")
            return

        logger.info("Stopping backup scheduler...")
        self.scheduler.shutdown(wait=True)
        self._is_running = False
        logger.info("Backup scheduler stopped")

    def is_running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self._is_running

    def get_status(self) -> dict:
        """
        Get current scheduler status and configuration.

        Returns:
            Dictionary with scheduler status information
        """
        return {
            "enabled": self.enabled,
            "running": self._is_running,
            "interval_hours": self.interval_hours,
            "retention_days": self.retention_days,
            "max_count": self.max_count,
            "next_backup": self._get_next_run_time("scheduled_backup"),
            "next_cleanup": self._get_next_run_time("backup_cleanup")
        }

    def trigger_backup_now(self) -> str:
        """
        Manually trigger a backup immediately.

        Returns:
            Backup ID of the created backup

        Raises:
            RuntimeError: If backup creation fails
        """
        logger.info("Manual backup triggered")
        return self._run_backup()

    def _get_next_run_time(self, job_id: str) -> Optional[str]:
        """Get the next scheduled run time for a job."""
        if not self._is_running:
            return None

        job = self.scheduler.get_job(job_id)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def _run_backup(self) -> str:
        """
        Execute a backup operation.

        This is the main backup job that runs on schedule.
        Creates a backup with automatic description.

        Returns:
            Backup ID of the created backup
        """
        try:
            # Check if we're already in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, use current loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_backup_sync)
                    backup_id = future.result()
                return backup_id
            except RuntimeError:
                # No running loop, create a new one
                return self._run_backup_sync()

        except Exception as e:
            logger.error(f"Scheduled backup failed: {str(e)}", exc_info=True)
            raise

    def _run_backup_sync(self) -> str:
        """
        Execute backup in a new event loop.

        Helper method that always creates a new event loop for the backup.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        description = f"Scheduled backup - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        backup_id = loop.run_until_complete(
            self.backup_service.create_backup(description=description)
        )

        loop.close()

        logger.info(f"Scheduled backup created successfully: {backup_id}")
        return backup_id

    def _run_cleanup(self) -> dict:
        """
        Execute backup cleanup based on retention policies.

        Removes backups that are:
        1. Older than retention_days
        2. Beyond max_count (keeps most recent)

        Returns:
            Dictionary with cleanup statistics
        """
        try:
            # Check if we're already in an async context
            try:
                _ = asyncio.get_running_loop()
                # We're in an async context, use thread pool
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_cleanup_sync)
                    return future.result()
            except RuntimeError:
                # No running loop, create a new one
                return self._run_cleanup_sync()

        except Exception as e:
            logger.error(f"Backup cleanup failed: {str(e)}", exc_info=True)
            raise

    def _run_cleanup_sync(self) -> dict:
        """
        Execute cleanup in a new event loop.

        Helper method that always creates a new event loop for cleanup.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Get all backups
        backups = loop.run_until_complete(self.backup_service.list_backups())

        deleted_count = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)

        # Sort by creation date (newest first)
        backups_sorted = sorted(
            backups,
            key=lambda b: b.get("created_at", ""),
            reverse=True
        )

        for i, backup in enumerate(backups_sorted):
            backup_id = backup["backup_id"]
            should_delete = False
            reason = ""

            # Check age-based retention
            try:
                created_at = datetime.fromisoformat(backup["created_at"].replace('Z', '+00:00'))
                if created_at < cutoff_date:
                    should_delete = True
                    reason = f"older than {self.retention_days} days"
            except (ValueError, KeyError):
                pass

            # Check count-based retention
            if i >= self.max_count:
                should_delete = True
                reason = f"beyond max count ({self.max_count})"

            # Delete if needed
            if should_delete:
                try:
                    loop.run_until_complete(
                        self.backup_service.delete_backup(backup_id)
                    )
                    deleted_count += 1
                    logger.info(f"Deleted backup {backup_id} - {reason}")
                except Exception as e:
                    logger.error(f"Failed to delete backup {backup_id}: {str(e)}")

        loop.close()

        result = {
            "deleted_count": deleted_count,
            "remaining_count": len(backups) - deleted_count,
            "retention_days": self.retention_days,
            "max_count": self.max_count
        }

        logger.info(
            f"Backup cleanup completed: deleted {deleted_count}, "
            f"remaining {result['remaining_count']}"
        )

        return result


# Global scheduler instance (initialized in app lifespan)
_scheduler_instance: Optional[BackupScheduler] = None


def get_scheduler() -> BackupScheduler:
    """
    Get the global scheduler instance.

    Returns:
        Global BackupScheduler instance

    Raises:
        RuntimeError: If scheduler hasn't been initialized
    """
    if _scheduler_instance is None:
        raise RuntimeError("Backup scheduler not initialized")
    return _scheduler_instance


def init_scheduler() -> BackupScheduler:
    """
    Initialize the global scheduler instance.

    Should be called during application startup.

    Returns:
        Initialized BackupScheduler instance
    """
    global _scheduler_instance
    _scheduler_instance = BackupScheduler()
    return _scheduler_instance


def shutdown_scheduler() -> None:
    """
    Shutdown the global scheduler instance.

    Should be called during application shutdown.
    """
    global _scheduler_instance
    if _scheduler_instance is not None:
        _scheduler_instance.stop()
        _scheduler_instance = None
