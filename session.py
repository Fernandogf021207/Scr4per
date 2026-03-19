<<<<<<< Updated upstream
# save_storage_state.py
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.facebook.com/login")
        print("Inicia sesión manualmente en la ventana del navegador. Cuando termines, presiona Enter aquí.")
        input()
        await context.storage_state(path="data/storage/facebook_storage_state.json")
        await browser.close()
        print("Storage state guardado en data/storage/facebook_storage_state.json")

if __name__ == "__main__":
    asyncio.run(main())
=======
from playwright.sync_api import sync_playwright
from getpass import getpass
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.facebook.com")
    input("Inicia sesión manualmente en Facebook y presiona Enter...")
    context.storage_state(path="facebook_storage_state.json")
    browser.close()
>>>>>>> Stashed changes
