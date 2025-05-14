from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import shutil
# import datetime # Not used in this minimal version if you don't add the context processor

app = Flask(__name__)
app.secret_key = 'secret123' # For Render, set this via Environment Variable if possible

# --- Define BASE_DIR and DATA_DIR correctly for Render ---
# Get the absolute path of the directory where app.py is located
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'season_data')

# --- Ensure the DATA_DIR exists when the app starts ---
# This is crucial for platforms like Render/Vercel
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    # Handle or log the error if DATA_DIR creation fails,
    # though exist_ok=True should prevent error if it already exists.
    pass

# --- Admin Credentials (Hardcoded as in original) ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

# --- Helper Functions (Unchanged logic, but will now use the robust DATA_DIR) ---
def get_seasons():
    try:
        # Check if DATA_DIR exists before trying to list its contents
        if not os.path.isdir(DATA_DIR):
            return [] # Return empty list ifDATA_DIR doesn't exist or is not a directory
        return [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]
    except FileNotFoundError: # Should be rare now with os.makedirs
        return []

def get_fixture_file(season):
    return os.path.join(DATA_DIR, season, 'fixtures.csv')

def generate_fixtures(teams):
    fixtures = []
    if len(teams) < 2:
        return []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                fixtures.append([teams[i], teams[j], '-', '-'])
    return fixtures

