"""Worker process entry point for processing scraping jobs.

Run with: python -m browser_scraper_pool.worker
"""

import asyncio
import contextlib
import logging
import signal
import sys

from browser_scraper_pool.config import settings
from browser_scraper_pool.pool.context_pool import ContextPool
from browser_scraper_pool.queue.consumer import JobConsumer

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Run the worker process."""
    logger.info("Starting worker...")

    # Get pool instance
    pool = ContextPool.get_instance()

    # Create consumer
    consumer = JobConsumer(pool)

    # Handle shutdown signals
    shutdown_event = asyncio.Event()

    def signal_handler(sig: int, _frame) -> None:
        logger.info("Received signal %s, shutting down...", signal.Signals(sig).name)
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        async with pool, consumer:
            logger.info("Worker ready, waiting for jobs...")

            # Run consumer until shutdown
            consume_task = asyncio.create_task(consumer.start_consuming())

            # Wait for shutdown signal
            await shutdown_event.wait()

            # Cancel consumer
            consume_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consume_task

    except Exception:
        logger.exception("Worker error")
        sys.exit(1)

    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
