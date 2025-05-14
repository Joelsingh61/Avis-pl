from flask import Flask, render_template, request, redirect, url_for, session, flash # Added flash
from flask_sqlalchemy import SQLAlchemy
import os
# import csv # No longer needed for primary data storage
# import shutil # No longer needed for DATA_DIR management
import datetime

app = Flask(__name__)

# --- Database Configuration ---
# Render will provide DATABASE_URL as an environment variable
# For local development, you might set up a local Postgres DB or use SQLite
# Example for local SQLite (easier to start with locally):
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///league_data.db'
# For Render (it will inject DATABASE_URL):
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://leaguedb_user:qNcmn4yYXfS3OvoJ4HwgEb6zGGVhUs5V@dpg-cmdidtt95pdvs7384av40-a/leaguedb')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Recommended

# --- Secret Key ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY', '')
if app.secret_key == 'f3a8c2e5b7d9a1c0b8e4f7a2d1c0e9f6a3b7d8c1e5f0a2b9d4c7e1f3a0b8d6c2' and app.env == 'production':
    # print("WARNING: Using default FLASK_SECRET_KEY in production!", file=sys.stderr) # Requires import sys
    pass


db = SQLAlchemy(app)

# --- Admin Credentials (Use Environment Variables) ---
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password')

# --- Database Models ---
class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # Relationship to fixtures (one season has many fixtures)
    fixtures = db.relationship('Fixture', backref='season_ref', lazy=True, cascade="all, delete-orphan")
    # If you want to store teams per season distinctly
    # teams = db.relationship('Team', backref='season', lazy=True)

    def __repr__(self):
        return f'<Season {self.name}>'

class Team(db.Model): # You might not need a separate Team table if team names are just strings in Fixtures
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # If you want to associate teams with seasons or fixtures, add relationships here

    def __repr__(self):
        return f'<Team {self.name}>'

class Fixture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'), nullable=False)
    home_team_name = db.Column(db.String(100), nullable=False)
    away_team_name = db.Column(db.String(100), nullable=False)
    home_goals = db.Column(db.Integer, nullable=True) # Nullable if score is '-'
    away_goals = db.Column(db.Integer, nullable=True) # Nullable if score is '-'

    def __repr__(self):
        return f'<Fixture {self.home_team_name} vs {self.away_team_name} in Season ID {self.season_id}>'


# --- Context Processor for Current Year ---
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.utcnow().year}


# --- Helper Functions (Rewritten for Database) ---
def get_seasons_from_db():
    seasons = Season.query.order_by(Season.name).all()
    return [s.name for s in seasons]

def generate_and_save_fixtures_db(season_name, team_names_list):
    season = Season.query.filter_by(name=season_name).first()
    if not season:
        # This assumes create_season route first creates the Season object.
        # Or, this function could create it if it doesn't exist.
        # For simplicity now, let's assume 'season' object is passed or created before.
        return False # Or raise an error

    if len(team_names_list) < 2:
        return False

    existing_fixtures = Fixture.query.filter_by(season_id=season.id).all()
    if existing_fixtures: # Avoid regenerating if fixtures exist for the season
        # print(f"Fixtures already exist for season {season_name}")
        return True

    for i in range(len(team_names_list)):
        for j in range(len(team_names_list)):
            if i != j:
                fixture = Fixture(
                    season_id=season.id,
                    home_team_name=team_names_list[i],
                    away_team_name=team_names_list[j],
                    home_goals=None, # Represent '-' as None in DB if integer type
                    away_goals=None
                )
                db.session.add(fixture)
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        # print(f"Error saving fixtures to DB: {e}")
        return False


def load_fixtures_from_db(season_name):
    season = Season.query.filter_by(name=season_name).first()
    if not season:
        return []
    fixtures_db = Fixture.query.filter_by(season_id=season.id).all()
    # Convert to the list-of-lists format your `calculate_points` expects
    fixtures_list = []
    for fix in fixtures_db:
        hg = fix.home_goals if fix.home_goals is not None else '-'
        ag = fix.away_goals if fix.away_goals is not None else '-'
        fixtures_list.append([fix.home_team_name, fix.away_team_name, str(hg), str(ag)])
    return fixtures_list


def calculate_points_db(fixtures_list_from_db): # This function's internal logic can remain similar
    points = {}
    all_teams_in_fixtures = set()

    if not fixtures_list_from_db:
        return []

    for fixture_row in fixtures_list_from_db:
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
    table.sort(key=lambda x: (-x[7], -(x[5] - x[6]), -x[5], x[0])) # Pts, GD, GF, Name
    return table


# --- Flask Routes (Modified to use DB functions) ---

@app.route('/')
def index():
    seasons = get_seasons_from_db()
    return render_template('index.html', seasons=seasons)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        submitted_username = request.form.get('username')
        submitted_password = request.form.get('password')
        if submitted_username == ADMIN_USERNAME and submitted_password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/create_season', methods=['GET', 'POST'])
