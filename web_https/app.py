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
from collections import defaultdict, OrderedDict
from dotenv import load_dotenv
from pathlib import Path
import psutil
import subprocess
import time
import threading
import plotly.graph_objs as go
import hashlib
import os
import requests
import json
import re

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

def get_all_wg_tanks():
    app_id = os.getenv("app_id")

    api_url = (
        "https://api.worldoftanks.eu/wot/encyclopedia/vehicles/"
        f"?application_id={app_id}"
        "&fields="
        "tank_id,"
        "name,"
        "short_name,"
        "tier,"
        "type,"
        "nation,"
        "is_premium,"
        "price_gold,"
        "price_credit,"
        "images.contour_icon"
    )

    response = requests.get(api_url, timeout=15).json()

    if response.get("status") != "ok":
        raise Exception("WG API error")

    return response["data"]

CACHE_PATH = Path("static/cache/wg_vehicles.json")
CACHE_TTL = 24 * 3600

def get_all_wg_tanks_cached():
    now = time.time()

    if CACHE_PATH.exists():
        age = now - CACHE_PATH.stat().st_mtime
        if age < CACHE_TTL:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)

    data = get_all_wg_tanks()

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)

    return data

def get_tank_type(tank):
    if tank.get("is_premium"):
        return "Premium"

    price_gold = tank.get("price_gold", 0)
    price_credit = tank.get("price_credit", 0)

    if price_gold == 0 and price_credit == 0:
        return "Reward"

    return "Tech Tree"

def get_banned_tanks():
    path = Path("static/config/banned_tanks.json")
    if not path.exists():
        return set()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return set(data.get("banned_wg_ids", []))

TANK_IMAGE_CACHE_DIR = Path("static/cache/wg_tank_images")
TANK_IMAGE_CACHE_TTL = 30 * 24 * 3600

def get_wg_tank_image_cached(wg_id):
    cache_file = TANK_IMAGE_CACHE_DIR / f"{wg_id}.json"
    now = time.time()

    if cache_file.exists():
        age = now - cache_file.stat().st_mtime
        if age < TANK_IMAGE_CACHE_TTL:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("big_icon")

    app_id = os.getenv("app_id")
    api_url = (
        "https://api.worldoftanks.eu/wot/encyclopedia/vehicles/"
        f"?application_id={app_id}"
        f"&tank_id={wg_id}"
        "&fields=images.big_icon"
    )

    try:
        response = requests.get(api_url, timeout=10).json()
        if response.get("status") == "ok" and str(wg_id) in response.get("data", {}):
            big_icon = response["data"][str(wg_id)]["images"]["big_icon"]
        else:
            big_icon = None
    except Exception as e:
        print(f"WG API Error ({wg_id}): {e}")
        big_icon = None

    TANK_IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"big_icon": big_icon}, f)

    return big_icon

def get_wg_tank_contour_icon_cached(wg_id):
    cache_dir = Path("static/cache/wg_tank_contour_icon")
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_file = cache_dir / f"{wg_id}.json"
    ttl = 30 * 24 * 3600
    now = time.time()

    if cache_file.exists() and now - cache_file.stat().st_mtime < ttl:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f).get("contour_icon")

    app_id = os.getenv("app_id")
    api_url = (
        "https://api.worldoftanks.eu/wot/encyclopedia/vehicles/"
        f"?application_id={app_id}"
        f"&tank_id={wg_id}"
        "&fields=images.contour_icon"
    )

    contour_icon = None
    try:
        r = requests.get(api_url, timeout=10).json()
        if r.get("status") == "ok" and str(wg_id) in r.get("data", {}):
            contour_icon = r["data"][str(wg_id)]["images"]["contour_icon"]
    except Exception as e:
        print(f"WG API error (contour_icon): {e}")

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"contour_icon": contour_icon}, f)

    return contour_icon

app.jinja_env.globals.update(
    get_wg_tank_contour_icon_cached=get_wg_tank_contour_icon_cached,
    get_wg_tank_image_cached=get_wg_tank_image_cached
)

