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

@app.route('/olga')
@jwt_required()
def olga():
    current_user = get_jwt_identity()
    
    is_logged_in = is_user_logged_in() 
    
    return render_template('olga.html', is_logged_in = is_logged_in)

@app.route('/olga-crea')
@jwt_required()
def olga_crea():
    current_user = get_jwt_identity()
    
    is_logged_in = is_user_logged_in() 
    
    return render_template('olga_crea.html', is_logged_in = is_logged_in)

@app.route('/data-tracker')
def data_tracker():
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
               t.id, 
               t.name,
               t.class, 
               t.tier, 
               t.type,
               t.mastery,
               t.moe,
               t.nation_code,  
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
        return render_template('data_tracker.html', tanks_by_nation = tanks_by_nation, nation_order = nation_order,
                                is_logged_in = is_logged_in)
    
    else:
        return "Error while connecting to Data Base"

@app.route('/image')
def image():
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
               t.id,
               t.name,
               t.class,
               t.tier,
               t.type,
               t.mastery,
               t.moe,
               t.nation_code,
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

@app.route('/add_moe', methods=['GET', 'POST'])
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

@app.route('/add_tank', methods=['GET', 'POST'])
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

@app.route('/moe_charts')
def moe_charts():
    conn = get_conn_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)

        class_order = ['Heavy Tank', 'Medium Tank', 'Tank Destroyer', 'Light Tank', 'Artillery']

        cursor.execute("""
            SELECT class,
                   SUM(CASE WHEN moe = 1 THEN 1 ELSE 0 END) AS moe_1,
                   SUM(CASE WHEN moe = 2 THEN 1 ELSE 0 END) AS moe_2,
                   SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3,
                   COUNT(*) AS total_tanks
            FROM tanks
            WHERE tier >= 5
            GROUP BY class
        """)
        moe_by_class = cursor.fetchall()

        cursor.execute("""
            SELECT moe_number, date_obtained
            FROM moes
            ORDER BY date_obtained
        """)
        moe_progression = cursor.fetchall()

        cursor.execute("""
            SELECT class,
                   COUNT(*) AS total_tanks,
                   SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3_count
            FROM tanks
            WHERE tier >= 5
            GROUP BY class
        """)
        class_completion = cursor.fetchall()

        cursor.execute("""
            SELECT tier,
                   COUNT(*) AS total_tanks,
                   SUM(CASE WHEN moe = 3 THEN 1 ELSE 0 END) AS moe_3_count
            FROM tanks
            WHERE tier >= 5
            GROUP BY tier
        """)
        tier_completion = cursor.fetchall()

        cursor.close()
        conn.close()

        classes = []
        moe_1_counts = []
        moe_2_counts = []
        moe_3_counts = []
        for class_type in class_order:
            found = False
            for row in moe_by_class:
                if row['class'] == class_type:
                    classes.append(row['class'])
                    moe_1_counts.append(row['moe_1'])
                    moe_2_counts.append(row['moe_2'])
                    moe_3_counts.append(row['moe_3'])
                    found = True
                    break
            if not found:
                classes.append(class_type)
                moe_1_counts.append(0)
                moe_2_counts.append(0)
                moe_3_counts.append(0)

        moe_1_monthly = defaultdict(int)
        moe_2_monthly = defaultdict(int)
        moe_3_monthly = defaultdict(int)

        for row in moe_progression:
            date = row['date_obtained']
            month_year = date.strftime('%Y-%m')
            if row['moe_number'] == 1:
                moe_1_monthly[month_year] += 1
            elif row['moe_number'] == 2:
                moe_2_monthly[month_year] += 1
            elif row['moe_number'] == 3:
                moe_3_monthly[month_year] += 1

        all_months = set(moe_1_monthly.keys()) | set(moe_2_monthly.keys()) | set(moe_3_monthly.keys())
        sorted_months = sorted(all_months)

        cumulative_moe_1 = []
        cumulative_moe_2 = []
        cumulative_moe_3 = []
        total_moe_1 = total_moe_2 = total_moe_3 = 0

        for month in sorted_months:
            total_moe_1 += moe_1_monthly.get(month, 0)
            total_moe_2 += moe_2_monthly.get(month, 0)
            total_moe_3 += moe_3_monthly.get(month, 0)
            cumulative_moe_1.append(total_moe_1)
            cumulative_moe_2.append(total_moe_2)
            cumulative_moe_3.append(total_moe_3)

        bar_chart = go.Figure()
        bar_chart.add_trace(go.Bar(
            x=classes,
            y=moe_1_counts,
            name='1e MOE',
            marker_color='#ED7D31',
            text=moe_1_counts,
            textposition='outside'
        ))
        bar_chart.add_trace(go.Bar(
            x=classes,
            y=moe_2_counts,
            name='2e MOE',
            marker_color='#F4BA04',
            text=moe_2_counts,
            textposition='outside'
        ))
        bar_chart.add_trace(go.Bar(
            x=classes,
            y=moe_3_counts,
            name='3e MOE',
            marker_color='#6FAA46',
            text=moe_3_counts,
            textposition='outside'
        ))
        bar_chart.update_layout(
        )

        stacked_chart = go.Figure()

        stacked_chart.add_trace(go.Scatter(
            x=sorted_months,
            y=cumulative_moe_1,
            mode='lines+markers',
            name="1e MOE",
            line=dict(color='#ED7D31', width=2)
        ))

        stacked_chart.add_trace(go.Scatter(
            x=sorted_months,
            y=cumulative_moe_2,
            mode='lines+markers',
            name="2e MOE",
            line=dict(color='#F4BA04', width=2)
        ))

        stacked_chart.add_trace(go.Scatter(
            x=sorted_months,
            y=cumulative_moe_3,
            mode='lines+markers',
            name="3e MOE",
            line=dict(color='#6FAA46', width=2)
        ))

        start_year = int(sorted_months[0][:4])
        end_year = int(sorted_months[-1][:4])
        for year in range(start_year, end_year + 1):
            january = f'{year}-01'
            if january in sorted_months:
                idx = sorted_months.index(january)
                stacked_chart.add_annotation(
                    x=january,
                    y=cumulative_moe_1[idx],
                    text=str(cumulative_moe_1[idx]),
                    showarrow=True,
                    arrowhead=2,
                    ax=0,
                    ay=-30,
                    font=dict(color='#ED7D31')
                )
                stacked_chart.add_annotation(
                    x=january,
                    y=cumulative_moe_2[idx],
                    text=str(cumulative_moe_2[idx]),
                    showarrow=True,
                    arrowhead=2,
                    ax=0,
                    ay=-30,
                    font=dict(color='#F4BA04')
                )
                stacked_chart.add_annotation(
                    x=january,
                    y=cumulative_moe_3[idx],
                    text=str(cumulative_moe_3[idx]),
                    showarrow=True,
                    arrowhead=2,
                    ax=0,
                    ay=-30,
                    font=dict(color='#6FAA46')
                )

        stacked_chart.update_layout(
            showlegend=True
        )

        bar_chart_div = bar_chart.to_html(full_html=False)
        stacked_chart_div = stacked_chart.to_html(full_html=False)

        total_class_tanks = 0
        total_class_moe_3 = 0
        for row in class_completion:
            row['completion_rate'] = (row['moe_3_count'] / row['total_tanks']) * 100 if row['total_tanks'] > 0 else 0
            total_class_tanks += row['total_tanks']
            total_class_moe_3 += row['moe_3_count']

        total_tier_tanks = 0
        total_tier_moe_3 = 0
        for row in tier_completion:
            row['completion_rate'] = (row['moe_3_count'] / row['total_tanks']) * 100 if row['total_tanks'] > 0 else 0
            total_tier_tanks += row['total_tanks']
            total_tier_moe_3 += row['moe_3_count']

        is_logged_in = is_user_logged_in() 
        return render_template('moe_charts.html',
            bar_chart_div=bar_chart_div,
            stacked_chart_div=stacked_chart_div,
            class_completion=class_completion,
            tier_completion=tier_completion,
            total_class_tanks=total_class_tanks,
            total_class_moe_3=total_class_moe_3,
            total_tier_tanks=total_tier_tanks,
            total_tier_moe_3=total_tier_moe_3,
            is_logged_in=is_logged_in)

    else:
        return "Error while connecting to the Data Base"

@app.route('/tank/<int:tank_id>')
def show_tank(tank_id):
    conn = get_conn_connection()

    if conn:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                t.id, 
                t.name,
                t.full_name, 
                t.class, 
                t.tier, 
                t.type, 
                t.moe,
                t.mastery,
                t.nation_code, 
                n.nom_nation AS nation 
            FROM tanks t 
            JOIN nations n ON t.nation_code = n.code_nation
            WHERE t.id = %s
        """, (tank_id,))
        tank = cursor.fetchone()

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

@app.route('/tank/<int:tank_id>/edit', methods=['GET', 'POST'])
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
                t.id, 
                t.name,
                t.full_name, 
                t.class, 
                t.tier, 
                t.type, 
                t.mastery,
                t.moe, 
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
