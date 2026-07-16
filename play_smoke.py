from playwright.sync_api import sync_playwright
with sync_playwright() as p:
      browser = p.chromium.launch(headless=True)
      page = browser.new_page()
      resp = page.goto("https://example.com", wait_until="networkidle", timeout=20000)
      print("status:", resp.status if resp else None, "len:", len(page.content()))
      browser.close()
