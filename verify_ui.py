import asyncio
from playwright.async_api import async_playwright

async def verify_ui():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Verify Streamlit
        try:
            await page.goto("http://localhost:8501")
            await page.wait_for_selector("h1")
            title = await page.inner_text("h1")
            print(f"Streamlit title: {title}")
            await page.screenshot(path="streamlit_screenshot.png")
        except Exception as e:
            print(f"Streamlit verification failed: {e}")

        # Verify Chainlit
        try:
            await page.goto("http://localhost:8000")
            # Chainlit might take a while to load
            await page.wait_for_timeout(5000)
            content = await page.content()
            print(f"Chainlit page content length: {len(content)}")
            await page.screenshot(path="chainlit_screenshot.png")
        except Exception as e:
            print(f"Chainlit verification failed: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_ui())
