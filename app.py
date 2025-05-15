from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import io
import base64
import requests

app = Flask(__name__)
app.secret_key = 'secret123'

# GitHub Configuration

GITHUB_REPO = "Joelsingh61/Avis-pl"  
GITHUB_BRANCH = "main"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API = "https://api.github.com"


ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

def github_headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

def get_seasons():
    r = requests.get(GITHUB_API_URL, headers=github_headers())
    if r.status_code == 200:
        return [item['name'] for item in r.json() if item['type'] == 'dir']
    return []

def get_fixture_file_path(season):
    return f'season_data/{season}/fixtures.csv'

def get_fixture_file_url(season):
    return f'{GITHUB_API_URL}/{season}/fixtures.csv'

def generate_fixtures(teams):
    fixtures = []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                fixtures.append([teams[i], teams[j], '-', '-'])
    return fixtures

def save_fixtures(season, fixtures):
    # Prepare CSV content
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(fixtures)
    csv_content = output.getvalue()

    # Base64 encode
    content_encoded = base64.b64encode(csv_content.encode()).decode()

    # Create season folder if not exists (we rely on GitHub structure only)
    file_path = get_fixture_file_path(season)
    url = f'https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{file_path}'

    # Check if file exists to determine whether to PUT or POST
    r = requests.get(url, headers=github_headers())
    if r.status_code == 200:
        sha = r.json()['sha']
        data = {
            "message": f"Update fixtures for {season}",
            "content": content_encoded,
            "sha": sha
        }
    else:
        data = {
            "message": f"Create fixtures for {season}",
            "content": content_encoded
        }

    requests.put(url, headers=github_headers(), json=data)

def load_fixtures(season):
    url = get_fixture_file_url(season)
    r = requests.get(url, headers=github_headers())
    if r.status_code == 200:
        content = base64.b64decode(r.json()['content']).decode()
        reader = csv.reader(io.StringIO(content))
        return [row for row in reader]
    return []

def delete_season_on_github(season):
    url = f'{GITHUB_API_URL}/{season}'
    r = requests.get(url, headers=github_headers())
    if r.status_code == 200:
        items = r.json()
        for item in items:
            delete_url = item['url']
            sha = item['sha']
            requests.delete(delete_url, headers=github_headers(), json={
                'message': f'Delete {item["name"]}',
                'sha': sha
            })

def calculate_points(fixtures):
    points = {}
    for home, away, hg, ag in fixtures:
        if hg == '-' or ag == '-':
            continue

        hg, ag = int(hg), int(ag)

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

    for home, away, _, _ in fixtures:
        for team in [home, away]:
            if team not in points:
                points[team] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

    table = []
    for team, stats in points.items():
        table.append([team] + [stats[k] for k in ['P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']])
    table.sort(key=lambda x: (-x[-1], x[0]))
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
    delete_season_on_github(season)
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
    app.run(debug=True)
