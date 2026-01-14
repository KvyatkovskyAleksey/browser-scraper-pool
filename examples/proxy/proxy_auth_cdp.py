"""
Proxy Authentication via CDP (Advanced)

Many enterprise proxies require username/password authentication (HTTP 407).
Browser-scraper-pool supports this via Chrome DevTools Protocol (CDP).

This example shows how to:
1. Create context with authenticated proxy
2. Get CDP endpoint URL
3. Set up CDP to intercept auth challenges
4. Provide credentials automatically

Use Case:
Enterprise environments where proxies require authentication.

Note: This is an advanced example. For simple proxy auth, include credentials
in the proxy URL: http://username:password@proxy:8080

Usage:
    python proxy_auth_cdp.py
"""

import asyncio
import httpx


async def main():
    """Demonstrate proxy authentication handling"""

    print("🔐 Proxy Authentication via CDP")
    print("=" * 60)

    pool_url = "http://localhost:8000"

    # Step 1: Create context with proxy URL (with credentials)
    print("\n1️⃣ Creating context with authenticated proxy...")

    proxy_url = "http://username:password@proxy-server:8080"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{pool_url}/contexts",
            json={
                "proxy": proxy_url,
                "tags": ["authenticated-proxy"]
            }
        )

        if response.status_code == 200:
            context_data = response.json()
            print(f"   ✅ Context created: {context_data['id']}")
        else:
            print(f"   ❌ Failed to create context: {response.status_code}")
            return

    # Step 2: Get CDP endpoint
    print("\n2️⃣ Getting CDP endpoint...")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{pool_url}/pool/cdp")
        cdp_data = response.json()
        cdp_url = cdp_data.get("cdp_url")

        print(f"   CDP URL: {cdp_url}")

    # Step 3: In production, you would connect via CDP here
    # and set up auth interception
    print("\n3️⃣ CDP Auth Interception Setup")
    print("   ℹ️  In production, you would:")
    print("      1. Connect to CDP endpoint")
    print("      2. Enable Fetch domain")
    print("      3. Listen for authRequired events")
    print("      4. Respond with credentials")
    print("\n   Pseudo-code:")
    print("""
    from playwright.async_api import async_playwright

    async def setup_proxy_auth(cdp_url, username, password):
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(cdp_url)

        # Get the context
        context = browser.contexts[0]

        # Setup CDP session for Fetch domain
        cdp_session = await context.new_cdp_session(context.page)
        await cdp_session.send("Fetch.enable")

        # Handle auth challenges
        async def handle_auth(params):
            if "AuthRequired" in str(params):
                await cdp_session.send("Fetch.continueWithAuth", {
                    "requestId": params["requestId"],
                    "authChallengeResponse": {
                        "response": "ProvideCredentials",
                        "username": username,
                        "password": password
                    }
                })

        # In real implementation, set up event listener
        # cdp_session.on("Fetch.authRequired", handle_auth)
    """)

    # Step 4: Scrape with authenticated proxy
    print("\n4️⃣ Scraping with authenticated proxy...")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{pool_url}/scrape",
            json={
                "url": "https://example.com",
                "tags": ["authenticated-proxy"],
                "get_content": True
            }
        )

        if response.status_code == 200:
            result = response.json()
            if result["success"]:
                print(f"   ✅ Scrape successful!")
                print(f"   Status: {result['status']}")
                print(f"   Context: {result['context_id']}")
            else:
                print(f"   ❌ Scrape failed: {result.get('error')}")
        else:
            print(f"   ❌ Request failed: {response.status_code}")

    print("\n" + "=" * 60)
    print("✅ Example completed!")
    print("\n💡 Note: For simpler auth, include credentials in proxy URL:")
    print("   proxy = 'http://user:pass@host:port'")


if __name__ == "__main__":
    asyncio.run(main())
