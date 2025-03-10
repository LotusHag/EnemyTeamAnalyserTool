#!/usr/bin/env python3
"""
Webscraper to fetch champions played for given accounts.
This script serves as a template. It scrapes the champions played this season and past seasons for a set of accounts.
Make sure to adjust the URL and parsing code to match the target website's structure.

Usage:
    pip install requests bs4
    python webscraper.py
"""

import requests
from bs4 import BeautifulSoup

# List of account identifiers to scrape
accounts = [
    'account1',
    'account2',
    'account3'
]

# Function to scrape champion data for a given account

def scrape_account(account):
    # Replace the URL below with the actual endpoint you need to scrape
    url = f"https://example.com/account/{account}/stats"
    print(f"Scraping data for account: {account}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching data for {account}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Initialize lists for current and past seasons
    champions_this_season = []
    champions_past_seasons = []
    
    # Example: look for a table with id 'champions'
    table = soup.find('table', id='champions')
    if not table:
        print(f"No champions table found for account {account}")
        return None

    rows = table.find_all('tr')
    if not rows or len(rows) < 2:
        print(f"No data rows found in the table for account {account}")
        return None

    # Assuming the first row is header, iterate over data rows
    for row in rows[1:]:
        cols = row.find_all('td')
        if len(cols) < 2:
            continue
        champion = cols[0].get_text(strip=True)
        season = cols[1].get_text(strip=True)
        
        # Based on season text, classify the champion into current or past seasons
        if season.lower() in ['current', 'this season']:
            champions_this_season.append(champion)
        else:
            champions_past_seasons.append(champion)

    return {
        "account": account,
        "current_season": champions_this_season,
        "past_seasons": champions_past_seasons
    }


def main():
    results = []
    for account in accounts:
        data = scrape_account(account)
        if data:
            results.append(data)
            print(f"Account: {data['account']}")
            print(f"  Current Season Champions: {data['current_season']}")
            print(f"  Past Season Champions: {data['past_seasons']}")
            print("-------------------------------------")

    # Optionally, save the results to a file
    # with open('results.json', 'w') as f:
    #     import json
    #     json.dump(results, f, indent=4)


if __name__ == '__main__':
    main()
