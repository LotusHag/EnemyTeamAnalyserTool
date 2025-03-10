#!/usr/bin/env python3
import time
import pandas as pd
import gspread
from webscraper import get_champion_stats, aggregate_champion_stats
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Load environment variables from .env
load_dotenv()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")
# Override the output sheet name to always "AggregatedSummary"
OUTPUT_SHEET_NAME = "AggregatedSummary"
JSON_CREDENTIALS_FILE = os.getenv("JSON_CREDENTIALS_FILE")

# -----------------------------
# Rate Limiter Implementation
# -----------------------------
class RateLimiter:
    """
    A simple rate limiter that allows a maximum number of actions per time period.
    """
    def __init__(self, rate, per):
        self.rate = rate      # actions allowed
        self.per = per        # time period in seconds
        self.allowance = rate
        self.last_check = time.time()
        self.lock = threading.Lock()
        
    def acquire(self):
        with self.lock:
            current = time.time()
            time_passed = current - self.last_check
            self.last_check = current
            self.allowance += time_passed * (self.rate / self.per)
            if self.allowance > self.rate:
                self.allowance = self.rate
            if self.allowance < 1.0:
                wait_time = (1.0 - self.allowance) * (self.per / self.rate)
                time.sleep(wait_time)
                self.allowance = 0.0
            else:
                self.allowance -= 1.0

# Global rate limiter instance: maximum 3 actions per 1 second.
rate_limiter = RateLimiter(rate=3, per=1)

def fetch_stats(region, account, season):
    """
    A helper function to rate-limit and fetch champion stats.
    """
    rate_limiter.acquire()  # Ensure we don't exceed 3 page requests per second
    return get_champion_stats(region, account, season)

# -----------------------------
# Google Sheets I/O Functions
# -----------------------------
def get_sheet_data():
    """
    Retrieves the data from the specified Google Sheet and worksheet.
    
    Returns:
        tuple: (DataFrame of records, gspread client, sheet object)
    """
    try:
        gc = gspread.service_account(filename=JSON_CREDENTIALS_FILE)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sheet.worksheet(WORKSHEET_NAME)
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        return df, gc, sheet
    except Exception as e:
        print(f"Error accessing Google Sheet: {e}")
        return pd.DataFrame(), None, None

def create_output_worksheet(sheet, output_sheet_title, header, default_rows="100", default_cols="20"):
    """
    Creates a new output worksheet (deleting any existing one with the same title) and writes the header.
    
    Args:
        sheet: gspread sheet object.
        output_sheet_title (str): Title of the output worksheet.
        header (list): List of header labels.
        
    Returns:
        A gspread worksheet object or None if creation failed.
    """
    try:
        try:
            existing_ws = sheet.worksheet(output_sheet_title)
            sheet.del_worksheet(existing_ws)
        except Exception:
            pass
        new_ws = sheet.add_worksheet(title=output_sheet_title, rows=default_rows, cols=default_cols)
        new_ws.update("A1", [header])
        return new_ws
    except Exception as e:
        print(f"Error creating output worksheet: {e}")
        return None

def get_or_create_output_worksheet(sheet, output_sheet_title, header, default_rows="100", default_cols="20"):
    """
    Retrieves the output worksheet if it exists, otherwise creates a new one.
    If the worksheet exists but the header does not match, update the header.
    """
    try:
        ws = sheet.worksheet(output_sheet_title)
        current_header = ws.row_values(1)
        if current_header != header:
            ws.update("A1", [header])
        return ws
    except Exception:
        # Worksheet doesn't exist, so create a new one.
        ws = sheet.add_worksheet(title=output_sheet_title, rows=default_rows, cols=default_cols)
        ws.update("A1", [header])
        return ws

