from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import shutil


app = Flask(__name__)
app.secret_key = 'secret123'
DATA_DIR = os.path.join(os.getcwd(), 'season_data')

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

def get_seasons():
    return [d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))]

def get_fixture_file(season):
    return os.path.join(DATA_DIR, season, 'fixtures.csv')

def generate_fixtures(teams):
    fixtures = []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                fixtures.append([teams[i], teams[j], '-', '-'])  # Store '-' for unplayed
    return fixtures

def save_fixtures(season, fixtures):
    os.makedirs(os.path.join(DATA_DIR, season), exist_ok=True)
    with open(get_fixture_file(season), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(fixtures)

def load_fixtures(season):
    path = get_fixture_file(season)
    if os.path.exists(path):
        with open(path, 'r') as f:
            reader = csv.reader(f)
            return [[row[0], row[1], row[2], row[3]] for row in reader]  # Keep as string
    return []

def calculate_points(fixtures):
    points = {}
    for home, away, hg, ag in fixtures:
        if hg == '-' or ag == '-':
            continue  # Skip unplayed matches

        hg = int(hg)
        ag = int(ag)

        for team in [home, away]:
            if team not in points:
                points[team] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

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

    # Include teams with no matches played
    for home, away, _, _ in fixtures:
        for team in [home, away]:
            if team not in points:
                points[team] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

    table = []
    for team, stats in points.items():
        table.append([team] + [stats[k] for k in ['P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']])
    table.sort(key=lambda x: (-x[-1], x[0]))  # Sort by points, then name
    return table

@app.route('/')
def index():
    return render_template('index.html', seasons=get_seasons())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        else:
            return 'Invalid credentials'
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
        season = request.form['season_name']
        team_names = request.form.getlist('team_names')
        fixtures = generate_fixtures(team_names)
        save_fixtures(season, fixtures)
        return redirect(url_for('index'))
    return render_template('create_season.html')

@app.route('/<season>/points')
def points_table(season):
    fixtures = load_fixtures(season)
    table = calculate_points(fixtures)
    headers = ['Team', 'Played', 'Won', 'Draw', 'Lost', 'GF', 'GA', 'Points']
    return render_template('points_table.html', season=season, table=table, headers=headers)

@app.route('/delete_season/<season>', methods=['POST'])
def delete_season(season):
    if 'admin' not in session:
        return redirect(url_for('login'))
    
    season_path = os.path.join(DATA_DIR, season)
    if os.path.exists(season_path):
        shutil.rmtree(season_path)
    
    return redirect(url_for('index'))


@app.route('/<season>/update', methods=['GET', 'POST'])
def update_scores(season):
    if 'admin' not in session:
        return redirect(url_for('login'))

    fixtures = load_fixtures(season)

    if request.method == 'POST':
        for i in range(len(fixtures)):
            home_goals = request.form.get(f'home_goals_{i}', '').strip()
            away_goals = request.form.get(f'away_goals_{i}', '').strip()

            fixtures[i][2] = int(home_goals) if home_goals.isdigit() else '-'
            fixtures[i][3] = int(away_goals) if away_goals.isdigit() else '-'

        save_fixtures(season, fixtures)
        return redirect(url_for('points_table', season=season))

    return render_template('update_scores.html', season=season, fixtures=fixtures)

if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True)
