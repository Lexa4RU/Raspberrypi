from flask import Flask, jsonify, render_template, request, redirect, url_for, make_response, session
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, decode_token
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_socketio import SocketIO
from datetime import datetime
from jwt.exceptions import PyJWTError
from markupsafe import escape
import mysql.connector as MC
from mysql.connector import Error
from datetime import timedelta
from collections import defaultdict
from dotenv import load_dotenv
import psutil
import subprocess
import time
import threading
import plotly.graph_objs as go
import hashlib
import os
import requests

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app)

app.secret_key = os.urandom(24)  

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(weeks=4)
app.config['JWT_TOKEN_LOCATION'] = os.getenv('JWT_TOKEN_LOCATION')
app.config['JWT_ACCESS_COOKIE_PATH'] = os.getenv('JWT_ACCESS_COOKIE_PATH')
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_ACCESS_COOKIE_NAME'] = os.getenv('JWT_ACCESS_COOKIE_NAME')

jwt = JWTManager(app)

def get_conn_connection():
    try:
        conn = MC.connect(
            host=os.getenv('host'),
            database=os.getenv('database'),
            user=os.getenv('user'),
            password=os.getenv('password')
        )
        if conn.is_connected():
            return conn
    except Error as e:
        print("Error while connecting to Data Base : ", e)
    return None

def fetch_all_as_dict(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def is_user_logged_in():
    try:
        access_token = request.cookies.get('access_token_cookie')
        if not access_token:
            return False

        decoded_token = decode_token(access_token, allow_expired=False)
        identity = decoded_token.get('sub')

        return identity is not None
    except PyJWTError:
        return False
    
@app.route('/')    
def index():
    is_logged_in = is_user_logged_in() 

    return render_template('index.html', is_logged_in = is_logged_in)    

@app.route('/data-tracker')
def data_tracker():
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
               t.*, 
               n.nom_nation AS nation 
            FROM tanks t 
            JOIN nations n ON t.nation_code = n.code_nation
            ORDER BY t.tier DESC, 
                    FIELD(t.class, 'Heavy Tank', 'Medium Tank', 'Tank Destroyer', 'Light Tank', 'Artillery')
        """)
        tanks = cursor.fetchall()
        cursor.close()
        conn.close()

        nation_order = [
            'Germany', 'USSR', 'USA', 'France', 'United Kingdom', 
            'China', 'Japan', 'Czech', 'Poland', 'Sweden', 'Italy'
        ]

        tanks_by_nation = {nation: [] for nation in nation_order}
        for tank in tanks:
            tanks_by_nation[tank['nation']].append(tank)

        is_logged_in = is_user_logged_in()
        return render_template('data_tracker.html', tanks_by_nation = tanks_by_nation, nation_order = nation_order, is_logged_in = is_logged_in)
    
    else:
        return "Error while connecting to Data Base"

@app.route('/data-tracker/image')
def image():
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
               t.*,
               n.nom_nation AS nation
            FROM tanks t
            JOIN nations n ON t.nation_code = n.code_nation
            ORDER BY t.tier DESC,
                    FIELD(t.class, 'Heavy Tank', 'Medium Tank', 'Tank Destroyer', 'Light Tank', 'Artillery')
        """)
        tanks = cursor.fetchall()
        cursor.close()
        conn.close()

        nation_order = [
            'Germany', 'USSR', 'USA', 'France', 'United Kingdom',
            'China', 'Japan', 'Czech', 'Poland', 'Sweden', 'Italy'
        ]

        tanks_by_nation = {nation: [] for nation in nation_order}
        for tank in tanks:
            tanks_by_nation[tank['nation']].append(tank)

        if tank:
            app_id = os.getenv('app_id') 
            api_url = f"https://api.worldoftanks.eu/wot/encyclopedia/vehicles/?application_id={app_id}&tank_id={tank['wg_id']}&fields=images.big_icon"
        
            try:
                response = requests.get(api_url).json()
                if response['status'] == 'ok' and str(tank['wg_id']) in response['data']:
                    # Get the URL directly from the API response
                    tank['api_image'] = response['data'][str(tank['wg_id'])]['images']['big_icon']
                else:
                    tank['api_image'] = None
            except Exception as e:
                print(f"API Error: {e}")
                tank['api_image'] = None     


        is_logged_in = is_user_logged_in()
        return render_template('image.html', tanks_by_nation = tanks_by_nation, nation_order = nation_order,
                                is_logged_in = is_logged_in)

    else:
        return "Error while connecting to Data Base"

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = escape(request.form['username'])
        password = hashlib.sha256((escape(request.form['password'])).encode('utf-8')).hexdigest()
        conn = get_conn_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            if user:
                access_token = create_access_token(identity=username)
                response = make_response(redirect(url_for('data_tracker')))

                next_page = session.pop('next', None)
                if next_page:
                    response = make_response(redirect(next_page))

                response.set_cookie('access_token_cookie', access_token, httponly=True, secure=app.config['JWT_COOKIE_SECURE'])
                return response
            
            else:
                error = "Invalid User or Password"

    return render_template('login.html', error=error)

