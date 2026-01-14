"""
Proxy Rotation Strategy with Tags

This example demonstrates how to use tag-based proxy rotation:

1. Create contexts with different proxy providers
2. Tag them by proxy type (residential, datacenter, premium)
3. Scrape URLs selecting appropriate proxy tier
4. Pool automatically load-balances within tag

Use Cases:
- Residential proxies for sensitive targets (expensive but reliable)
- Datacenter proxies for fast targets (fast but detectable)
- Premium proxies for logged-in sessions (protected from eviction)

Usage:
    python proxy_rotation.py
"""

import asyncio
import httpx


class ProxyRotator:
    """Manage proxy contexts with tags"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(base_url=self.base_url)
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def create_context(self, proxy: str, tags: list[str], persistent: bool = False):
        """Create a new context with proxy and tags"""
        response = await self.client.post(
            "/contexts",
            json={
                "proxy": proxy,
                "tags": tags,
                "persistent": persistent
            }
        )
        response.raise_for_status()
        return response.json()

    async def scrape(self, url: str, tags: list[str] = None, **kwargs):
        """Scrape URL with specified tag"""
        payload = {"url": url, "get_content": True, "tags": tags}
        payload.update(kwargs)

        response = await self.client.post("/scrape", json=payload)
        response.raise_for_status()
        return response.json()

    async def list_contexts(self, tags: list[str] = None):
        """List contexts, optionally filtered by tags"""
        params = {"tags": ",".join(tags)} if tags else None
        response = await self.client.get("/contexts", params=params)
        response.raise_for_status()
        return response.json()


async def setup_proxy_strategy(rotator: ProxyRotator):
    """
    Set up contexts with different proxy tiers

    In production, you'd have real proxy URLs here.
    For this example, we use placeholder URLs.
    """

    print("\n🔧 Setting up proxy contexts...")

    # Residential proxies (expensive but reliable, hard to detect)
    # Use for: sensitive targets, anti-bot protection
    await rotator.create_context(
        proxy="http://residential-proxy1:8080",
        tags=["residential", "high-trust"]
    )
    await rotator.create_context(
        proxy="http://residential-proxy2:8080",
        tags=["residential", "high-trust"]
    )
    print("   ✅ Created 2 residential proxy contexts")

    # Datacenter proxies (fast but detectable)
    # Use for: public APIs, data-heavy scraping
    await rotator.create_context(
        proxy="http://dc-proxy1:8080",
        tags=["datacenter", "fast"]
    )
    await rotator.create_context(
        proxy="http://dc-proxy2:8080",
        tags=["datacenter", "fast"]
    )
    print("   ✅ Created 2 datacenter proxy contexts")

    # Protected context (never evicted, for logins)
    # Use for: sessions with authentication, persistent cookies
    await rotator.create_context(
        proxy="http://premium-proxy:8080",
        tags=["protected", "logged-in"],
        persistent=True
    )
    print("   ✅ Created 1 protected context (persistent)")


async def scrape_with_strategy(rotator: ProxyRotator):
    """
    Scrape URLs using appropriate proxy tier based on target sensitivity
    """

    print("\n🎯 Scraping with proxy strategy...")

    # Sensitive target - use residential proxies
    # Pool will automatically load-balance between the 2 residential contexts
    print("\n1️⃣ Sensitive target → Residential proxies")
    result = await rotator.scrape(
        url="https://sensitive-site.com",
        tags=["residential"]
    )
    print(f"   Context used: {result.get('context_id')}")

    # Fast target - use datacenter proxies
    # Pool will load-balance between the 2 datacenter contexts
    print("\n2️⃣ Fast target → Datacenter proxies")
    result = await rotator.scrape(
        url="https://public-api.com/data",
        tags=["datacenter"]
    )
    print(f"   Context used: {result.get('context_id')}")

    # Logged-in scrape - use protected context
    # This context won't be evicted, preserving login session
    print("\n3️⃣ Logged-in target → Protected context")
    result = await rotator.scrape(
        url="https://dashboard.com/profile",
        tags=["logged-in"]
    )
    print(f"   Context used: {result.get('context_id')}")


async def inspect_contexts(rotator: ProxyRotator):
    """Inspect contexts by tag"""

    print("\n🔍 Inspecting contexts by tag...")

    # List all residential contexts
    residential = await rotator.list_contexts(tags=["residential"])
    print(f"\n   Residential contexts: {len(residential)}")
    for ctx in residential:
        print(f"      - {ctx['id']}: {ctx['tags']}")

    # List all datacenter contexts
    datacenter = await rotator.list_contexts(tags=["datacenter"])
    print(f"\n   Datacenter contexts: {len(datacenter)}")
    for ctx in datacenter:
        print(f"      - {ctx['id']}: {ctx['tags']}")


async def main():
    """Main execution"""

    print("🚀 Proxy Rotation Strategy Example")
    print("=" * 60)

    async with ProxyRotator() as rotator:
        # Set up contexts with different proxy tiers
        await setup_proxy_strategy(rotator)

        # Inspect what we created
        await inspect_contexts(rotator)

        # Demonstrate scraping with different strategies
        await scrape_with_strategy(rotator)

    print("\n" + "=" * 60)
    print("✅ Proxy rotation example completed!")


if __name__ == "__main__":
    asyncio.run(main())
