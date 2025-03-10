#!/usr/bin/env python3
import json
import os
import pandas as pd
import gspread
import requests
import re
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")
OUTPUT_SHEET_NAME = "AggregatedSummary"
JSON_CREDENTIALS_FILE = os.getenv("JSON_CREDENTIALS_FILE")

# Directory to store JSON files
DATA_DIR = "interface/data"
os.makedirs(DATA_DIR, exist_ok=True)

# Directory to store champion icons
ICONS_DIR = "interface/images/champions"
os.makedirs(ICONS_DIR, exist_ok=True)

def get_sheet_data(worksheet_name):
    """
    Retrieves the data from the specified Google Sheet and worksheet.
    
    Returns:
        DataFrame of records
    """
    try:
        gc = gspread.service_account(filename=JSON_CREDENTIALS_FILE)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(worksheet_name)
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        return df
    except Exception as e:
        print(f"Error accessing Google Sheet: {e}")
        return pd.DataFrame()

def get_latest_version():
    """
    Get the latest version of Data Dragon.
    """
    try:
        response = requests.get("https://ddragon.leagueoflegends.com/api/versions.json")
        versions = response.json()
        return versions[0]  # Return the latest version
    except Exception as e:
        print(f"Error fetching Data Dragon version: {e}")
        return "13.24.1"  # Fallback to a recent version

def get_champion_data(version):
    """
    Get champion data from Data Dragon.
    """
    try:
        url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
        response = requests.get(url)
        return response.json()["data"]
    except Exception as e:
        print(f"Error fetching champion data: {e}")
        return {}

def normalize_champion_name(name):
    """
    Normalize champion name to match Data Dragon format.
    Removes spaces, punctuation, and converts to lowercase.
    """
    # Remove spaces, apostrophes, and convert to lowercase
    normalized = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
    return normalized

def create_champion_mapping(champion_data):
    """
    Create a mapping between normalized champion names and their Data Dragon IDs.
    """
    mapping = {}
    for champion_id, champion_info in champion_data.items():
        normalized_name = normalize_champion_name(champion_info["name"])
        mapping[normalized_name] = champion_id
    return mapping

def download_champion_icons(champion_data, version):
    """
    Download champion icons from Data Dragon.
    """
    champion_icons = {}
    champion_mapping = create_champion_mapping(champion_data)
    
    # First, download all champion icons
    for champion_id, champion_info in champion_data.items():
        icon_url = f"https://ddragon.leagueoflegends.com/cdn/{version}/img/champion/{champion_id}.png"
        icon_path = os.path.join(ICONS_DIR, f"{champion_id}.png")
        
        # Store the mapping of champion name to icon file
        champion_icons[champion_info["name"]] = f"{champion_id}.png"
        
        # Download the icon if it doesn't exist
        if not os.path.exists(icon_path):
            try:
                response = requests.get(icon_url)
                with open(icon_path, "wb") as f:
                    f.write(response.content)
                print(f"Downloaded icon for {champion_info['name']}")
            except Exception as e:
                print(f"Error downloading icon for {champion_info['name']}: {e}")
    
    # Save the champion name to icon mapping
    with open(os.path.join(DATA_DIR, "champion_icons.json"), "w") as f:
        json.dump(champion_icons, f)
    
    # Save the normalized name mapping for easier lookup
    with open(os.path.join(DATA_DIR, "champion_mapping.json"), "w") as f:
        json.dump(champion_mapping, f)
    
    return champion_icons, champion_mapping

def export_teams():
    """
    Export the list of teams to a JSON file.
    """
    df = get_sheet_data(WORKSHEET_NAME)
    
    if df.empty:
        print("No data found in the input worksheet.")
        return
    
    # Verify required columns
    if 'TeamName' not in df.columns:
        print("Missing expected column: TeamName")
        return
    
    # Get unique team names
    teams = df['TeamName'].unique().tolist()
    
    # Save to JSON
    with open(os.path.join(DATA_DIR, 'teams.json'), 'w') as f:
        json.dump(teams, f)
    
    print(f"Exported {len(teams)} teams to teams.json")

