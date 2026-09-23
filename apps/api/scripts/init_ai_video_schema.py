"""Create the Linglong Lab AI Video schema in the existing Incept database.

Run this idempotent command as part of the Incept Cloud Run migration Job after
deploying the unified API image. It deliberately uses the same environment and
Cloud SQL connection configuration as ``app.main``; it is not a second API
service or a separate database deployment.
"""

from __future__ import annotations

import asyncio

from app.ai_video.core.db import close_db, init_db


async def _main() -> None:
    """Create missing AI Video tables and release the database engine."""
    try:
        await init_db()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(_main())