def slugify(text):
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")

GOLD_TO_EUR_RATIO = 99.99 / 30500

def gold_to_eur(gold):
    if gold is None:
        return None
    eur = float(gold) * GOLD_TO_EUR_RATIO
    if eur < 0.01:
        return round(eur, 6)
    return round(eur, 2)

CATEGORY_ORDER = [
    "Exterior",
    "Currency",
    "Fragments",
    "Crew",
    "Reserve",
    "Equipment",
    "Miscellaneous"
]
    
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
        return render_template('data_tracker/data_tracker.html', tanks_by_nation = tanks_by_nation, nation_order = nation_order, is_logged_in = is_logged_in)
    
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

        return render_template('data_tracker/add_moe.html', tanks = tanks, is_logged_in = is_logged_in)
    else:
        return "Error while connecting to Data Base"

@app.route("/data-tracker/add_tank", methods=["GET", "POST"])
@jwt_required()
def add_tank():
    conn = get_conn_connection()
    if not conn:
        return "Error while connecting to Data Base", 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT wg_id FROM tanks WHERE wg_id IS NOT NULL")
    existing_wg_ids = {row["wg_id"] for row in cursor.fetchall()}

    banned_wg_ids = get_banned_tanks()
    
    WG_CLASS_MAP = {
    "mediumTank": "Medium Tank",
    "heavyTank": "Heavy Tank",
    "lightTank": "Light Tank",
    "AT-SPG": "Tank Destroyer",
    "SPG": "Artillery"
    }

    WG_NATION_MAP = {
    "china": "CH",
    "czech": "CZ",
    "france": "FR",
    "germany": "GER",
    "italy": "IT",
    "japan": "JP",
    "poland": "PL",
    "sweden": "SW",
    "uk": "UK",
    "usa": "US",
    "ussr": "USSR"
    }

    try:
        wg_tanks = get_all_wg_tanks_cached()
    except Exception:
        cursor.close()
        conn.close()
        return f"WG API Error", 500

    tanks_to_display = []

    for wg_id_str, tank in wg_tanks.items():
        wg_id = int(wg_id_str)

        if wg_id in existing_wg_ids:
            continue

        if wg_id in banned_wg_ids:
            continue

        tank_class = WG_CLASS_MAP.get(tank.get("type"))
        nation_code = WG_NATION_MAP.get(tank.get("nation"))

        if not tank_class or not nation_code:
            continue

        tanks_to_display.append({
            "wg_id": wg_id,
            "name": tank.get("short_name"),
            "full_name": tank.get("name"),
            "tier": tank.get("tier"),
            "class": tank_class,
            "type": get_tank_type(tank),
            "nation_code": nation_code,
            "icon": tank["images"]["contour_icon"]
        })

    if request.method == "POST":
        selected_ids = set(map(int, request.form.getlist("tank_ids")))

        insert_sql = """
            INSERT INTO tanks
            (name, full_name, tier, class, type, moe, mastery, nation_code, wg_id)
            VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s)
        """

        for tank in tanks_to_display:
            if tank["wg_id"] in selected_ids:
                cursor.execute(insert_sql, (
                    tank["name"],
                    tank["full_name"],
                    tank["tier"],
                    tank["class"],
                    tank["type"],
                    tank["nation_code"],
                    tank["wg_id"]
                ))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("data_tracker"))

    cursor.close()
    conn.close()

    return render_template(
        "data_tracker/add_tank.html",
        tanks=tanks_to_display,
        is_logged_in=is_user_logged_in()
    )

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
        'data_tracker/charts.html',
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
            tank['api_image'] = get_wg_tank_image_cached(tank['wg_id']) 

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
            return render_template('data_tracker/tank.html', tank=tank, moes=moes, is_logged_in=is_logged_in)
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
            txt = request.form['txt']

            cursor.execute("""
                UPDATE tanks 
                SET name = %s, full_name = %s, class = %s, tier = %s, type = %s, mastery = %s, txt = %s
                WHERE id = %s
            """, (name, full_name, tank_class, tier, tank_type, ace, txt, tank_id))
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
                
                return render_template('data_tracker/edit_tank.html', tank = tank, is_logged_in = is_logged_in)
            else:
                return "Tank not found", 404
    else:
        return "Error while connecting to Data Base"
    