@app.route('/logout')
@jwt_required()
def logout():
    response = make_response(redirect(url_for('index')))
    response.delete_cookie('access_token_cookie')
    return response

@app.route('/data-tracker/add_moe', methods=['GET', 'POST'])
@jwt_required()
def add_moe():
    current_user = get_jwt_identity()
    conn = get_conn_connection()

    if conn:
        if request.method == 'POST':
            tank_name = request.form['tank_name']
            moe_number = int(request.form['moe_number'])
            date_obtained = request.form['date_obtained']
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO moes (tank_id, moe_number, date_obtained)
                SELECT id, %s, %s FROM tanks WHERE name = %s
            """, (moe_number, date_obtained, tank_name))
            cursor.execute("""
                UPDATE tanks 
                SET moe = GREATEST(moe, %s) 
                WHERE name = %s
            """, (moe_number, tank_name))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('data_tracker'))
        
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM tanks WHERE tier >= 5")
        tanks = fetch_all_as_dict(cursor)
        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()

        return render_template('add_moe.html', tanks = tanks, is_logged_in = is_logged_in)
    else:
        return "Error while connecting to Data Base"

@app.route('/data-tracker/add_tank', methods=['GET', 'POST'])
@jwt_required()
def add_tank():
    current_user = get_jwt_identity()
    conn = get_conn_connection()

    if conn:
        if request.method == 'POST':
            name = request.form['name']
            full_name = request.form['full_name']
            tier = int(request.form['tier'])
            tank_class = request.form['class']
            tank_type = request.form['type']
            nation_code = request.form['nation_code']

            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO tanks (name, full_name, tier, class, type, moe, mastery, nation_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (name, full_name, tier, tank_class, tank_type, 0, 0, nation_code))

            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('data_tracker'))
        
        cursor = conn.cursor()
        cursor.execute("SELECT code_nation, nom_nation FROM nations")
        nations = cursor.fetchall()
        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()
        
        return render_template('add_tank.html', nations=nations, is_logged_in=is_logged_in)
    
    else:
        return "Error while connecting to Data Base"

@app.route('/data-tracker/charts')
def charts():
    conn = get_conn_connection()
    if not conn:
        return "Error while connecting to the Data Base"

    cursor = conn.cursor(dictionary=True)
    class_order = ['Heavy Tank', 'Medium Tank', 'Tank Destroyer', 'Light Tank', 'Artillery']

    cursor.execute("""
        SELECT class,
               SUM(CASE WHEN moe = 1 THEN 1 ELSE 0 END) AS moe_1,
               SUM(CASE WHEN moe = 2 THEN 1 ELSE 0 END) AS moe_2,
               SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3,
               COUNT(*) AS total_tanks
        FROM tanks WHERE tier >= 5 GROUP BY class
    """)
    moe_by_class = cursor.fetchall()

    cursor.execute("SELECT moe_number, date_obtained FROM moes ORDER BY date_obtained")
    moe_progression = cursor.fetchall()

    cursor.execute("""
        SELECT class, COUNT(*) AS total_tanks, SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3_count
        FROM tanks WHERE tier >= 5 GROUP BY class
    """)
    class_completion = cursor.fetchall()

    cursor.execute("""
        SELECT tier, COUNT(*) AS total_tanks, SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3_count
        FROM tanks WHERE tier >= 5 GROUP BY tier
    """)
    tier_completion = cursor.fetchall()

    cursor.execute("""
        SELECT class, COUNT(*) AS total_tanks, SUM(CASE WHEN mastery = 4 THEN 1 ELSE 0 END) AS aces_count
        FROM tanks GROUP BY class
    """)
    aces_class_completion = cursor.fetchall()

    cursor.execute("""
        SELECT tier, COUNT(*) AS total_tanks, SUM(CASE WHEN mastery = 4 THEN 1 ELSE 0 END) AS aces_count
        FROM tanks GROUP BY tier
    """)
    aces_tier_completion = cursor.fetchall()

    cursor.close()
    conn.close()

    classes, moe_1, moe_2, moe_3 = [], [], [], []
    for c in class_order:
        row = next((r for r in moe_by_class if r['class'] == c), None)
        classes.append(c)
        moe_1.append(row['moe_1'] if row else 0)
        moe_2.append(row['moe_2'] if row else 0)
        moe_3.append(row['moe_3'] if row else 0)

    bar_chart = go.Figure()
    config_bars = [
        (moe_1, '1e MOE', '#ED7D31'),
        (moe_2, '2e MOE', '#F4BA04'),
        (moe_3, '3e MOE', '#6FAA46')
    ]
    for data, name, color in config_bars:
        bar_chart.add_trace(go.Bar(
            x=classes, y=data, name=name, marker_color=color,
            text=data, textposition='outside'
        ))

    moe_monthly = {1: defaultdict(int), 2: defaultdict(int), 3: defaultdict(int)}
    for row in moe_progression:
        month = row['date_obtained'].strftime('%Y-%m')
        moe_monthly[row['moe_number']][month] += 1

    months = sorted(set().union(*[m.keys() for m in moe_monthly.values()]))
    cumulative = {1: [], 2: [], 3: []}
    totals = {1: 0, 2: 0, 3: 0}

    for m in months:
        for i in [1, 2, 3]:
            totals[i] += moe_monthly[i].get(m, 0)
            cumulative[i].append(totals[i])

    stacked_chart = go.Figure()
    colors = {1: '#ED7D31', 2: '#F4BA04', 3: '#6FAA46'}

    for i in [1, 2, 3]:
        stacked_chart.add_trace(go.Scatter(
            x=months, y=cumulative[i], mode='lines+markers',
            name=f'{i}e MOE', line=dict(color=colors[i], width=2)
        ))

    if months:
        start_year = int(months[0][:4])
        end_year = int(months[-1][:4])
        for year in range(start_year, end_year + 1):
            january = f'{year}-01'
            if january in months:
                idx = months.index(january)
                for i in [1, 2, 3]:
                    stacked_chart.add_annotation(
                        x=january, y=cumulative[i][idx],
                        text=str(cumulative[i][idx]),
                        showarrow=True, arrowhead=2, ax=0, ay=-30,
                        font=dict(color=colors[i])
                    )

    def compute_totals(rows, key):
        total_tanks = total_done = 0
        for r in rows:
            r['completion_rate'] = (r[key] / r['total_tanks'] * 100) if r['total_tanks'] else 0
            total_tanks += r['total_tanks']
            total_done += r[key]
        return total_tanks, total_done

    t_cl_tanks, t_cl_moe3 = compute_totals(class_completion, 'moe_3_count')
    t_tr_tanks, t_tr_moe3 = compute_totals(tier_completion, 'moe_3_count')
    t_ace_cl_tanks, t_ace_cl = compute_totals(aces_class_completion, 'aces_count')
    t_ace_tr_tanks, t_ace_tr = compute_totals(aces_tier_completion, 'aces_count')

    return render_template(
        'charts.html',
        bar_chart_div=bar_chart.to_html(full_html=False),
        stacked_chart_div=stacked_chart.to_html(full_html=False),
        class_completion=class_completion,
        tier_completion=tier_completion,
        total_class_tanks=t_cl_tanks,
        total_class_moe_3=t_cl_moe3,
        total_tier_tanks=t_tr_tanks,
        total_tier_moe_3=t_tr_moe3,
        aces_class_completion=aces_class_completion,
        aces_tier_completion=aces_tier_completion,
        total_aces_class_tanks=t_ace_cl_tanks,
        total_aces_class=t_ace_cl,
        total_aces_tier_tanks=t_ace_tr_tanks,
        total_aces_tier=t_ace_tr,
        is_logged_in=is_user_logged_in()
    )

@app.route('/data-tracker/tank/<int:tank_id>/')
def show_tank(tank_id):
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                t.*, 
                n.nom_nation AS nation 
            FROM tanks t 
            JOIN nations n ON t.nation_code = n.code_nation
            WHERE t.id = %s
        """, (tank_id,))
        tank = cursor.fetchone()
        
        if tank:
            # --- NEW API LOGIC ---
            # 1. Use your wg_id to get the tag/image from Wargaming
            # Replace 'YOUR_APP_ID' with your Wargaming Developer App ID
            app_id = os.getenv('app_id') 
            api_url = f"https://api.worldoftanks.eu/wot/encyclopedia/vehicles/?application_id={app_id}&tank_id={tank['wg_id']}&fields=images.big_icon"
        
            try:
                response = requests.get(api_url).json()
                if response['status'] == 'ok' and str(tank['wg_id']) in response['data']:
                    # Get the URL directly from the API response
                    tank['api_image'] = response['data'][str(tank['wg_id'])]['images']['big_icon']
                else:
                    tank['api_image'] = None
            except Exception as e:
                print(f"API Error: {e}")
                tank['api_image'] = None      

        cursor.execute("""
            SELECT moe_number, date_obtained 
            FROM moes 
            WHERE tank_id = %s
            ORDER BY moe_number
        """, (tank_id,))
        rows = cursor.fetchall()

        moes = {}
        for row in rows:
            moes[row['moe_number']] = row['date_obtained'].strftime('%d/%m/%Y')

        cursor.close()
        conn.close()

        if tank:
            is_logged_in = is_user_logged_in() 
            return render_template('tank.html', tank=tank, moes=moes, is_logged_in=is_logged_in)
        else:
            return "Tank not found", 404
    
    else:
        return "Error while connecting to the Data Base"

