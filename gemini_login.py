import asyncio
import shutil
from playwright.async_api import async_playwright

BRAVE_PATH = (
    shutil.which("brave-browser") or
    shutil.which("chromium-browser") or
    "/usr/bin/brave-browser"
)

async def main():
    async with async_playwright() as p:
        # Use persistent context WITHOUT automation flags
        context = await p.chromium.launch_persistent_context(
            "./user_data",
            executable_path=BRAVE_PATH,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
            # Spoof a real browser
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation"],
        )
        page = await context.new_page()

        # Remove webdriver property
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        print("🌐 Opening Gemini...")
        await page.goto("https://gemini.google.com/app", timeout=60000)

        print("=" * 50)
        print("👉 Log into your Google account in the browser")
        print("👉 Once you see the Gemini chat — press ENTER here")
        print("=" * 50)
        input("Press ENTER after logging in...")

        await context.close()
        print("✅ Session saved — never run this again!")

asyncio.run(main())
