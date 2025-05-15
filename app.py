from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import shutil
import sys # For exiting if critical config is missing

app = Flask(__name__)

# --- Configuration ---

# Secret Key - CRUCIAL for sessions - MUST be set as an environment variable on Render
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    print("CRITICAL ERROR: FLASK_SECRET_KEY environment variable is not set. Application cannot start securely.")
    print("Please set FLASK_SECRET_KEY in your Render service's environment variables.")
    sys.exit(1) # Exit if no secret key is provided

# Admin Credentials - Hardcoded directly as per your request
ADMIN_USERNAME = 'admin'  # Or your desired username
ADMIN_PASSWORD = 'password' # Or your desired password
print(f"INFO: Using hardcoded Admin Username: {ADMIN_USERNAME}") # Be mindful of logging credentials

# DATA_DIR Configuration for Render Disks (Persistent File Storage)
# RENDER_DISK_MOUNT_PATH MUST be set as an environment variable on Render
RENDER_DISK_MOUNT_PATH = os.environ.get('RENDER_DISK_MOUNT_PATH')
PERSISTENT_BASE_PATH = "" # Initialize

if not RENDER_DISK_MOUNT_PATH:
    # Heuristic: if RENDER_INSTANCE_ID is set by Render, then RENDER_DISK_MOUNT_PATH is mandatory
    if os.environ.get('RENDER_INSTANCE_ID'):
        print(f"CRITICAL ERROR: RENDER_DISK_MOUNT_PATH environment variable not set on Render. Cannot determine persistent storage location.")
        sys.exit(1)
    else:
        # This block is for LOCAL DEVELOPMENT ONLY if RENDER_DISK_MOUNT_PATH is not set locally
        print("INFO: RENDER_DISK_MOUNT_PATH not set. Assuming local development.")
        print("INFO: For local development, DATA_DIR will be 'season_data' relative to app.py's directory.")
        PERSISTENT_BASE_PATH = os.path.abspath(os.path.dirname(__file__))
else:
    PERSISTENT_BASE_PATH = RENDER_DISK_MOUNT_PATH
    print(f"INFO: Using persistent disk mount path for data: {PERSISTENT_BASE_PATH}")

DATA_DIR = os.path.join(PERSISTENT_BASE_PATH, 'season_data')

# --- Ensure the DATA_DIR exists ---
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"INFO: DATA_DIR ensured at: {DATA_DIR}")
except OSError as e:
    print(f"CRITICAL ERROR: Could not create DATA_DIR at '{DATA_DIR}'. Error: {e}. Application will likely fail.")
    # Depending on how critical DATA_DIR is, you might exit here too.
    # sys.exit(1)
    pass


# --- Helper Functions (Your original CSV logic, now using the configured DATA_DIR) ---
# (Copy all your helper functions: get_seasons, get_fixture_file, generate_fixtures,
#  save_fixtures, load_fixtures, calculate_points here.
#  Make sure they use the global DATA_DIR variable.)
def get_seasons():
    try:
        if not os.path.isdir(DATA_DIR): return []
        return [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    except Exception as e:
        print(f"ERROR in get_seasons accessing '{DATA_DIR}': {e}"); return []

def get_fixture_file(season):
    return os.path.join(DATA_DIR, str(season), 'fixtures.csv')

def generate_fixtures(teams):
    fixtures = []
    if not isinstance(teams, list) or len(teams) < 2: return []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j: fixtures.append([str(teams[i]), str(teams[j]), '-', '-'])
    return fixtures

def save_fixtures(season, fixtures):
    season_str = str(season)
    season_path = os.path.join(DATA_DIR, season_str)
    file_path = get_fixture_file(season_str)
    try:
        os.makedirs(season_path, exist_ok=True)
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f); writer.writerows(fixtures)
    except Exception as e: print(f"ERROR saving fixtures for season '{season_str}' to '{file_path}': {e}")

def load_fixtures(season):
    season_str = str(season)
    path = get_fixture_file(season_str)
    loaded_data = []
    if os.path.exists(path):
        try:
            with open(path, 'r', newline='') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row:
                        while len(row) < 4: row.append('-')
                        loaded_data.append(row[:4])
            return loaded_data
        except Exception as e: print(f"ERROR loading fixtures from '{path}': {e}"); return []
    return []

