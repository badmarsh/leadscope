from crawl4ai import AsyncWebCrawler, BrowserConfig
import asyncio

async def main():
    config = BrowserConfig(browser_ws_endpoint='ws://browserless:3000')
    async with AsyncWebCrawler(config=config) as crawler:
        result = await crawler.arun(url='https://example.com')
        print(result.success)

asyncio.run(main())