def create_season():
    if 'admin' not in session:
        flash('Please log in to create a season.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        team_names = list(set([name.strip() for name in request.form.getlist('team_names') if name.strip()])) # Unique, stripped

        if not season_name:
            flash('Season name cannot be empty.', 'danger')
            return render_template('create_season.html', current_teams=team_names)
        if not team_names or len(team_names) < 2:
            flash('You must provide at least two unique team names.', 'danger')
            return render_template('create_season.html', season_name=season_name, current_teams=team_names)
        
        if Season.query.filter_by(name=season_name).first():
            flash(f"Season '{season_name}' already exists.", 'warning')
            return render_template('create_season.html', season_name=season_name, current_teams=team_names)

        # Create new season in DB
        new_season = Season(name=season_name)
        db.session.add(new_season)
        try:
            db.session.commit() # Commit to get new_season.id
            if generate_and_save_fixtures_db(new_season.name, team_names): # Pass season name
                flash(f"Season '{season_name}' and its fixtures created successfully!", 'success')
            else:
                # If fixture generation failed, we might want to rollback season creation or notify.
                # For now, assume it partly succeeded or needs attention.
                flash(f"Season '{season_name}' created, but there was an issue generating fixtures.", 'warning')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating season '{season_name}': {e}", 'danger')
            # print(f"DB Error creating season: {e}")
            return render_template('create_season.html', season_name=season_name, current_teams=team_names)

    return render_template('create_season.html')

@app.route('/<season_name>/points')
def points_table(season_name):
    season = Season.query.filter_by(name=season_name).first()
    if not season:
        flash(f"Season '{season_name}' not found.", 'danger')
        return redirect(url_for('index'))
    
    fixtures_list = load_fixtures_from_db(season_name)
    table = calculate_points_db(fixtures_list)
    headers = ['Team', 'P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']
    return render_template('points_table.html', season=season_name, table=table, headers=headers) # Pass season_name

@app.route('/delete_season/<season_name>', methods=['POST'])
def delete_season(season_name):
    if 'admin' not in session:
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))
    
    season_to_delete = Season.query.filter_by(name=season_name).first()
    if season_to_delete:
        try:
            # Fixtures will be cascade-deleted due to relationship setting
            db.session.delete(season_to_delete)
            db.session.commit()
            flash(f"Season '{season_name}' and all its data deleted successfully.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error deleting season '{season_name}': {e}", 'danger')
            # print(f"DB Error deleting season: {e}")
    else:
        flash(f"Season '{season_name}' not found.", 'warning')
            
    return redirect(url_for('index'))

@app.route('/<season_name>/update', methods=['GET', 'POST'])
def update_scores(season_name):
    if 'admin' not in session:
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))

    season = Season.query.filter_by(name=season_name).first()
    if not season:
        flash(f"Season '{season_name}' not found.", 'danger')
        return redirect(url_for('index'))

    # Get fixtures for the form (we need their IDs for updating specific ones)
    db_fixtures_for_form = Fixture.query.filter_by(season_id=season.id).order_by(Fixture.id).all()

    if request.method == 'POST':
        try:
            for i, fix_db in enumerate(db_fixtures_for_form):
                home_goals_str = request.form.get(f'home_goals_{i}', '').strip()
                away_goals_str = request.form.get(f'away_goals_{i}', '').strip()

                if home_goals_str == '':
                    fix_db.home_goals = None
                elif home_goals_str.isdigit():
                    fix_db.home_goals = int(home_goals_str)
                # Else: if not empty and not digit, do nothing to keep previous or raise error earlier

                if away_goals_str == '':
                    fix_db.away_goals = None
                elif away_goals_str.isdigit():
                    fix_db.away_goals = int(away_goals_str)
                # Else: if not empty and not digit, do nothing

            db.session.commit()
            flash(f"Scores for season '{season_name}' updated successfully!", 'success')
            return redirect(url_for('points_table', season_name=season_name)) # Pass season_name
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating scores: {e}", 'danger')
            # print(f"DB Error updating scores: {e}")
    
    # Convert DB fixtures to list of lists for the template, if template expects that structure
    # Or better, adapt the template to use the fixture objects directly
    template_fixtures = []
    for fix_db in db_fixtures_for_form:
         hg = fix_db.home_goals if fix_db.home_goals is not None else '-'
         ag = fix_db.away_goals if fix_db.away_goals is not None else '-'
         template_fixtures.append({
             'id': fix_db.id, # Send ID to template if needed for form field names
             'home_team_name': fix_db.home_team_name,
             'away_team_name': fix_db.away_team_name,
             'home_goals': hg,
             'away_goals': ag
         })

    return render_template('update_scores.html', season=season_name, fixtures=template_fixtures) # Pass season_name


# Command to create database tables (run this once locally, or via Render shell, or in a startup script logic)
# You can create a separate script for this or a Flask CLI command.
# For Render, you might run this from the shell after the first deploy, or use migrations.
# with app.app_context():
# db.create_all()
# print("Database tables created (if they didn't exist).")

if __name__ == '__main__':
    # For local development with SQLite, this will create the DB file and tables
    with app.app_context():
        db.create_all()
        print("Initialized the local SQLite database (if it didn't exist).")
    app.run(debug=True, port=5001) # Use a different port to avoid conflicts if any