def calculate_points(fixtures):
    points = {}; all_teams_in_fixtures = set()
    if not fixtures: return []
    for fixture_row in fixtures:
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
    table.sort(key=lambda x: (-x[7], -(x[5]-x[6]), -x[5], str(x[0])))
    return table

# --- Flask Routes (Your original logic) ---
# (Copy all your @app.route definitions here.
#  They will use the global ADMIN_USERNAME and ADMIN_PASSWORD)
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
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/create_season', methods=['GET', 'POST'])
def create_season():
    if 'admin' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        team_names_raw = request.form.getlist('team_names')
        team_names = list(set([str(name).strip() for name in team_names_raw if str(name).strip()]))
        error = None
        if not season_name: error = "Season name cannot be empty."
        elif not team_names or len(team_names) < 2: error = "At least two unique team names are required."
        elif season_name in get_seasons(): error = f"Season '{season_name}' already exists."
        if error:
            return render_template('create_season.html', error=error, season_name=season_name, current_teams=team_names)
        fixtures = generate_fixtures(team_names)
        if fixtures: save_fixtures(season_name, fixtures)
        return redirect(url_for('index'))
    return render_template('create_season.html')

@app.route('/<string:season>/points')
def points_table(season):
    if str(season) not in get_seasons(): return redirect(url_for('index'))
    fixtures = load_fixtures(str(season))
    table = calculate_points(fixtures)
    headers = ['Team', 'Played', 'Won', 'Draw', 'Lost', 'GF', 'GA', 'Points']
    return render_template('points_table.html', season=str(season), table=table, headers=headers)

@app.route('/delete_season/<string:season>', methods=['POST'])
def delete_season(season):
    if 'admin' not in session: return redirect(url_for('login'))
    season_path = os.path.join(DATA_DIR, str(season))
    if os.path.exists(season_path) and os.path.isdir(season_path):
        try: shutil.rmtree(season_path)
        except OSError as e: print(f"ERROR deleting directory {season_path}: {e}")
    return redirect(url_for('index'))

@app.route('/<string:season>/update', methods=['GET', 'POST'])
def update_scores(season):
    if 'admin' not in session: return redirect(url_for('login'))
    season_str = str(season)
    if season_str not in get_seasons(): return redirect(url_for('index'))
    fixtures = load_fixtures(season_str)
    if request.method == 'POST':
        updated_fixtures_data = []
        for i in range(len(fixtures)):
            o_home, o_away, cur_hg, cur_ag = fixtures[i]
            form_hg = request.form.get(f'home_goals_{i}', '').strip()
            form_ag = request.form.get(f'away_goals_{i}', '').strip()
            new_hg = cur_hg
            if form_hg == '' or form_hg == '-': new_hg = '-'
            elif form_hg.isdigit(): new_hg = form_hg
            new_ag = cur_ag
            if form_ag == '' or form_ag == '-': new_ag = '-'
            elif form_ag.isdigit(): new_ag = form_ag
            updated_fixtures_data.append([o_home, o_away, new_hg, new_ag])
        save_fixtures(season_str, updated_fixtures_data)
        return redirect(url_for('points_table', season=season_str))
    return render_template('update_scores.html', season=season_str, fixtures=fixtures)


# --- Main Block for Local Development ---
if __name__ == '__main__':
    print(f"--- Flask App (Local Development Mode) ---")
    if not RENDER_DISK_MOUNT_PATH: # Only if RENDER_DISK_MOUNT_PATH is not set (i.e., local dev)
        # Ensure local DATA_DIR exists for development convenience
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            print(f"INFO: Local DATA_DIR for development ensured at: {DATA_DIR}")
        except OSError as e:
            print(f"WARNING: Could not create local DATA_DIR at '{DATA_DIR}'. Error: {e}")

    print(f"DATA_DIR is configured to: {DATA_DIR}")
    print(f"Admin Username (hardcoded): {ADMIN_USERNAME}")
    print(f"Flask Secret Key Set from ENV: {'Yes' if app.secret_key else 'No - CRITICAL (App will exit on Render if not set)'}")
    print(f"-------------------------------------------")
    app.run(debug=True)