# -----------------------------
# Main Aggregation Function
# -----------------------------
def build_player_summaries(team_filter, region='euw1', seasons=['current', '24', '23', '22', '21', '20']):
    """
    Processes players from the input Google Sheet, filtering by a specific team.
    
    For each player in the specified team, scrape each of their accounts over the specified
    seasons and generate an aggregated champion stats summary. Before processing, if the player's
    aggregated summary already exists in the output worksheet, their rows are removed. The new data
    is then appended at the bottom, preserving the rows of players from other teams.
    
    Output Format:
        TeamName, Name, AccountName, Champion, Total Games, Win Rate, KDA, CS, Damage, Gold, Wins, Losses
    """
    df, gc, sheet = get_sheet_data()
    
    if df.empty or gc is None or sheet is None:
        print("No data found or connection failure.")
        return
    
    # Verify required columns
    for col in ['TeamName', 'Name', 'AccountName']:
        if col not in df.columns:
            print(f"Missing expected column: {col}")
            return
    
    # Filter the dataframe to only include players from the specified team.
    df = df[df['TeamName'].str.strip() == team_filter]
    if df.empty:
        print(f"No players found for team '{team_filter}'.")
        return
    
    players = df.groupby('Name').agg({
        'TeamName': 'first',
        'AccountName': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    header = ['TeamName', 'Name', 'AccountName', 'Champion', 'Total Games', 'Win Rate', 'KDA', 'CS', 'Damage', 'Gold', 'Wins', 'Losses']
    # Use the existing output worksheet if it exists, otherwise create one.
    out_ws = get_or_create_output_worksheet(sheet, OUTPUT_SHEET_NAME, header)
    if out_ws is None:
        print("Failed to access or create the output worksheet.")
        return

    # Remove existing rows for players of the specified team from the output sheet.
    all_values = out_ws.get_all_values()
    if all_values:
        # Keep the header and only those rows whose team is NOT the one we are updating.
        new_values = [all_values[0]] + [row for row in all_values[1:] if row[0].strip() != team_filter]
        out_ws.clear()
        out_ws.update("A1", new_values)
    
    # Process each player individually.
    for idx, row in players.iterrows():
        player_name = row['Name']
        team_name = row['TeamName']
        accounts_str = row['AccountName']
        account_names = [acc.strip() for acc in accounts_str.split(',')]
        all_account_data = []
        
        for account in account_names:
            print(f"Processing account '{account}' for player '{player_name}'...")
            # Process each account sequentially (only one at a time).
            with ThreadPoolExecutor(max_workers=1) as account_executor:
                futures = []
                for season in seasons:
                    future = account_executor.submit(fetch_stats, region, account, season)
                    futures.append(future)
                for future in as_completed(futures):
                    try:
                        df_stats = future.result()
                        if df_stats is not None and not df_stats.empty:
                            all_account_data.append(df_stats)
                    except Exception as e:
                        print(f"Error fetching data for player '{player_name}', account '{account}': {e}")
            print("Waiting 10 seconds before processing the next account...")
            time.sleep(10)
        
        if all_account_data:
            try:
                aggregated_summary = aggregate_champion_stats(all_account_data)
                if aggregated_summary is not None and not aggregated_summary.empty:
                    player_rows = []
                    for _, champ_row in aggregated_summary.iterrows():
                        player_rows.append([
                            team_name,
                            player_name,
                            accounts_str,
                            champ_row.get('Champion', ''),
                            champ_row.get('Total Games', ''),
                            champ_row.get('Win Rate', ''),
                            champ_row.get('KDA', ''),
                            champ_row.get('CS', ''),
                            champ_row.get('Damage', ''),
                            champ_row.get('Gold', ''),
                            champ_row.get('Wins', ''),
                            champ_row.get('Losses', '')
                        ])
                    out_ws.append_rows(player_rows, value_input_option="USER_ENTERED")
                else:
                    print(f"Aggregation for player '{player_name}' returned no data.")
            except Exception as e:
                print(f"Error aggregating data for player '{player_name}': {e}")
        else:
            print(f"No data collected for player '{player_name}'.")
        
        time.sleep(5)
    
    print("All specified team player data processed and written to the output sheet.")

if __name__ == "__main__":
    time.sleep(300)
    # Example usage: process players only for team "Dorans Independent Gamers"
    team_to_process = "Dorans Independent Gamers"
    build_player_summaries(team_to_process)
    team_to_process = "Zephyr Theseus"
    build_player_summaries(team_to_process)
    team_to_process = "Dorans Maggi"
    build_player_summaries(team_to_process)