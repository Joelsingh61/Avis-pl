import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

# --- Application Setup ---
app = Flask(__name__)

# === Configuration ===
# Secret Key (CRITICAL for session security)
# MUST be set in the environment for production.
SECRET_KEY_FROM_ENV = os.environ.get('FLASK_SECRET_KEY')
if SECRET_KEY_FROM_ENV:
    app.secret_key = SECRET_KEY_FROM_ENV
else:
    # Fallback for local development if FLASK_SECRET_KEY is not set
    # Check FLASK_ENV; Render might set NODE_ENV=production which sometimes works
    if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('NODE_ENV') == 'production':
        print("CRITICAL ERROR: FLASK_SECRET_KEY environment variable not set in production environment!")
        # In a real production scenario, you might want to raise an error or exit
        # For now, using a placeholder to allow startup for debugging, but this is insecure.
        app.secret_key = "PLEASE_SET_A_REAL_SECRET_KEY_IN_PRODUCTION_ENV"
    else:
        app.secret_key = 'dev_secret_key_123_!@#_this_is_not_for_production'
        print("WARNING: FLASK_SECRET_KEY environment variable not set. Using a default development key. DO NOT DEPLOY THIS TO PRODUCTION.")

# Database Configuration
# Expects DATABASE_URL to be set in the environment (Render provides this for linked DBs)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
if not app.config['SQLALCHEMY_DATABASE_URI']:
    print("WARNING: DATABASE_URL environment variable not set. Defaulting to local SQLite (league_data.db).")
    # Fallback to a local SQLite database file for development if DATABASE_URL is not set
    # Construct path relative to this file for the SQLite DB
    BASE_DIR_FOR_DB = os.path.abspath(os.path.dirname(__file__))
    SQLITE_DB_PATH = os.path.join(BASE_DIR_FOR_DB, 'league_data.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{SQLITE_DB_PATH}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Suppresses a Flask-SQLAlchemy warning

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Admin Credentials (Should be set via Environment Variables in Render)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin_fallback')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'password_fallback')
if ADMIN_USERNAME == 'admin_fallback' or ADMIN_PASSWORD == 'password_fallback':
    print("WARNING: Using fallback admin credentials. Set ADMIN_USERNAME and ADMIN_PASSWORD environment variables.")


# --- Database Models ---
class Season(db.Model):
    __tablename__ = 'season' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    fixtures = db.relationship('Fixture', backref='season_obj', lazy='dynamic', cascade="all, delete-orphan")
    # 'season_obj' is how Fixture can refer back to Season. 'dynamic' means fixtures query is not run automatically.

    def __repr__(self):
        return f'<Season {self.name}>'

class Fixture(db.Model):
    __tablename__ = 'fixture' # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id', name='fk_fixture_season_id'), nullable=False)
    home_team_name = db.Column(db.String(100), nullable=False)
    away_team_name = db.Column(db.String(100), nullable=False)
    home_goals = db.Column(db.Integer, nullable=True) # Null (None) means unplayed or '-'
    away_goals = db.Column(db.Integer, nullable=True) # Null (None) means unplayed or '-'

    def __repr__(self):
        hg_display = self.home_goals if self.home_goals is not None else '-'
        ag_display = self.away_goals if self.away_goals is not None else '-'
        return f'<Fixture {self.home_team_name} {hg_display}-{ag_display} {self.away_team_name} (Season ID: {self.season_id})>'


# --- Context Processor ---
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.datetime.utcnow().year}


# --- Helper Functions (Database Oriented) ---
def get_seasons_from_db():
    try:
        seasons_query = Season.query.order_by(Season.name).all()
        return [s.name for s in seasons_query]
    except Exception as e:
        # print(f"Error fetching seasons from DB: {e}")
        flash(f"Error accessing season data: {e}", "danger")
        return []

def generate_and_save_fixtures_db(season_db_obj, team_names_list):
    if not season_db_obj or not season_db_obj.id:
        # print("Error: Invalid season object passed to generate_and_save_fixtures_db")
        return False
    if len(team_names_list) < 2:
        # print("Error: Not enough teams to generate fixtures.")
        return False

    # Check if fixtures already exist for this season to prevent duplicates
    if Fixture.query.filter_by(season_id=season_db_obj.id).first():
        # print(f"Fixtures already exist for season: {season_db_obj.name}")
        return True # Or False if this should be an error condition

    fixtures_to_add = []
    for i in range(len(team_names_list)):
        for j in range(len(team_names_list)):
            if i != j:
                fixture = Fixture(
                    season_id=season_db_obj.id,
                    home_team_name=team_names_list[i],
                    away_team_name=team_names_list[j],
                    home_goals=None, # Represent '-' as None
                    away_goals=None
                )
                fixtures_to_add.append(fixture)
    try:
        db.session.add_all(fixtures_to_add)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        # print(f"Error saving fixtures to DB for season {season_db_obj.name}: {e}")
        flash(f"Database error saving fixtures: {e}", "danger")
        return False

