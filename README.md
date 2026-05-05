# hiii-style Newest Arrivals Scraper

Scrapes newest arrivals from [hiii-style.com](https://www.hiii-style.com/category?sort=newest-arrivals) daily at **08:00 EAT** and appends the results to a Google Sheet.

---

## Repo Structure

```
hiii-style-scraper/
├── scraper.py                  # Main scraper + scheduler
├── requirements.txt            # pip dependencies
├── .gitignore                  # Excludes service_account.json
└── .github/
    └── workflows/
        └── scrape.yml          # GitHub Actions cron job
```

---

## Google Sheet Output

| Scraped At (EAT) | Product Name | Price (Ksh) | Original Price (Ksh) | URL |
|-----------------|-------------|-------------|---------------------|-----|
| 2026-05-05 08:00:12 | Nike Air Max | 4500 | 6000 | https://... |

Each run **appends** rows — full history is preserved.

---

## Setup

### 1. Google Sheets API (one-time)

1. Go to [Google Cloud Console](https://console.cloud.google.com) → create a project
2. Enable **Google Sheets API** and **Google Drive API**
3. Go to **IAM & Admin → Service Accounts** → Create a service account
4. Under the service account → **Keys → Add Key → JSON** → save as `service_account.json`
5. Create a [Google Sheet](https://sheets.google.com), copy the **Spreadsheet ID** from the URL
6. Share the sheet with the service account email (Editor access)

### 2. Configure `scraper.py`

```python
SERVICE_ACCOUNT = "service_account.json"
SPREADSHEET_ID  = "YOUR_SPREADSHEET_ID"   # ← paste your Sheet ID here
SHEET_NAME      = "Newest Arrivals"
RUN_TIME        = "08:00"                  # EAT
```

### 3. Add GitHub Secret

In your repo → **Settings → Secrets and variables → Actions → New repository secret**:

- **Name:** `GOOGLE_SERVICE_ACCOUNT`
- **Value:** paste the entire contents of your `service_account.json`

---

## Running

### Via GitHub Actions (recommended — no server needed)
The workflow runs automatically at **05:00 UTC = 08:00 EAT** every day.
To trigger manually: **Actions → Daily Scrape → Run workflow**

### Locally (scheduler mode)
```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py
```

### Locally (single run)
```bash
python scraper.py --run-once
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No products found` | Site CSS may have changed — inspect a product card in DevTools and update selectors in `scrape_products()` |
| `403` on Sheets | Re-share the sheet with the service account email as Editor |
| Playwright not found | Run `playwright install chromium` |