def export_players():
    """
    Export players grouped by team to a JSON file.
    """
    df = get_sheet_data(WORKSHEET_NAME)
    
    if df.empty:
        print("No data found in the input worksheet.")
        return
    
    # Verify required columns
    for col in ['TeamName', 'Name', 'AccountName']:
        if col not in df.columns:
            print(f"Missing expected column: {col}")
            return
    
    # Group players by team
    team_players = {}
    
    for team_name in df['TeamName'].unique():
        team_df = df[df['TeamName'] == team_name]
        
        # Group accounts by player name
        players = []
        for player_name in team_df['Name'].unique():
            player_accounts = team_df[team_df['Name'] == player_name]['AccountName'].tolist()
            players.append({
                'name': player_name,
                'accounts': player_accounts
            })
        
        team_players[team_name] = players
    
    # Save to JSON
    with open(os.path.join(DATA_DIR, 'players.json'), 'w') as f:
        json.dump(team_players, f)
    
    print(f"Exported players for {len(team_players)} teams to players.json")

def export_stats(champion_icons, champion_mapping):
    """
    Export champion stats to a JSON file.
    """
    df = get_sheet_data(OUTPUT_SHEET_NAME)
    
    if df.empty:
        print("No data found in the aggregated summary worksheet.")
        return
    
    # Group stats by team and player
    stats = {}
    
    for _, row in df.iterrows():
        team_name = row.get('TeamName', '')
        player_name = row.get('Name', '')
        
        if not team_name or not player_name:
            continue
        
        if team_name not in stats:
            stats[team_name] = {}
        
        if player_name not in stats[team_name]:
            stats[team_name][player_name] = []
        
        # Get champion name and try to find its icon
        champion_name = row.get('Champion', '')
        champion_icon = ''
        
        # Try direct lookup first
        if champion_name in champion_icons:
            champion_icon = champion_icons[champion_name]
        else:
            # Try normalized lookup
            normalized_name = normalize_champion_name(champion_name)
            if normalized_name in champion_mapping:
                champion_id = champion_mapping[normalized_name]
                champion_icon = f"{champion_id}.png"
                print(f"Matched '{champion_name}' to '{champion_id}' using normalized name")
            else:
                print(f"Could not find icon for champion: {champion_name}")
        
        # Format numeric values to preserve commas
        total_games = row.get('Total Games', '')
        win_rate = row.get('Win Rate', '')
        kda = row.get('KDA', '')
        cs = row.get('CS', '')
        damage = row.get('Damage', '')
        gold = row.get('Gold', '')
        wins = row.get('Wins', '')
        losses = row.get('Losses', '')
        
        # Extract champion stats
        champion_stats = {
            'Champion': champion_name,
            'ChampionIcon': champion_icon,
            'Total Games': str(total_games),
            'Win Rate': str(win_rate),
            'KDA': str(kda),
            'CS': str(cs),
            'Damage': str(damage),
            'Gold': str(gold),
            'Wins': str(wins),
            'Losses': str(losses)
        }
        
        stats[team_name][player_name].append(champion_stats)
    
    # Save to JSON
    with open(os.path.join(DATA_DIR, 'stats.json'), 'w') as f:
        json.dump(stats, f, indent=2)
    
    print(f"Exported stats for {len(stats)} teams to stats.json")

def export_all_data():
    """
    Export all data to JSON files.
    """
    print("Exporting data from Google Sheets to JSON files...")
    
    # Get champion data and icons
    version = get_latest_version()
    print(f"Using Data Dragon version: {version}")
    
    champion_data = get_champion_data(version)
    if champion_data:
        champion_icons, champion_mapping = download_champion_icons(champion_data, version)
        print(f"Downloaded icons for {len(champion_icons)} champions")
    else:
        champion_icons = {}
        champion_mapping = {}
    
    export_teams()
    export_players()
    export_stats(champion_icons, champion_mapping)
    print("Data export complete.")

if __name__ == "__main__":
    export_all_data() 