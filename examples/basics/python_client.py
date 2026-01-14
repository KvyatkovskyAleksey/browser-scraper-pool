"""
Python Client with Context Manager

Complete Python client example showing:
- Async context manager for automatic cleanup
- Smart context selection with tags
- Proxy integration
- Error handling
- Response parsing

Usage:
    python python_client.py
"""

import asyncio
import httpx
from typing import Optional


class BrowserPoolClient:
    """
    Clean client abstraction for browser-scraper-pool

    Handles connection management and provides a simple interface
    for scraping URLs with various options.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Initialize HTTP client when entering context manager"""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0
        )
        return self

    async def __aexit__(self, *args):
        """Close HTTP client when exiting context manager"""
        if self.client:
            await self.client.aclose()

    async def scrape(
        self,
        url: str,
        tags: Optional[list[str]] = None,
        proxy: Optional[str] = None,
        wait_for: Optional[str] = None,
        screenshot: bool = False,
        script: Optional[str] = None
    ) -> dict:
        """
        Scrape a URL using the pool

        Args:
            url: Target URL to scrape
            tags: Optional tags for context selection (e.g., ["premium", "residential"])
            proxy: Optional proxy URL (e.g., "http://user:pass@proxy:8080")
            wait_for: Optional wait condition ("networkidle", "domcontentloaded", etc.)
            screenshot: Whether to take a screenshot (base64 encoded)
            script: Optional JavaScript to execute after page load

        Returns:
            Dictionary with scrape results including:
            - success (bool): Whether the scrape succeeded
            - url (str): The URL that was scraped
            - status (int): HTTP status code
            - content (str): HTML content if get_content=True
            - script_result (str): Result of script execution if provided
            - context_id (str): ID of the context used
            - queue_wait_ms (int): Time waited in queue
            - error (str): Error message if failed
        """
        payload = {
            "url": url,
            "get_content": True,
        }

        # Add optional parameters
        if tags:
            payload["tags"] = tags
        if proxy:
            payload["proxy"] = proxy
        if wait_for:
            payload["wait_for"] = wait_for
        if screenshot:
            payload["screenshot"] = True
        if script:
            payload["script"] = script

        # Make request
        response = await self.client.post("/scrape", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_pool_status(self) -> dict:
        """Get current pool status"""
        response = await self.client.get("/pool/status")
        response.raise_for_status()
        return response.json()


async def example_basic_scrape():
    """Example 1: Simple scrape with tags"""
    print("\n📄 Example 1: Basic scrape with tags")

    async with BrowserPoolClient() as pool:
        result = await pool.scrape(
            url="https://example.com",
            tags=["basic"],
            wait_for="networkidle"
        )

        if result["success"]:
            print(f"   ✅ Success: {result['url']}")
            print(f"   Status: {result['status']}")
            print(f"   Content: {len(result['content'])} bytes")
            print(f"   Context: {result['context_id']}")
        else:
            print(f"   ❌ Failed: {result.get('error')}")


async def example_scrape_with_script():
    """Example 2: Scrape with JavaScript execution"""
    print("\n📜 Example 2: Scrape with JavaScript execution")

    async with BrowserPoolClient() as pool:
        result = await pool.scrape(
            url="https://example.com",
            script="document.title",
            get_content=False
        )

        if result["success"]:
            print(f"   ✅ Script result: {result.get('script_result')}")
        else:
            print(f"   ❌ Failed: {result.get('error')}")


async def example_pool_status():
    """Example 3: Check pool status"""
    print("\n📊 Example 3: Pool status")

    async with BrowserPoolClient() as pool:
        status = await pool.get_pool_status()

        print(f"   Pool size: {status['size']}")
        print(f"   Available: {status['available']}")
        print(f"   Busy: {status['busy']}")
        print(f"   CDP port: {status['cdp_port']}")


async def main():
    """Run all examples"""
    print("🚀 Browser Pool Client Examples")
    print("=" * 50)

    await example_basic_scrape()
    await example_scrape_with_script()
    await example_pool_status()

    print("\n" + "=" * 50)
    print("✅ All examples completed!")


if __name__ == "__main__":
    asyncio.run(main())
