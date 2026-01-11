import requests
import pandas as pd
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

SEARCH_URL = "https://www.flashscore.com/search/?q="

teams = []
with open("teams.txt", "r") as f:
    teams = [t.strip() for t in f if t.strip()]

rows = []

for team in teams:
    gender = "Women" if "(W)" in team else "Men"
    team_name = team.replace("(W)", "").strip()

    url = SEARCH_URL + team_name.replace(" ", "%20")
    r = requests.get(url, headers=HEADERS, timeout=20)

    if r.status_code != 200:
        continue

    soup = BeautifulSoup(r.text, "html.parser")
    events = soup.select(".event__match")

    for e in events:
        try:
            time_el = e.select_one(".event__time")
            if not time_el:
                continue

            time_text = time_el.text.strip()

            # Skip finished matches
            if ":" not in time_text:
                continue

            home = e.select_one(".event__participant--home").text.strip()
            away = e.select_one(".event__participant--away").text.strip()

            opponent = away if team_name.lower() in home.lower() else home

            rows.append({
                "Team": team_name,
                "Opponent": opponent,
                "Kickoff": time_text,
                "Gender": gender
            })

        except:
            continue

df = pd.DataFrame(rows)

# Keep only next 2 matches per team
df = df.groupby(["Team", "Gender"]).head(2)

df.to_csv("fixtures_flashscore.csv", index=False)

print("Saved fixtures_flashscore.csv")
