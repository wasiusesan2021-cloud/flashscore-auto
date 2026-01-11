import re
import pandas as pd
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

SEARCH_URL = "https://www.flashscore.com/search/?q="

def clean_team_name(raw: str) -> str:
    return raw.replace("(W)", "").strip()

def is_women_team(raw: str) -> bool:
    return "(W)" in raw

def safe_text(locator):
    try:
        return locator.inner_text().strip()
    except:
        return ""

def normalize_date(date_text: str) -> str:
    """
    Tries to normalize Flashscore date headers like:
    - "TODAY", "TOMORROW"
    - "12/01/2026" or "12.01.2026" etc
    If unknown, returns original text.
    """
    t = date_text.strip().lower()

    today = datetime.now(timezone.utc).date()
    if "today" in t:
        return today.isoformat()
    if "tomorrow" in t:
        return (today.replace(day=today.day) + pd.Timedelta(days=1)).date().isoformat()

    # common formats: 12.01.2026 or 12/01/2026 or 12-01-2026
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", date_text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        try:
            return datetime(int(y), int(mo), int(d)).date().isoformat()
        except:
            return date_text.strip()

    return date_text.strip()

def main():
    with open("teams.txt", "r", encoding="utf-8") as f:
        teams_raw = [line.strip() for line in f if line.strip()]

    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # A more realistic user agent
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        })

        for raw in teams_raw:
            gender = "Women" if is_women_team(raw) else "Men"
            team_name = clean_team_name(raw)

            # For women teams, searching with "women" helps reduce wrong matches
            query = team_name + (" women" if gender == "Women" else "")
            url = SEARCH_URL + query.replace(" ", "%20")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
            except:
                continue

            # Try to find any upcoming match rows (Flashscore often uses .event__match after JS render)
            # If the structure changes, we still won't crash; we’ll just skip.
            match_blocks = page.locator(".event__match")
            count = match_blocks.count()

            if count == 0:
                # No rows for this team, skip safely
                continue

            # We’ll capture up to the next 2 FUTURE fixtures for each team
            fixtures_found = 0

            # Date headers are often shown above blocks. We'll track the last seen date header.
            current_date = ""

            for i in range(count):
                block = match_blocks.nth(i)

                # Update date if there's a nearby header (best-effort)
                # Many pages have .event__header or similar; handle both.
                # If not found, it stays as last known.
                try:
                    header = block.locator("xpath=preceding::*[contains(@class,'event__header')][1]")
                    header_text = safe_text(header)
                    if header_text:
                        current_date = normalize_date(header_text)
                except:
                    pass

                time_text = safe_text(block.locator(".event__time"))
                if not time_text:
                    continue

                # Skip finished/played matches (usually not in HH:MM format)
                if ":" not in time_text:
                    continue

                home = safe_text(block.locator(".event__participant--home"))
                away = safe_text(block.locator(".event__participant--away"))
                if not home or not away:
                    continue

                # Decide opponent relative to team_name
                if team_name.lower() in home.lower():
                    opponent = away
                elif team_name.lower() in away.lower():
                    opponent = home
                else:
                    # If the match doesn't actually contain the team, ignore it
                    continue

                # If we still don't have a date, store a blank but keep the row
                rows.append({
                    "Team": team_name,
                    "Opponent": opponent,
                    "Date": current_date,
                    "Kickoff": time_text,
                    "Gender": gender
                })

                fixtures_found += 1
                if fixtures_found >= 2:
                    break

        browser.close()

    # Always write a CSV (even if empty) so workflow never crashes
    df = pd.DataFrame(rows, columns=["Team", "Opponent", "Date", "Kickoff", "Gender"])
    df.to_csv("fixtures_flashscore.csv", index=False)

    print(f"Saved fixtures_flashscore.csv with {len(df)} rows")

if __name__ == "__main__":
    main()