@app.route('/data-tracker/image')
@jwt_required()
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
            tank['api_image'] = get_wg_tank_image_cached(tank['wg_id']) 

        is_logged_in = is_user_logged_in()
        return render_template('data_tracker/image.html', tanks_by_nation = tanks_by_nation, nation_order = nation_order,
                                is_logged_in = is_logged_in)

    else:
        return "Error while connecting to Data Base"
    
@app.route("/data-tracker/battle-pass/")
def battle_pass_list():
    conn = get_conn_connection()
    
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
        SELECT
            bp.id,
            bp.name,
            bp.slug,
            bp.start_date,
            bp.end_date,
            GROUP_CONCAT(t.name SEPARATOR ' & ') AS tank_names
        FROM battle_pass bp
        LEFT JOIN battle_pass_tanks bpt ON bp.id = bpt.bp_id
        LEFT JOIN tanks t ON bpt.tank_wg_id = t.wg_id
        GROUP BY bp.id
        ORDER BY bp.start_date ASC
        """)

        bps = cursor.fetchall()
        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()
        return render_template("battle_pass/list.html", battle_passes=bps, is_logged_in = is_logged_in)
    
    else:
        return "Error while connecting to Data Base"
    
@app.route("/data-tracker/battle-pass/<string:slug>/")
def battle_pass_detail(slug):
    conn = get_conn_connection()
    
    if conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM battle_pass WHERE slug=%s", (slug,))
        bp = cursor.fetchone()

        if not bp:
            return "Battle Pass not found", 404

        cursor.execute("""
            SELECT t.name, t.wg_id
            FROM battle_pass_tanks bpt
            JOIN tanks t ON bpt.tank_wg_id = t.wg_id
            WHERE bpt.bp_id = %s
            ORDER BY t.name
        """, (bp["id"],))
        tanks = cursor.fetchall()

        cursor.execute("""
            SELECT d.category, d.name, d.gold_price, o.quantity, o.reward
            FROM bp_objects o
            JOIN bp_data d ON o.data_id = d.id
            WHERE o.bp_id = %s
            ORDER BY o.reward, d.category
        """, (bp["id"],))
        objects = cursor.fetchall()

        # Calculs
        total_days = (bp["end_date"] - bp["start_date"]).days + 1
        total_points = bp["chapters"] * bp["stages_per_chapter"] * bp["points_per_stage"]
        points_per_day = round(total_points / total_days, 2)

        for obj in objects:
            obj["eur_price"] = gold_to_eur(obj["gold_price"])
        
        total_base_gold = 0
        total_improved_gold = 0

        for obj in objects:
            if obj["gold_price"] and obj["quantity"]:
                total = obj["gold_price"] * obj["quantity"]
                if obj["reward"] == 0:
                    total_base_gold += total
                else:
                    total_improved_gold += total

        total_base_eur = gold_to_eur(total_base_gold)
        total_improved_eur = gold_to_eur(total_improved_gold)


        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()
        return render_template(
            "battle_pass/bp.html",
            bp=bp,
            tanks=tanks,
            objects=objects,
            total_days=total_days,
            total_points=total_points,
            points_per_day=points_per_day,
            is_logged_in = is_logged_in,
            total_base_eur=total_base_eur,
            total_base_gold=total_base_gold,
            total_improved_eur=total_improved_eur,
            total_improved_gold=total_improved_gold
        )
        
    else:
        return "Error while connecting to Data Base"
    
@app.route("/data-tracker/battle-pass/data/")
def bp_data_list():
    conn = get_conn_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM bp_data ORDER BY category, name")
        data = cursor.fetchall()

        for d in data:
            d["eur_price"] = gold_to_eur(d["gold_price"])

        # Grouper par category
        data_by_category = defaultdict(list)
        for d in data:
            data_by_category[d["category"]].append(d)

        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()
        return render_template(
            "battle_pass/data.html",
            data_by_category=data_by_category,
            is_logged_in=is_logged_in
        )
    else:
        return "Error while connecting to Data Base"
    
@app.route("/data-tracker/battle-pass/add-data/", methods=["GET", "POST"])
@jwt_required()
def add_bp_data():

    conn = get_conn_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)

        if request.method == "POST":
            category = request.form["category"]
            name = request.form["name"]
            gold_price = request.form.get("gold_price")

            # Gestion des valeurs vides
            if gold_price == "" or gold_price is None:
                gold_price = None   # MySQL prendra NULL
            else:
                gold_price = float(gold_price)
    
            cursor.execute("""
                INSERT INTO bp_data (category, name, gold_price)
                VALUES (%s, %s, %s)
            """, (category,name,gold_price))
            
            conn.commit()
            return redirect(url_for("bp_data_list"))

        cursor.close()
        conn.close()

        is_logged_in = is_user_logged_in()
        return render_template("battle_pass/add_data.html", is_logged_in=is_logged_in)
    else:
        return "Error while connecting to Data Base"
    
@app.route("/data-tracker/battle-pass/edit-data/<int:data_id>/", methods=["GET", "POST"])
@jwt_required()
def edit_bp_data(data_id):
    conn = get_conn_connection()
    if not conn:
        return "Error while connecting to Data Base"
    
    cursor = conn.cursor(dictionary=True)

    # GET: récupérer les infos actuelles
    if request.method == "GET":
        cursor.execute("SELECT * FROM bp_data WHERE id=%s", (data_id,))
        data_item = cursor.fetchone()
        cursor.close()
        conn.close()
        if not data_item:
            return "Data not found", 404
        
        is_logged_in = is_user_logged_in()
        return render_template("battle_pass/edit_data.html", data=data_item,  is_logged_in=is_logged_in)

    # POST: update
    name = request.form.get("name")
    category = request.form.get("category")
    gold_price = request.form.get("gold_price")
    if gold_price == "" or gold_price is None:
        gold_price = None
    else:
        gold_price = float(gold_price)

    cursor.execute("""
        UPDATE bp_data
        SET name=%s, category=%s, gold_price=%s
        WHERE id=%s
    """, (name, category, gold_price, data_id))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("bp_data_list"))

@app.route("/data-tracker/battle-pass/add-bp/", methods=["GET", "POST"])
@jwt_required()
def add_battle_pass():
    conn = get_conn_connection()
    if not conn:
        return "Error while connecting to Data Base"

    cursor = conn.cursor(dictionary=True)

    # Tanks T10 Tech Tree uniquement
    cursor.execute("""
        SELECT name, wg_id, nation_code
        FROM tanks
        WHERE tier = 10 AND type = 'Tech Tree'
        ORDER BY nation_code, name
    """)
    tanks = cursor.fetchall()

    # Objets BP
    cursor.execute("""
        SELECT *
        FROM bp_data
        ORDER BY category, name
    """)
    bp_data = cursor.fetchall()

    if request.method == "POST":
        name = request.form["name"]
        slug = slugify(name)

        cursor.execute("""
            INSERT INTO battle_pass
            (name, slug, start_date, end_date, article_link,
             chapters, stages_per_chapter, points_per_stage)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            name,
            slug,
            request.form["start_date"],
            request.form["end_date"],
            request.form.get("article_link"),
            request.form["chapters"],
            request.form["stages_per_chapter"],
            request.form["points_per_stage"]
        ))

        bp_id = cursor.lastrowid

        # 🔹 Highlighted tanks
        for wg_id in request.form.getlist("tanks"):
            cursor.execute("""
                INSERT INTO battle_pass_tanks (bp_id, tank_wg_id)
                VALUES (%s, %s)
            """, (bp_id, wg_id))

        # 🔹 Rewards (base / improved)
        for obj in bp_data:
            for reward_type, reward_flag in [("base", 0), ("improved", 1)]:
                qty = request.form.get(f"{reward_type}_{obj['id']}")
                if qty and int(qty) > 0:
                    cursor.execute("""
                        INSERT INTO bp_objects (bp_id, data_id, quantity, reward)
                        VALUES (%s, %s, %s, %s)
                    """, (bp_id, obj["id"], int(qty), reward_flag))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("battle_pass_detail", slug=slug))

    cursor.close()
    conn.close()

    is_logged_in = is_user_logged_in()
    return render_template(
        "battle_pass/add_bp.html",
        tanks=tanks,
        bp_data=bp_data,
        is_logged_in=is_logged_in
    )

