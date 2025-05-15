from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import shutil
import sys # For sys.exit()

app = Flask(__name__)

# --- Configuration ---

# 1. Secret Key - CRUCIAL for sessions.
# MUST be set as an environment variable on Render.
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    print("CRITICAL ERROR: FLASK_SECRET_KEY environment variable is not set. Application cannot start securely.")
    print("Please set FLASK_SECRET_KEY in your Render service's environment variables.")
    sys.exit(1) # Exit if no secret key is provided by the environment

# 2. Admin Credentials - Hardcoded directly as per your request
ADMIN_USERNAME = 'admin'  # Change 'admin' to your desired username
ADMIN_PASSWORD = 'password' # Change 'password' to your desired strong password
print(f"INFO: Using hardcoded Admin Username: '{ADMIN_USERNAME}'") # Log for confirmation, be mindful if logs are public

# 3. DATA_DIR Configuration for Render Disks (Persistent File Storage)
# RENDER_DISK_MOUNT_PATH MUST be set as an environment variable on Render.
RENDER_DISK_MOUNT_PATH = os.environ.get('RENDER_DISK_MOUNT_PATH')
PERSISTENT_BASE_PATH = "" # Initialize

if not RENDER_DISK_MOUNT_PATH:
    # Heuristic: if RENDER_INSTANCE_ID is set by Render, then RENDER_DISK_MOUNT_PATH is mandatory
    if os.environ.get('RENDER_INSTANCE_ID'): # This env var is usually set by Render
        print(f"CRITICAL ERROR: RENDER_DISK_MOUNT_PATH environment variable is not set on Render. Cannot determine persistent storage location.")
        sys.exit(1)
    else:
        # This block is for LOCAL DEVELOPMENT ONLY if RENDER_DISK_MOUNT_PATH is not set locally
        print("INFO: RENDER_DISK_MOUNT_PATH not set. Assuming local development.")
        print("INFO: For local development, DATA_DIR will be 'season_data' relative to app.py's directory.")
        PERSISTENT_BASE_PATH = os.path.abspath(os.path.dirname(__file__))
else:
    # RENDER_DISK_MOUNT_PATH is set, use it as the base for persistent data
    PERSISTENT_BASE_PATH = RENDER_DISK_MOUNT_PATH
    print(f"INFO: Using persistent disk mount path for data: {PERSISTENT_BASE_PATH}")

DATA_DIR = os.path.join(PERSISTENT_BASE_PATH, 'season_data')
print(f"INFO: Full DATA_DIR path is configured as: {DATA_DIR}")

# --- Ensure the DATA_DIR exists (crucial for first run or if disk is empty) ---
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"INFO: DATA_DIR successfully ensured/created at: {DATA_DIR}")
except OSError as e:
    print(f"CRITICAL ERROR: Could not create DATA_DIR at '{DATA_DIR}'. OS Error: {e}")
    print(f"Please check permissions and if the base path '{PERSISTENT_BASE_PATH}' is writable by the application on Render.")
    sys.exit(1) # Exit if essential data directory cannot be created
except Exception as e_gen:
    print(f"CRITICAL ERROR: An unexpected error occurred while creating DATA_DIR at '{DATA_DIR}': {e_gen}")
    sys.exit(1)


