"""
Simple Web Scraping Example

This is the minimal example to scrape a URL using browser-scraper-pool.
No proxy, no special features - just get the page content.

Usage:
    python simple_scrape.py
"""

import asyncio
import httpx


async def main():
    """Scrape a single URL with minimal configuration"""

    pool_url = "http://localhost:8000"
    target_url = "https://example.com"

    async with httpx.AsyncClient() as client:
        # Make scrape request
        response = await client.post(
            f"{pool_url}/scrape",
            json={
                "url": target_url,
                "get_content": True,  # Return HTML content
                "wait_for": "networkidle"  # Wait for network to be idle
            }
        )

        # Check if request succeeded
        response.raise_for_status()
        result = response.json()

        # Display results
        if result["success"]:
            print(f"✅ Successfully scraped: {result['url']}")
            print(f"   Status: {result['status']}")
            print(f"   Content length: {len(result['content'])} bytes")
            print(f"   Context used: {result['context_id']}")
            print(f"   Queue wait: {result['queue_wait_ms']}ms")

            # Print first 200 characters of content
            print(f"\n   Content preview:")
            print(f"   {result['content'][:200]}...")
        else:
            print(f"❌ Scrape failed: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    print("🚀 Starting simple scrape example...\n")
    asyncio.run(main())
