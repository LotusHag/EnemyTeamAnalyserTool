"""
Webscraper to fetch champions played for given accounts.
This script scrapes the champions played (current season) from the player's OP.GG champions page.

Usage:
    pip install requests bs4
    python webscraper.py

References:
    [OP.GG Champions Page](https://www.op.gg/summoners/euw/Oriented-EUW/champions)
"""

import requests
from bs4 import BeautifulSoup

# List of account identifiers in OP.GG URL format (e.g. "Oriented-EUW")
accounts = [
    "Oriented-EUW",
    # Add other accounts as needed
]

def scrape_account(account):
    """
    Scrapes champion data for a given account.

    Fetches the champions played for the current season from:
         https://www.op.gg/summoners/euw/{account}/champions
    """
    url = f"https://www.op.gg/summoners/euw/{account}/champions"
    print(f"Scraping data for account: {account}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching data for {account}: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Locate the champion table - adjust the selector if necessary.
    table = soup.find('table')
    if not table:
        print(f"No champion table found for account {account}")
        return []

    rows = table.find_all('tr')
    if not rows or len(rows) < 2:
        print(f"No data rows found in the champion table for account {account}")
        return []

    champions = []
    # Skip the header row (assumed as the first row)
    for row in rows[1:]:
        cols = row.find_all('td')
        # Ensure that there are at least five columns:
        if len(cols) < 5:
            continue

        try:
            rank = cols[0].get_text(strip=True)
            # Skip this row if rank isn't an integer
            if not rank.isdigit():
                continue
            champion_name = cols[1].get_text(strip=True)
            played = cols[2].get_text(strip=True)
            kda = cols[3].get_text(strip=True)
            op_score = cols[4].get_text(strip=True)
            laning = cols[5].get_text(strip=True)
            DMG = cols[6].get_text(strip=True)
            wards = cols[7].get_text(strip=True)
            CS = cols[8].get_text(strip=True)
            Gold = cols[9].get_text(strip=True)
        except Exception as e:
            print(f"Error parsing a row: {e}")
            continue

        champ_data = {
            "rank": rank,
            "champion": champion_name,
            "played": played,
            "kda": kda,
            "op_score": op_score,
            "laning": laning,
            "DMG": DMG,
            "wards": wards,
            "CS": CS,
            "Gold": Gold
        }
        champions.append(champ_data)
    return champions

def main():
    """
    Main processing: iterates over each account and fetches champion data for the current season.
    """
    results = {}
    for account in accounts:
        champ_list = scrape_account(account)
        results[account] = champ_list
        print(f"\nAccount: {account}")
        for champ in champ_list:
            print(champ)
        print("-------------------------------------")

if __name__ == '__main__':
    main()
