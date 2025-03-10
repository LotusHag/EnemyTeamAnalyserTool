from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time

def get_champion_stats(region, summoner_name, season='current'):
    """
    Scrape champion statistics for a given summoner from u.gg using Selenium
    
    Args:
        region (str): Player region (e.g., 'euw1', 'na1')
        summoner_name (str): Summoner name
        season (str): 'current' for current season, or season number (e.g., '24', '23')
    """
    # Now, all summoner names are treated the same.
    formatted_name = summoner_name.lower().replace('#', '-').replace(' ', '%20')
    base_url = f'https://u.gg/lol/profile/{region}/{formatted_name}/champion-stats'
    if season != 'current':
        url = f'{base_url}?season={season}'
    else:
        url = base_url
    
    print(f"Fetching URL: {url}")
    
    # Setup Chrome driver with additional options for stability
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # Run in headless mode
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(url)
        
        # Increase wait time for dynamic content to fully load
        wait = WebDriverWait(driver, 20)
        try:
            table = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "rt-tbody")))
        except Exception as e:
            print("Timeout or error waiting for the champion stats table to load.")
            return pd.DataFrame()  # Return an empty DataFrame if the table isn't found
        
        # Find all champion rows
        rows = table.find_elements(By.CLASS_NAME, "rt-tr-group")
        
        champions_data = []
        for row in rows:
            try:
                # Get champion name
                champion_name = row.find_element(By.CLASS_NAME, "champion-cell").text.strip()
                if not champion_name:  # Skip empty rows
                    continue
                
                # Get win rate info - look for both possible structures
                win_rate_cell = row.find_element(By.CLASS_NAME, "win-rate-cell")
                try:
                    win_rate = win_rate_cell.find_element(By.TAG_NAME, "strong").text
                    games = win_rate_cell.find_element(By.CLASS_NAME, "text-lavender-50").text
                except:
                    # Backup method: get all text and split
                    win_rate_text = win_rate_cell.text.split('\n')
                    win_rate = win_rate_text[0] if win_rate_text else '0%'
                    games = win_rate_text[1] if len(win_rate_text) > 1 else '0W 0L'
                
                # Get KDA - handle both possible formats
                kda_cell = row.find_element(By.CLASS_NAME, "kda-cell")
                try:
                    kda = kda_cell.find_element(By.TAG_NAME, "strong").text
                except:
                    kda = kda_cell.text.split('\n')[0] if kda_cell.text else '0'
                
                # Get CS per minute
                cs_cell = row.find_element(By.CLASS_NAME, "cs-cell")
                try:
                    cs = cs_cell.find_element(By.TAG_NAME, "strong").text
                except:
                    cs = cs_cell.text.split('\n')[0] if cs_cell.text else '0'
                
                # Get damage per minute
                damage_cell = row.find_element(By.CLASS_NAME, "damage-cell")
                try:
                    damage = damage_cell.find_element(By.TAG_NAME, "strong").text
                except:
                    damage = damage_cell.text.split('\n')[0] if damage_cell.text else '0'
                
                # Get gold per minute
                gold_cell = row.find_element(By.CLASS_NAME, "gold-cell")
                try:
                    gold = gold_cell.find_element(By.TAG_NAME, "strong").text
                except:
                    gold = gold_cell.text.split('\n')[0] if gold_cell.text else '0'
                
                # Clean the values (remove any non-numeric characters except decimal points)
                cs = ''.join(c for c in cs if c.isdigit() or c == '.')
                damage = ''.join(c for c in damage if c.isdigit() or c == '.')
                gold = ''.join(c for c in gold if c.isdigit() or c == '.')
                
                print(f"Found champion: {champion_name}, WR: {win_rate}, Games: {games}, KDA: {kda}, CS: {cs}, DMG: {damage}, Gold: {gold}")
                
                champions_data.append({
                    'Champion': champion_name,
                    'Win Rate': win_rate,
                    'Games': games,
                    'KDA': kda,
                    'CS': cs or '0',
                    'Damage': damage or '0',
                    'Gold': gold or '0',
                    'Season': season
                })
                
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
        
        return pd.DataFrame(champions_data)
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None
        
    finally:
        driver.quit()

def aggregate_champion_stats(all_data):
    """
    Aggregate champion statistics across all seasons
    
    Args:
        all_data (list): List of DataFrames containing champion stats from different seasons
    """
    if not all_data:
        return None
        
    # Combine all DataFrames
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # Process the Games column to extract W/L numbers
    combined_df[['Wins', 'Losses']] = combined_df['Games'].str.extract(r'(\d+)W (\d+)L')
    
    # Fill NaN values with 0 before converting to int
    combined_df['Wins'] = combined_df['Wins'].fillna(0).astype(int)
    combined_df['Losses'] = combined_df['Losses'].fillna(0).astype(int)
    
    # Group by Champion and calculate aggregated stats
    aggregated = combined_df.groupby('Champion').agg({
        'Wins': 'sum',
        'Losses': 'sum',
        'KDA': lambda x: round(sum(float(i) for i in x if str(i).replace('.', '').isdigit()) / len(x), 2),
        'CS': lambda x: round(sum(float(i) for i in x if str(i).replace('.', '').isdigit()) / len(x), 1),
        'Damage': lambda x: round(sum(float(i) for i in x if str(i).replace('.', '').isdigit()) / len(x), 0),
        'Gold': lambda x: round(sum(float(i) for i in x if str(i).replace('.', '').isdigit()) / len(x), 0),
    }).reset_index()
    
    # Calculate total games and win rate
    aggregated['Total Games'] = aggregated['Wins'] + aggregated['Losses']
    aggregated['Win Rate'] = round(
        aggregated['Wins'].div(aggregated['Total Games'].where(aggregated['Total Games'] != 0, 1)) * 100, 1
    )
    
    # Sort by total games played, then win rate
    aggregated = aggregated.sort_values(['Total Games', 'Win Rate'], ascending=[False, False])
    aggregated['Win Rate'] = aggregated['Win Rate'].astype(str) + '%'
    
    return aggregated[['Champion', 'Total Games', 'Win Rate', 'KDA', 'CS', 'Damage', 'Gold', 'Wins', 'Losses']]
