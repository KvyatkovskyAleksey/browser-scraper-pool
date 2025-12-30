"""RabbitMQ publisher for job queue."""

import json
import logging
from typing import TYPE_CHECKING, ClassVar

from aio_pika import Message, connect_robust

from browser_scraper_pool.config import settings

if TYPE_CHECKING:
    from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

logger = logging.getLogger(__name__)

QUEUE_NAME = "scraper_jobs"


class JobPublisher:
    """Publishes scraping jobs to RabbitMQ.

    Singleton pattern - use get_instance() to get the shared instance.
    """

    _instance: ClassVar["JobPublisher | None"] = None

    def __init__(self, rabbitmq_url: str | None = None) -> None:
        """Initialize publisher.

        Args:
            rabbitmq_url: RabbitMQ connection URL. Defaults to settings.
        """
        self._rabbitmq_url = rabbitmq_url or settings.rabbitmq_url
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None

    @classmethod
    def get_instance(cls, rabbitmq_url: str | None = None) -> "JobPublisher":
        """Get or create singleton instance.

        Args:
            rabbitmq_url: RabbitMQ URL (only used if creating new instance).

        Returns:
            Shared JobPublisher instance.
        """
        if cls._instance is None:
            cls._instance = cls(rabbitmq_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None

    async def connect(self) -> None:
        """Connect to RabbitMQ and declare queue."""
        if self._connection and not self._connection.is_closed:
            return

        logger.info("Connecting to RabbitMQ: %s", self._rabbitmq_url)
        self._connection = await connect_robust(self._rabbitmq_url)
        self._channel = await self._connection.channel()
        self._queue = await self._channel.declare_queue(QUEUE_NAME, durable=True)
        logger.info("Connected to RabbitMQ, queue: %s", QUEUE_NAME)

    async def disconnect(self) -> None:
        """Close RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("Disconnected from RabbitMQ")
        self._connection = None
        self._channel = None
        self._queue = None

    async def publish(self, job_id: str) -> None:
        """Publish a job ID to the queue.

        The worker will fetch job details from storage using the ID.

        Args:
            job_id: Job identifier to publish.
        """
        if not self._channel:
            await self.connect()

        message = Message(
            body=json.dumps({"job_id": job_id}).encode(),
            content_type="application/json",
            delivery_mode=2,  # Persistent
        )

        await self._channel.default_exchange.publish(
            message,
            routing_key=QUEUE_NAME,
        )
        logger.debug("Published job %s to queue", job_id)

    @property
    def is_connected(self) -> bool:
        """Check if connected to RabbitMQ."""
        return self._connection is not None and not self._connection.is_closed

    async def __aenter__(self) -> "JobPublisher":
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.disconnect()