# --- Helper Functions (CSV-based, using the configured DATA_DIR) ---
def get_seasons():
    try:
        if not os.path.isdir(DATA_DIR):
            print(f"DEBUG: DATA_DIR '{DATA_DIR}' is not a directory in get_seasons.")
            return []
        season_list = [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
        # print(f"DEBUG: Seasons found in {DATA_DIR}: {season_list}")
        return season_list
    except FileNotFoundError: # Should be less likely now but good to keep
        print(f"DEBUG: DATA_DIR '{DATA_DIR}' not found when listing seasons.")
        return []
    except Exception as e:
        print(f"ERROR in get_seasons accessing '{DATA_DIR}': {e}")
        return []

def get_fixture_file(season_name_str):
    return os.path.join(DATA_DIR, season_name_str, 'fixtures.csv')

def generate_fixtures(team_names_list):
    fixtures = []
    if not isinstance(team_names_list, list) or len(team_names_list) < 2:
        print(f"DEBUG: generate_fixtures - Not enough teams ({len(team_names_list)}) or invalid input type.")
        return []
    for i in range(len(team_names_list)):
        for j in range(len(team_names_list)):
            if i != j:
                fixtures.append([str(team_names_list[i]), str(team_names_list[j]), '-', '-'])
    return fixtures

def save_fixtures(season_name_str, fixtures_list):
    season_path = os.path.join(DATA_DIR, season_name_str)
    file_path = get_fixture_file(season_name_str)
    try:
        os.makedirs(season_path, exist_ok=True) # Ensure season-specific directory exists
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(fixtures_list)
        print(f"INFO: Fixtures saved for season '{season_name_str}' at '{file_path}'")
    except Exception as e:
        print(f"ERROR saving fixtures for season '{season_name_str}' to '{file_path}': {e}")
        # In a real app, you might want to raise this error or return a status
        # to inform the calling route that the save failed.

def load_fixtures(season_name_str):
    path = get_fixture_file(season_name_str)
    loaded_data = []
    if os.path.exists(path):
        try:
            with open(path, 'r', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row: # Process only non-empty rows
                        while len(row) < 4: row.append('-') # Pad if fewer than 4 columns
                        loaded_data.append(row[:4]) # Take only the first 4 elements
            return loaded_data
        except Exception as e:
            print(f"ERROR loading fixtures from '{path}': {e}")
            return [] # Return empty list on error
    else:
        print(f"DEBUG: Fixture file not found at '{path}' for season '{season_name_str}'.")
    return []

def calculate_points(fixtures_list):
    points = {}
    all_teams_in_fixtures = set()
    if not fixtures_list: return []

    for fixture_row in fixtures_list:
        if not isinstance(fixture_row, list) or len(fixture_row) < 4: continue
        home, away, hg_str, ag_str = str(fixture_row[0]), str(fixture_row[1]), str(fixture_row[2]), str(fixture_row[3])
        all_teams_in_fixtures.add(home); all_teams_in_fixtures.add(away)
        for team_name in [home, away]:
            if team_name not in points: points[team_name] = {'P':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'Pts':0}
        if hg_str == '-' or ag_str == '-': continue
        try: hg = int(hg_str); ag = int(ag_str)
        except ValueError: continue
        points[home]['P']+=1; points[away]['P']+=1; points[home]['GF']+=hg; points[home]['GA']+=ag
        points[away]['GF']+=ag; points[away]['GA']+=hg
        if hg > ag: points[home]['W']+=1; points[home]['Pts']+=3; points[away]['L']+=1
        elif ag > hg: points[away]['W']+=1; points[away]['Pts']+=3; points[home]['L']+=1
        else: points[home]['D']+=1; points[away]['D']+=1; points[home]['Pts']+=1; points[away]['Pts']+=1
    for team_name in all_teams_in_fixtures:
        if team_name not in points: points[team_name] = {'P':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'Pts':0}
    table = []
    for team, stats in points.items():
        table.append([team] + [stats[k] for k in ['P','W','D','L','GF','GA','Pts']])
    table.sort(key=lambda x: (-x[7], -(x[5]-x[6]), -x[5], str(x[0]))) # Pts, GD, GF, Name
    return table

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html', seasons=get_seasons())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        submitted_username = request.form.get('username')
        submitted_password = request.form.get('password')
        if submitted_username == ADMIN_USERNAME and submitted_password == ADMIN_PASSWORD:
            session['admin'] = True
            # flash('Login successful!', 'success') # Requires flash setup in template
            return redirect(url_for('index'))
        else:
            # flash_error('Invalid credentials.') # Requires flash setup in template
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    # flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/create_season', methods=['GET', 'POST'])
def create_season():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        team_names_raw = request.form.getlist('team_names')
        team_names = list(set([str(name).strip() for name in team_names_raw if str(name).strip()]))

        error = None
        if not season_name:
            error = "Season name cannot be empty."
        elif any(not c.isalnum() and c not in ' _-' for c in season_name): # Basic check for invalid chars
            error = "Season name contains invalid characters. Use letters, numbers, spaces, underscores, or hyphens."
        elif not team_names or len(team_names) < 2:
            error = "At least two unique, valid team names are required."
        elif season_name in get_seasons():
            error = f"Season '{season_name}' already exists."
        
        if error:
            # flash(error, 'danger') # Consider using flash for better UX
            return render_template('create_season.html', error=error, season_name=season_name, current_teams=team_names)

        print(f"INFO: Attempting to create season '{season_name}' with teams: {team_names}")
        fixtures = generate_fixtures(team_names)
        if fixtures: # Check if fixtures were actually generated
            save_fixtures(season_name, fixtures)
            print(f"INFO: Season '{season_name}' and fixtures should be saved.")
            # flash(f"Season '{season_name}' created successfully!", 'success')
        else:
            # This might happen if generate_fixtures returns an empty list (e.g., not enough teams)
            # The validation above should catch it, but as a safeguard:
            print(f"WARNING: No fixtures generated for season '{season_name}'. Season directory might be empty.")
            # flash(f"Season '{season_name}' was processed, but no fixtures were generated (check team count).", 'warning')
        return redirect(url_for('index'))
    return render_template('create_season.html')

@app.route('/<string:season>/points')
def points_table(season):
    # season is already a string due to <string:season>
    if season not in get_seasons():
        return redirect(url_for('index'))
    fixtures = load_fixtures(season)
    table = calculate_points(fixtures)
    headers = ['Team', 'Played', 'Won', 'Draw', 'Lost', 'GF', 'GA', 'Points']
    return render_template('points_table.html', season=season, table=table, headers=headers)

@app.route('/delete_season/<string:season>', methods=['POST'])
def delete_season(season):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    season_path = os.path.join(DATA_DIR, season)
    if os.path.exists(season_path) and os.path.isdir(season_path):
        try:
            shutil.rmtree(season_path)
            print(f"INFO: Season '{season}' deleted from '{season_path}'")
            # flash(f"Season '{season}' deleted successfully.", 'success')
        except OSError as e:
            print(f"ERROR deleting directory {season_path}: {e}")
            # flash(f"Error deleting season '{season}': {str(e)}", 'danger')
    # else:
        # flash(f"Season '{season}' not found for deletion.", 'warning')
    return redirect(url_for('index'))

@app.route('/<string:season>/update', methods=['GET', 'POST'])
def update_scores(season):
    if 'admin' not in session:
        return redirect(url_for('login'))

    if season not in get_seasons():
        return redirect(url_for('index'))

    fixtures = load_fixtures(season)

    if request.method == 'POST':
        updated_fixtures_data = []
        for i in range(len(fixtures)):
            original_home_team, original_away_team = fixtures[i][0], fixtures[i][1]
            current_home_score, current_away_score = fixtures[i][2], fixtures[i][3]

            form_home_goals = request.form.get(f'home_goals_{i}', '').strip()
            form_away_goals = request.form.get(f'away_goals_{i}', '').strip()

            new_home_score = current_home_score # Default to current score
            if form_home_goals == '' or form_home_goals == '-': new_home_score = '-'
            elif form_home_goals.isdigit(): new_home_score = form_home_goals
            
            new_away_score = current_away_score # Default to current score
            if form_away_goals == '' or form_away_goals == '-': new_away_score = '-'
            elif form_away_goals.isdigit(): new_away_score = form_away_goals
            
            updated_fixtures_data.append([original_home_team, original_away_team, new_home_score, new_away_score])
        
        save_fixtures(season, updated_fixtures_data)
        # flash(f"Scores for season '{season}' updated.", 'success')
        return redirect(url_for('points_table', season=season))

    return render_template('update_scores.html', season=season, fixtures=fixtures)

# --- Main Block (Primarily for Local Development) ---
if __name__ == '__main__':
    print(f"--- Flask App Starting (Local Development Mode) ---")
    # For local dev, if RENDER_DISK_MOUNT_PATH isn't set, DATA_DIR is relative to app.py
    # The global os.makedirs(DATA_DIR, exist_ok=True) handles its creation.
    print(f"Effective DATA_DIR: {DATA_DIR}")
    print(f"Admin Username (Hardcoded): {ADMIN_USERNAME}")
    # Do not print passwords, even in dev.
    # print(f"Admin Password (Hardcoded): {ADMIN_PASSWORD}")
    print(f"Flask Secret Key Set from ENV: {'Yes (value hidden)' if app.secret_key else 'No - CRITICAL (App will exit if not set on Render)'}")
    print(f"-------------------------------------------------")
    app.run(debug=True) # debug=True enables reloader & debugger locally

