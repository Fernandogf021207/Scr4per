from playwright.sync_api import sync_playwright
from getpass import getpass
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://instagram.com")
    input("Inicia sesión manualmente en X y presiona Enter...")
    context.storage_state(path="instagram_storage_state.json")
    browser.close()
