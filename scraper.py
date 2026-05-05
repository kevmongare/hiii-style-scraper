"""
hiii-style.com Newest Arrivals Scraper
---------------------------------------
Scrapes newest arrivals daily at 08:00 EAT (UTC+3)
and appends results to a Google Sheet.

Columns scraped:
    - Scraped At (EAT)
    - Product Name
    - Price (Ksh)
    - Original Price (Ksh)
    - Product URL
    - Image URL

Usage:
    python scraper.py              # Runs scheduler (keeps running, fires at 08:00 EAT)
    python scraper.py --run-once   # Scrapes immediately once and exits (used by GitHub Actions)

Requirements:
    pip install playwright schedule gspread google-auth pytz
    playwright install chromium
"""

import sys
import schedule
import time
import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCRAPE_URL      = "https://www.hiii-style.com/category?sort=newest-arrivals"
SERVICE_ACCOUNT = "service_account.json"   # Path to your Google SA JSON key
SPREADSHEET_ID  = "YOUR_SPREADSHEET_ID"   # From the Sheets URL
SHEET_NAME      = "Newest Arrivals"        # Tab name inside the spreadsheet
EAT             = pytz.timezone("Africa/Nairobi")
RUN_TIME        = "08:00"                  # Daily run time in EAT
# ──────────────────────────────────────────────────────────────────────────────


def get_sheet():
    """Authenticate and return the target worksheet."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=5000, cols=10)
        sheet.append_row(
            [
                "Scraped At (EAT)",
                "Product Name",
                "Price (Ksh)",
                "Original Price (Ksh)",
                "Product URL",
                "Image URL",
            ],
            value_input_option="USER_ENTERED",
        )
        print(f"[INFO] Created new sheet tab: '{SHEET_NAME}' with headers.")

    return sheet


def clean_price(text):
    """Strip currency symbols, commas, and whitespace from a price string."""
    return text.replace("Ksh", "").replace("KSh", "").replace(",", "").strip()


def resolve_url(href):
    """Turn a relative URL into an absolute one."""
    if href and not href.startswith("http"):
        return "https://www.hiii-style.com" + href
    return href or ""


def scrape_products():
    """Use a headless browser to scrape all products from the newest arrivals page."""
    products = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        page.goto(SCRAPE_URL, wait_until="networkidle", timeout=60_000)

        # Wait for at least one product card to appear
        try:
            page.wait_for_selector(
                ".product-card, .product-item, [class*='product']",
                timeout=20_000,
            )
        except Exception:
            print("[WARN] Product selector timeout — trying to parse whatever loaded.")

        # ── Try multiple common CSS patterns ──────────────────────────────────
        items = page.query_selector_all(
            ".product-card, .product-item, "
            "[class*='product-card'], [class*='ProductCard'], "
            "li.product, div.product"
        )

        if not items:
            items = page.query_selector_all("[class*='product']")

        print(f"[INFO] Found {len(items)} raw product elements.")

        for item in items:
            # ── Product Name ──────────────────────────────────────────────────
            name_el = item.query_selector(
                "h2, h3, h4, "
                "[class*='name'], [class*='title'], "
                "[class*='product-name'], [class*='product-title']"
            )
            name = name_el.inner_text().strip() if name_el else ""

            # ── Current Price ─────────────────────────────────────────────────
            price_el = item.query_selector(
                "[class*='price']:not([class*='original'])"
                ":not([class*='was']):not([class*='old'])"
            )
            price = clean_price(price_el.inner_text()) if price_el else ""

            # ── Original / Strikethrough Price ────────────────────────────────
            orig_el = item.query_selector(
                "[class*='original-price'], [class*='was-price'], "
                "[class*='old-price'], s, del, strike"
            )
            original_price = clean_price(orig_el.inner_text()) if orig_el else ""

            # ── Product URL ───────────────────────────────────────────────────
            link_el = item.query_selector("a[href]")
            product_url = resolve_url(
                link_el.get_attribute("href") if link_el else ""
            )

            # ── Image URL ─────────────────────────────────────────────────────
            # Try src first, then data-src (lazy-loaded), then srcset (responsive)
            img_el = item.query_selector("img")
            image_url = ""
            if img_el:
                image_url = (
                    img_el.get_attribute("src")
                    or img_el.get_attribute("data-src")
                    or img_el.get_attribute("data-lazy-src")
                    or ""
                )
                # Fallback: pick the largest candidate from srcset
                if not image_url or image_url.startswith("data:"):
                    srcset = img_el.get_attribute("srcset") or ""
                    if srcset:
                        candidates = [
                            s.strip().split(" ")[0]
                            for s in srcset.split(",")
                            if s.strip()
                        ]
                        image_url = candidates[-1] if candidates else ""

                image_url = resolve_url(image_url)

            if name:
                products.append({
                    "name": name,
                    "price": price,
                    "original_price": original_price,
                    "product_url": product_url,
                    "image_url": image_url,
                })

        browser.close()

    # De-duplicate by name + price
    seen = set()
    unique = []
    for prod in products:
        key = (prod["name"], prod["price"])
        if key not in seen:
            seen.add(key)
            unique.append(prod)

    print(f"[INFO] {len(unique)} unique products after de-duplication.")
    return unique


def run_job():
    """Main job: scrape -> write to Google Sheets."""
    now_eat = datetime.datetime.now(EAT).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_eat} EAT] Starting scrape job ...")

    try:
        products = scrape_products()
    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
        return

    if not products:
        print("[WARN] No products found — nothing written to Sheets.")
        return

    try:
        sheet = get_sheet()
        rows = [
            [
                now_eat,
                p["name"],
                p["price"],
                p["original_price"],
                p["product_url"],
                p["image_url"],
            ]
            for p in products
        ]
        sheet.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"[OK] Wrote {len(rows)} products to Google Sheets.")
    except Exception as e:
        print(f"[ERROR] Google Sheets write failed: {e}")


# ── SCHEDULER ─────────────────────────────────────────────────────────────────
def main():
    print(f"Scheduler started. Will run daily at {RUN_TIME} EAT.")
    print("Press Ctrl+C to stop.\n")

    eat_run = datetime.datetime.strptime(RUN_TIME, "%H:%M").replace(tzinfo=EAT)
    utc_run = eat_run.astimezone(pytz.utc).strftime("%H:%M")
    schedule.every().day.at(utc_run).do(run_job)

    print(f"[INFO] Job scheduled at {RUN_TIME} EAT = {utc_run} UTC")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    if "--run-once" in sys.argv:
        run_job()
    else:
        main()