def load_fixtures_from_db_for_template(season_name):
    season_obj = Season.query.filter_by(name=season_name).first()
    if not season_obj:
        return []
    
    db_fixtures = Fixture.query.filter_by(season_id=season_obj.id).order_by(Fixture.id).all()
    
    template_fixtures = []
    for fix in db_fixtures:
        template_fixtures.append({
            'id': fix.id, # Useful for forms if updating specific fixtures by ID
            'home_team_name': fix.home_team_name,
            'away_team_name': fix.away_team_name,
            'home_goals': str(fix.home_goals) if fix.home_goals is not None else '-',
            'away_goals': str(fix.away_goals) if fix.away_goals is not None else '-'
        })
    return template_fixtures


def calculate_points_for_display(fixtures_for_calc): # Expects list of dicts from load_fixtures_from_db_for_template
    points = {}
    all_teams_in_fixtures = set()

    if not fixtures_for_calc:
        return []

    for fixture_item in fixtures_for_calc:
        home = fixture_item['home_team_name']
        away = fixture_item['away_team_name']
        hg_str = fixture_item['home_goals']
        ag_str = fixture_item['away_goals']

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
            # print(f"Warning: Invalid score '{hg_str}' or '{ag_str}' in fixture for {home} vs {away}")
            continue

        points[home]['P'] += 1
        points[away]['P'] += 1
        points[home]['GF'] += hg
        points[home]['GA'] += ag
        points[away]['GF'] += ag
        points[away]['GA'] += hg

        if hg > ag:
            points[home]['W'] += 1; points[home]['Pts'] += 3; points[away]['L'] += 1
        elif ag > hg:
            points[away]['W'] += 1; points[away]['Pts'] += 3; points[home]['L'] += 1
        else:
            points[home]['D'] += 1; points[away]['D'] += 1; points[home]['Pts'] += 1; points[away]['Pts'] += 1
            
    for team_name in all_teams_in_fixtures:
        if team_name not in points:
             points[team_name] = {'P': 0, 'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0}

    table_data = []
    for team, stats in points.items():
        table_data.append([team, stats['P'], stats['W'], stats['D'], stats['L'], stats['GF'], stats['GA'], stats['Pts']])
    
    table_data.sort(key=lambda x: (-x[7], -(x[5] - x[6]), -x[5], x[0])) # Pts, GD (GF-GA), GF, Name
    return table_data


# --- Flask Routes ---
@app.route('/')
def index():
    seasons = get_seasons_from_db()
    return render_template('index.html', seasons=seasons)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'admin' in session: # If already logged in, redirect to index
        return redirect(url_for('index'))
    if request.method == 'POST':
        submitted_username = request.form.get('username')
        submitted_password = request.form.get('password')
        if submitted_username == ADMIN_USERNAME and submitted_password == ADMIN_PASSWORD:
            session['admin'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
            # No need to pass error to template if using flash
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/create_season', methods=['GET', 'POST'])
def create_season():
    if 'admin' not in session:
        flash('Admin access required to create a season.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        season_name = request.form.get('season_name', '').strip()
        # Get unique, non-empty team names
        team_names = list(set([name.strip() for name in request.form.getlist('team_names') if name.strip()]))

        # Validation
        if not season_name:
            flash('Season name cannot be empty.', 'danger')
        elif not team_names or len(team_names) < 2:
            flash('At least two unique team names are required.', 'danger')
        elif Season.query.filter_by(name=season_name).first():
            flash(f"A season named '{season_name}' already exists.", 'warning')
        else:
            # Proceed to create season and fixtures
            new_season = Season(name=season_name)
            db.session.add(new_season)
            try:
                db.session.commit() # Commit to get an ID for new_season for fixture foreign keys
                if generate_and_save_fixtures_db(new_season, team_names):
                    flash(f"Season '{season_name}' and fixtures created successfully!", 'success')
                    return redirect(url_for('index'))
                else:
                    # Fixture generation failed, season was created but might be empty of fixtures
                    # We might want to delete the season then or just warn
                    db.session.delete(new_season) # Rollback implicit: delete the season if fixtures failed
                    db.session.commit()
                    flash(f"Could not generate fixtures for '{season_name}'. Season not created.", 'danger')
            except Exception as e:
                db.session.rollback()
                flash(f"Database error creating season '{season_name}': {str(e)}", 'danger')
                # print(f"Error in create_season during DB commit: {e}")

        # If any validation failed or DB error, re-render form with submitted values
        return render_template('create_season.html', season_name=season_name, current_teams=team_names)

    return render_template('create_season.html')


@app.route('/<string:season_name>/points')
def points_table(season_name):
    season = Season.query.filter_by(name=season_name).first()
    if not season:
        flash(f"Season '{season_name}' not found.", 'danger')
        return redirect(url_for('index'))
    
    fixtures_for_display = load_fixtures_from_db_for_template(season_name)
    table = calculate_points_for_display(fixtures_for_display)
    headers = ['Team', 'P', 'W', 'D', 'L', 'GF', 'GA', 'Pts']
    return render_template('points_table.html', season=season_name, table=table, headers=headers)

@app.route('/delete_season/<string:season_name>', methods=['POST'])
def delete_season(season_name):
    if 'admin' not in session:
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))
    
    season_to_delete = Season.query.filter_by(name=season_name).first()
    if season_to_delete:
        try:
            # Due to cascade="all, delete-orphan" on Season.fixtures,
            # deleting the season should also delete its associated fixtures.
            db.session.delete(season_to_delete)
            db.session.commit()
            flash(f"Season '{season_name}' and all its data deleted successfully.", 'success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error deleting season '{season_name}': {str(e)}", 'danger')
            # print(f"Error deleting season '{season_name}': {e}")
    else:
        flash(f"Season '{season_name}' not found.", 'warning')
            
    return redirect(url_for('index'))

@app.route('/<string:season_name>/update', methods=['GET', 'POST'])
def update_scores(season_name):
    if 'admin' not in session:
        flash('Admin access required.', 'danger')
        return redirect(url_for('login'))

    season_obj = Season.query.filter_by(name=season_name).first()
    if not season_obj:
        flash(f"Season '{season_name}' not found.", 'danger')
        return redirect(url_for('index'))

    # Fetch fixtures with their IDs for precise updates
    db_fixtures = Fixture.query.filter_by(season_id=season_obj.id).order_by(Fixture.id).all()

    if request.method == 'POST':
        try:
            for i, fixture_db_obj in enumerate(db_fixtures):
                # Use loop.index0 from template for name, or if sending fixture IDs, match by ID
                home_goals_str = request.form.get(f'home_goals_{i}', '').strip() # Assuming names are home_goals_0, home_goals_1 etc.
                away_goals_str = request.form.get(f'away_goals_{i}', '').strip()

                if home_goals_str == '' or home_goals_str == '-':
                    fixture_db_obj.home_goals = None
                elif home_goals_str.isdigit():
                    fixture_db_obj.home_goals = int(home_goals_str)
                # else: input was invalid, score remains unchanged (or you can flash an error)

                if away_goals_str == '' or away_goals_str == '-':
                    fixture_db_obj.away_goals = None
                elif away_goals_str.isdigit():
                    fixture_db_obj.away_goals = int(away_goals_str)
                # else: input was invalid, score remains unchanged

            db.session.commit()
            flash(f"Scores for season '{season_name}' updated successfully!", 'success')
            return redirect(url_for('points_table', season_name=season_name))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating scores: {str(e)}", 'danger')
            # print(f"Error updating scores: {e}")
    
    # Prepare fixtures for template display (similar to load_fixtures_from_db_for_template)
    template_fixtures_display = []
    for fix in db_fixtures:
         template_fixtures_display.append({
             'id': fix.id, 
             'home_team_name': fix.home_team_name,
             'away_team_name': fix.away_team_name,
             'home_goals': str(fix.home_goals) if fix.home_goals is not None else '-',
             'away_goals': str(fix.away_goals) if fix.away_goals is not None else '-'
         })

    return render_template('update_scores.html', season=season_name, fixtures=template_fixtures_display)


# --- Main Block for Local Development ---
if __name__ == '__main__':
    with app.app_context():
        # This will create tables based on your models if they don't exist.
        # It's safe to run multiple times. It won't drop/recreate existing tables.
        # For Render, you'll typically run this once via the shell after first deploy.
        db.create_all()
        print("Initialized the database (created tables if they didn't exist).")
    
    # For local development, you can specify host and port
    # host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    # port = int(os.environ.get('FLASK_RUN_PORT', 5000)) # Default Flask port
    app.run(debug=True) # debug=True for development, Gunicorn handles this in prod on Render