@app.route('/data-tracker/tank/<int:tank_id>/edit', methods=['GET', 'POST'])
@jwt_required()
def edit_tank(tank_id):
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        if request.method == 'POST':
            name = request.form['name']
            full_name = request.form['full_name']
            tank_class = request.form['class']
            tier = int(request.form['tier'])
            tank_type = request.form['type']
            ace = request.form['mastery']

            cursor.execute("""
                UPDATE tanks 
                SET name = %s, full_name = %s, class = %s, tier = %s, type = %s, mastery = %s
                WHERE id = %s
            """, (name, full_name, tank_class, tier, tank_type, ace, tank_id))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('show_tank', tank_id=tank_id))
        else:
            cursor.execute("""
                SELECT 
                t.*, 
                n.nom_nation AS nation 
                FROM tanks t 
                JOIN nations n ON t.nation_code = n.code_nation
                WHERE t.id = %s
                """, (tank_id,))

            tank = cursor.fetchone()
            cursor.close()
            conn.close()

            if tank:
                is_logged_in = is_user_logged_in()
                
                return render_template('edit_tank.html', tank = tank, is_logged_in = is_logged_in)
            else:
                return "Tank not found", 404
    else:
        return "Error while connecting to Data Base"
    
@app.errorhandler(NoAuthorizationError)
def handle_auth_error(e):
    return redirect(url_for('login'))

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_data):
    return redirect(url_for('login'))

@app.errorhandler(NoAuthorizationError)
def handle_auth_error(e):
    session['next'] = request.url
    return redirect(url_for('login'))

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_data):
    session['next'] = request.url
    return redirect(url_for('login'))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5005)
