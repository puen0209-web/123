import asyncio
import logging
import os
import time
from pathlib import Path
from app.config import DB_PATH, RETENTION_DAYS
from app.database import get_db_connection

logger = logging.getLogger("cowrie_soc.cleaner")

class DiskAndDBCleaner:
    def __init__(self, retention_days: int = RETENTION_DAYS):
        self.retention_days = retention_days
        self.is_running = False
        self._task = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._clean_loop())
            logger.info(f"Disk and DB cleaner started (retention: {self.retention_days} days).")

    def stop(self):
        if self.is_running:
            self.is_running = False
            if self._task:
                self._task.cancel()
            logger.info("Disk and DB cleaner stopped.")

    async def _clean_loop(self):
        while self.is_running:
            try:
                await self.prune_database()
                self.prune_download_samples()
                # Run once every 12 hours
                await asyncio.sleep(12 * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleaner routine error: {e}")
                await asyncio.sleep(3600)

    async def prune_database(self):
        """Delete SQLite events older than retention_days and VACUUM."""
        try:
            db_file = Path(DB_PATH)
            if not db_file.exists():
                return

            logger.info(f"Pruning SQLite events older than {self.retention_days} days...")
            async with await get_db_connection() as db:
                # Delete old detailed event records
                await db.execute("""
                    DELETE FROM events 
                    WHERE timestamp < datetime('now', '-' || ? || ' days')
                """, (str(self.retention_days),))
                
                # Check row count limit (keep max 100,000 rows on 10GB disk)
                await db.execute("""
                    DELETE FROM events 
                    WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 100000)
                """)
                await db.commit()

                # VACUUM to reclaim actual disk space
                await db.execute("VACUUM")
                await db.commit()

            size_mb = db_file.stat().st_size / (1024 * 1024)
            logger.info(f"Database pruned successfully. Current size: {size_mb:.2f} MB")
        except Exception as e:
            logger.warning(f"Failed to prune database: {e}")

    def prune_download_samples(self):
        """Remove malware download samples older than 3 days to protect 10GB disk."""
        downloads_dir = Path("/app/downloads")
        if not downloads_dir.exists():
            return

        try:
            now = time.time()
            cutoff = now - (3 * 86400) # 3 days in seconds
            count = 0
            for item in downloads_dir.iterdir():
                if item.is_file() and item.stat().st_mtime < cutoff:
                    try:
                        item.unlink()
                        count += 1
                    except Exception:
                        pass
            if count > 0:
                logger.info(f"Cleaned {count} stale download sample(s) older than 3 days.")
        except Exception as e:
            logger.warning(f"Failed to prune downloads: {e}")

db_cleaner = DiskAndDBCleaner()