@app.route("/data-tracker/battle-pass/<string:slug>/edit/", methods=["GET", "POST"])
@jwt_required()
def edit_battle_pass(slug):
    conn = get_conn_connection()
    if not conn:
        return "Error while connecting to Data Base"
    
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM battle_pass WHERE slug=%s", (slug,))
    bp = cursor.fetchone()
    if not bp:
        cursor.close()
        conn.close()
        return "Battle Pass not found", 404

    cursor.execute("""
        SELECT name, wg_id, nation_code
        FROM tanks
        WHERE tier = 10 AND type = 'Tech Tree'
        ORDER BY nation_code, name
    """)
    tanks = cursor.fetchall()

    cursor.execute("SELECT tank_wg_id FROM battle_pass_tanks WHERE bp_id=%s", (bp["id"],))
    selected_tanks = {row["tank_wg_id"] for row in cursor.fetchall()}

    cursor.execute("SELECT * FROM bp_data ORDER BY category, name")
    bp_data = cursor.fetchall()

    cursor.execute("""
        SELECT data_id, quantity, reward
        FROM bp_objects
        WHERE bp_id=%s
    """, (bp["id"],))
    existing = {(o["data_id"], o["reward"]): o["quantity"] for o in cursor.fetchall()}

    if request.method == "POST":
        cursor.execute("""
            UPDATE battle_pass
            SET name=%s, start_date=%s, end_date=%s,
                article_link=%s, chapters=%s,
                stages_per_chapter=%s, points_per_stage=%s
            WHERE id=%s
        """, (
            request.form["name"],
            request.form["start_date"],
            request.form["end_date"],
            request.form.get("article_link"),
            request.form["chapters"],
            request.form["stages_per_chapter"],
            request.form["points_per_stage"],
            bp["id"]
        ))

        cursor.execute("DELETE FROM battle_pass_tanks WHERE bp_id=%s", (bp["id"],))
        for wg_id in request.form.getlist("tanks"):
            cursor.execute("""
                INSERT INTO battle_pass_tanks (bp_id, tank_wg_id)
                VALUES (%s, %s)
            """, (bp["id"], wg_id))

        cursor.execute("DELETE FROM bp_objects WHERE bp_id=%s", (bp["id"],))
        for obj in bp_data:
            for reward_type, reward_flag in [("base", 0), ("improved", 1)]:
                qty = request.form.get(f"{reward_type}_{obj['id']}")
                if qty and int(qty) > 0:
                    cursor.execute("""
                        INSERT INTO bp_objects (bp_id, data_id, quantity, reward)
                        VALUES (%s, %s, %s, %s)
                    """, (bp["id"], obj["id"], int(qty), reward_flag))

        conn.commit()
        return redirect(url_for("battle_pass_detail", slug=slug))

    cursor.close()
    conn.close()
    
    is_logged_in = is_user_logged_in()
    return render_template("battle_pass/edit_bp.html", bp=bp, bp_data=bp_data, existing=existing, is_logged_in=is_logged_in, tanks=tanks)

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