def save_fixtures(season, fixtures):
    season_path = os.path.join(DATA_DIR, season)
    os.makedirs(season_path, exist_ok=True) # Ensure individual season directory also exists
    with open(get_fixture_file(season), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(fixtures)

def load_fixtures(season):
    path = get_fixture_file(season)
    if os.path.exists(path):
        with open(path, 'r') as f:
            reader = csv.reader(f)
            # Basic check for row structure, assuming 4 columns
            loaded_data = []
            for row in reader:
                if row and len(row) == 4: # Only process non-empty rows with expected columns
                    loaded_data.append([row[0], row[1], row[2], row[3]])
                elif row: # If row exists but not 4 columns, maybe log or handle
                    # print(f"Warning: Malformed row in {path}: {row}")
                    pass
            return loaded_data
    return []

def calculate_points(fixtures):
    points = {}
    all_teams_in_fixtures = set()

    if not fixtures:
        return []

    for fixture_row in fixtures:
        if len(fixture_row) < 4:
            continue 

        home, away, hg_str, ag_str = fixture_row
        all_teams_in_fixtures.add(home)
        all_teams_in_fixtures.add(away)

        for team in [home, away]:
            if team not in points:
                points[team] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

        if hg_str == '-' or ag_str == '-':
            continue

        try:
            hg = int(hg_str)
            ag = int(ag_str)
        except ValueError:
            continue

        points[home]['P'] += 1
        points[away]['P'] += 1
        points[home]['GF'] += hg
        points[home]['GA'] += ag
        points[away]['GF'] += ag
        points[away]['GA'] += hg

        if hg > ag:
            points[home]['W'] += 1
            points[home]['Pts'] += 3
            points[away]['L'] += 1
        elif ag > hg:
            points[away]['W'] += 1
            points[away]['Pts'] += 3
            points[home]['L'] += 1
        else:
            points[home]['D'] += 1
            points[away]['D'] += 1
            points[home]['Pts'] += 1
            points[away]['Pts'] += 1

    for team_name in all_teams_in_fixtures:
        if team_name not in points:
             points[team_name] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

    table = []
    for team, stats in points.items():
        table.append([team] + [stats[k] for k in ['P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']])
    
    # Original sort: by points, then name
    table.sort(key=lambda x: (-x[-1], x[0]))
    return table

# --- Flask Routes (Unchanged from your original, except for small non-functional comments where flash could go) ---
@app.route('/')
def index():
    return render_template('index.html', seasons=get_seasons())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Using .get() is safer to avoid KeyError if form field is missing
        submitted_username = request.form.get('username')
        submitted_password = request.form.get('password')
        if submitted_username == ADMIN_USERNAME and submitted_password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        else:
            # For the "Invalid credentials" message to show on login page,
            # login.html needs to be able to render an error message.
            # And this route needs to pass that error when re-rendering.
            # Original returned a plain string, keeping it similar:
            return 'Invalid credentials' # Or: render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/create_season', methods=['GET', 'POST'])
def create_season():
    if 'admin' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        team_names = [name.strip() for name in request.form.getlist('team_names') if name.strip()]

        if not season_name:
            # Could render_template with error: 'Season name required'
            return redirect(request.url) # Simple redirect back if error
        if not team_names or len(team_names) < 2:
            # Could render_template with error: 'At least 2 teams required'
            return redirect(request.url) # Simple redirect back

        # Basic check if season already exists (case-sensitive)
        if season_name in get_seasons():
            # Could render_template with error: 'Season already exists'
            return redirect(request.url) # Simple redirect back

        fixtures = generate_fixtures(team_names)
        if fixtures: # Only save if fixtures were generated
            save_fixtures(season_name, fixtures)
        return redirect(url_for('index'))
    return render_template('create_season.html')

@app.route('/<season>/points')
def points_table(season):
    if season not in get_seasons(): # Basic check
        return redirect(url_for('index'))
    fixtures = load_fixtures(season)
    table = calculate_points(fixtures)
    headers = ['Team', 'Played', 'Won', 'Draw', 'Lost', 'GF', 'GA', 'Points']
    return render_template('points_table.html', season=season, table=table, headers=headers)

@app.route('/delete_season/<season>', methods=['POST'])
def delete_season(season):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    season_path = os.path.join(DATA_DIR, season)
    # Ensure it's a directory before trying to rmtree
    if os.path.exists(season_path) and os.path.isdir(season_path):
        try:
            shutil.rmtree(season_path)
        except OSError:
            # Could log error or flash message
            pass
            
    return redirect(url_for('index'))


@app.route('/<season>/update', methods=['GET', 'POST'])
def update_scores(season):
    if 'admin' not in session:
        return redirect(url_for('login'))
    if season not in get_seasons(): # Basic check
        return redirect(url_for('index'))

    fixtures = load_fixtures(season)

    if request.method == 'POST':
        updated_fixtures = []
        for i in range(len(fixtures)):
            original_fixture_line = fixtures[i]
            home_team = original_fixture_line[0]
            away_team = original_fixture_line[1]

            home_goals_str = request.form.get(f'home_goals_{i}', '').strip()
            away_goals_str = request.form.get(f'away_goals_{i}', '').strip()

            # Simplified logic from original: keep '-' if not digit, else convert to int, then back to str for saving.
            # This assumes fixture[2] and fixture[3] always store strings.
            hg = str(int(home_goals_str)) if home_goals_str.isdigit() else '-'
            ag = str(int(away_goals_str)) if away_goals_str.isdigit() else '-'
            
            # A slight refinement from your original to ensure '-' if truly empty,
            # otherwise use the new value (if digit) or keep original (if not digit and not cleared)
            if home_goals_str == '':
                hg = '-'
            elif home_goals_str.isdigit():
                hg = home_goals_str
            else: # Not a digit and not empty, keep original score
                hg = original_fixture_line[2]

            if away_goals_str == '':
                ag = '-'
            elif away_goals_str.isdigit():
                ag = away_goals_str
            else: # Not a digit and not empty, keep original score
                ag = original_fixture_line[3]

            updated_fixtures.append([home_team, away_team, hg, ag])

        save_fixtures(season, updated_fixtures)
        return redirect(url_for('points_table', season=season))

    return render_template('update_scores.html', season=season, fixtures=fixtures)

if __name__ == '__main__':
    # os.makedirs(DATA_DIR, exist_ok=True) # This is now handled at the top, globally
    app.run(debug=True)
