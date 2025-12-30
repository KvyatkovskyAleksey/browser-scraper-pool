"""RabbitMQ consumer for processing scraping jobs."""

import base64
import json
import logging
from typing import TYPE_CHECKING

from aio_pika import connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractIncomingMessage,
    AbstractQueue,
)

from browser_scraper_pool.config import settings
from browser_scraper_pool.models.schemas import JobResult
from browser_scraper_pool.queue.job_storage import Job, job_storage
from browser_scraper_pool.queue.publisher import QUEUE_NAME

if TYPE_CHECKING:
    from browser_scraper_pool.pool.context_pool import ContextPool

logger = logging.getLogger(__name__)


class JobConsumer:
    """Consumes and processes scraping jobs from RabbitMQ."""

    def __init__(
        self,
        pool: "ContextPool",
        rabbitmq_url: str | None = None,
    ) -> None:
        """Initialize consumer.

        Args:
            pool: ContextPool instance for browser operations.
            rabbitmq_url: RabbitMQ connection URL. Defaults to settings.
        """
        self._pool = pool
        self._rabbitmq_url = rabbitmq_url or settings.rabbitmq_url
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._running = False

    async def connect(self) -> None:
        """Connect to RabbitMQ and declare queue."""
        if self._connection and not self._connection.is_closed:
            return

        logger.info("Consumer connecting to RabbitMQ: %s", self._rabbitmq_url)
        self._connection = await connect_robust(self._rabbitmq_url)
        self._channel = await self._connection.channel()

        # Fair dispatch - one message at a time per worker
        await self._channel.set_qos(prefetch_count=1)

        self._queue = await self._channel.declare_queue(QUEUE_NAME, durable=True)
        logger.info("Consumer connected, queue: %s", QUEUE_NAME)

    async def disconnect(self) -> None:
        """Close RabbitMQ connection."""
        self._running = False
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("Consumer disconnected from RabbitMQ")
        self._connection = None
        self._channel = None
        self._queue = None

    async def start_consuming(self) -> None:
        """Start consuming messages from the queue.

        This method runs indefinitely until disconnect() is called.
        """
        if not self._queue:
            await self.connect()

        self._running = True
        logger.info("Starting to consume jobs...")

        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                await self._process_message(message)

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        """Process a single message from the queue.

        Args:
            message: RabbitMQ message containing job ID.
        """
        async with message.process():
            try:
                data = json.loads(message.body.decode())
                job_id = data.get("job_id")

                if not job_id:
                    logger.warning("Message missing job_id: %s", data)
                    return

                logger.info("Processing job: %s", job_id)
                await self._process_job(job_id)

            except json.JSONDecodeError:
                logger.warning("Invalid JSON in message: %s", message.body)
            except Exception:
                logger.exception("Error processing message")

    async def _process_job(self, job_id: str) -> None:
        """Execute a scraping job.

        Args:
            job_id: Job identifier.
        """
        job = job_storage.get(job_id)
        if not job:
            logger.warning("Job not found in storage: %s", job_id)
            return

        # Mark as processing
        job_storage.update_status(job_id, "processing")

        ctx = None
        try:
            # Create temporary context for this job
            ctx = await self._pool.create_context(proxy=job.request.proxy)
            await self._pool.acquire_context(ctx.id)

            result = await self._execute_job(job, ctx)

            job_storage.update_status(job_id, "completed", result)
            logger.info("Job completed: %s", job_id)

        except Exception as e:
            logger.exception("Job failed: %s", job_id)
            error_result = JobResult(
                url=str(job.request.url),
                status=None,
                error=str(e),
            )
            job_storage.update_status(job_id, "failed", error_result)

        finally:
            # Clean up context
            if ctx:
                try:
                    await self._pool.release_context(ctx.id)
                    await self._pool.remove_context(ctx.id)
                except Exception:
                    logger.debug("Error cleaning up context %s", ctx.id, exc_info=True)

    async def _execute_job(
        self,
        job: Job,
        ctx,
    ) -> JobResult:
        """Execute job operations and return result.

        Args:
            job: Job to execute.
            ctx: Acquired ContextInstance.

        Returns:
            JobResult with collected data.
        """
        req = job.request
        page = ctx.page

        # Navigate
        response = await page.goto(
            str(req.url),
            timeout=req.timeout,
            wait_until=req.wait_until,
        )

        result_url = page.url
        result_status = response.status if response else None
        result_content: str | None = None
        result_script: str | int | float | bool | dict | list | None = None
        result_screenshot: str | None = None

        # Get content if requested
        if req.get_content:
            result_content = await page.content()

        # Execute script if provided
        if req.script:
            result_script = await page.evaluate(req.script)

        # Take screenshot if requested
        if req.screenshot:
            screenshot_bytes = await page.screenshot(full_page=req.screenshot_full_page)
            result_screenshot = base64.b64encode(screenshot_bytes).decode("utf-8")

        return JobResult(
            url=result_url,
            status=result_status,
            content=result_content,
            script_result=result_script,
            screenshot=result_screenshot,
        )

    @property
    def is_running(self) -> bool:
        """Check if consumer is running."""
        return self._running

    async def __aenter__(self) -> "JobConsumer":
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.disconnect()
