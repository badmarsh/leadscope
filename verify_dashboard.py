import asyncio
import sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://localhost:3000/")
        
        # Wait for load
        try:
            await page.wait_for_function("() => !document.body.innerText.includes('Loading…')", timeout=5000)
        except:
            pass
            
        # Login
        try:
            if await page.locator("input[placeholder='••••••••']").is_visible(timeout=3000):
                await page.fill("input[placeholder='••••••••']", "admin")
                async with page.expect_response(lambda r: '/api/login' in r.url and r.status == 200):
                    await page.click("button:has-text('Sign In')")
        except Exception as e:
            print(f"Login skip/fail: {e}")
            
        # Wait for campaigns to load
        await page.wait_for_timeout(2000)
            
        # Select WP campaign
        print("Switching to WP Remediation...")
        try:
            await page.wait_for_selector("text=WP Remediation", timeout=15000)
            await page.click("text=WP Remediation")
        except Exception as e:
            print("Could not find WP Remediation campaign tab:", e)
        
        print("Waiting for data to load...")
        await page.wait_for_timeout(3000)
        
        print("Taking screenshot...")
        # Save to artifacts directory
        await page.screenshot(path=r"C:\Users\marek\.gemini\antigravity\brain\c2b9f9a9-4626-4772-9e0c-1d594505548e\dashboard_verified.png")
        print("Screenshot saved!")
        
        await browser.close()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
