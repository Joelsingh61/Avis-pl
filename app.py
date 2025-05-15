from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = 'secret123'

# 🛠️ PostgreSQL DB config (use your credentials)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://leaguedb_user:qNcmn4yYXfS3OvoJ4HwgEb6zGGVhUs5V@dpg-d0idtt95pdvs7384av40-a/leaguedb'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------------------------
# 📦 Models
# -----------------------------------------
class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    teams = db.relationship('Team', backref='season', cascade="all, delete-orphan", lazy=True)
    fixtures = db.relationship('Fixture', backref='season', cascade="all, delete-orphan", lazy=True)

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)

class Fixture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    home_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    away_team_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    home_goals = db.Column(db.Integer, nullable=True)
    away_goals = db.Column(db.Integer, nullable=True)

    home_team = db.relationship('Team', foreign_keys=[home_team_id])
    away_team = db.relationship('Team', foreign_keys=[away_team_id])

# 🔐 Admin login credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

# -----------------------------------------
# 🌐 Routes
# -----------------------------------------

@app.route('/')
def index():
    seasons = Season.query.all()
    return render_template('index.html', seasons=seasons)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        return 'Invalid credentials', 401
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
        season_name = request.form['season_name'].strip()
        team_names = [t.strip() for t in request.form.getlist('team_names') if t.strip()]
        
        if not season_name or not team_names:
            return "Season name and teams are required", 400

        if Season.query.filter_by(name=season_name).first():
            return "Season already exists", 400

        season = Season(name=season_name)
        db.session.add(season)
        db.session.commit()

        # Add teams
        teams = []
        for name in team_names:
            team = Team(name=name, season=season)
            db.session.add(team)
            teams.append(team)
        db.session.commit()

        # Generate fixtures (round-robin home/away)
        for i in range(len(teams)):
            for j in range(len(teams)):
                if i != j:
                    db.session.add(Fixture(
                        season=season,
                        home_team=teams[i],
                        away_team=teams[j]
                    ))
        db.session.commit()
        return redirect(url_for('index'))

    return render_template('create_season.html')

@app.route('/<int:season_id>/points')
def points_table(season_id):
    season = Season.query.get_or_404(season_id)
    fixtures = Fixture.query.filter_by(season_id=season.id).all()

    points = {}
    for fixture in fixtures:
        home, away = fixture.home_team.name, fixture.away_team.name
        hg, ag = fixture.home_goals, fixture.away_goals

        if home not in points:
            points[home] = {'P':0, 'W':0, 'D':0, 'L':0, 'GF':0, 'GA':0, 'Pts':0}
        if away not in points:
            points[away] = {'P':0, 'W':0, 'D':0, 'L':0, 'GF':0, 'GA':0, 'Pts':0}

        if hg is None or ag is None:
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

    table = [[team] + [stats[k] for k in ['P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']] for team, stats in points.items()]
    table.sort(key=lambda x: (-x[-1], x[0]))

    headers = ['Team', 'Played', 'Won', 'Draw', 'Lost', 'GF', 'GA', 'Points']
    return render_template('points_table.html', season=season, table=table, headers=headers)

@app.route('/delete_season/<int:season_id>', methods=['POST'])
def delete_season(season_id):
    if 'admin' not in session:
        return redirect(url_for('login'))
    season = Season.query.get_or_404(season_id)
    db.session.delete(season)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/<int:season_id>/update', methods=['GET', 'POST'])
def update_scores(season_id):
    if 'admin' not in session:
        return redirect(url_for('login'))

    season = Season.query.get_or_404(season_id)
    fixtures = Fixture.query.filter_by(season_id=season.id).all()

    if request.method == 'POST':
        for fixture in fixtures:
            home_goals = request.form.get(f'home_goals_{fixture.id}', '').strip()
            away_goals = request.form.get(f'away_goals_{fixture.id}', '').strip()
            fixture.home_goals = int(home_goals) if home_goals.isdigit() else None
            fixture.away_goals = int(away_goals) if away_goals.isdigit() else None
        db.session.commit()
        return redirect(url_for('points_table', season_id=season.id))

    return render_template('update_scores.html', season=season, fixtures=fixtures)

# -----------------------------------------
# 🚀 Run the application
# -----------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
