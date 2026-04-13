"""
Run this ONCE to log into Gemini.
Session saved permanently to ./user_data — never need to run again.
"""
import asyncio
import shutil
from playwright.async_api import async_playwright

BRAVE_PATH = (
    shutil.which("brave-browser") or
    shutil.which("chromium-browser") or
    shutil.which("chromium") or
    "/usr/bin/brave-browser"
)

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            "./user_data",
            executable_path=BRAVE_PATH,
            headless=False,
            args=["--no-sandbox"]
        )
        page = await context.new_page()
        await page.goto("https://gemini.google.com/app")
        print("=" * 50)
        print("👉 Log into your Google account in the browser")
        print("👉 Once you see the Gemini chat — press ENTER here")
        print("=" * 50)
        input("Press ENTER after logging in...")
        await context.close()
        print("✅ Session saved to ./user_data — never run this again!")

asyncio.run(main())
