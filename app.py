
import csv
import hashlib
import io
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

import pdfplumber
import pymysql
from dotenv import load_dotenv
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for, send_file)
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from difflib import get_close_matches

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / '.env')
app = Flask(__name__, instance_path=str(BASE / 'instance'))
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
SECRET_PATH = Path(app.instance_path) / '.session_secret'
if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_hex(32), encoding='utf-8')
app.secret_key = os.getenv('SECRET_KEY') or SECRET_PATH.read_text(encoding='utf-8').strip()
app.config.update(
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    TEMPLATES_AUTO_RELOAD=True,
)
DRAFTS = Path(app.instance_path) / 'drafts'
ARCHIVE = Path(app.instance_path) / 'pdf_archive'
DRAFTS.mkdir(exist_ok=True)
ARCHIVE.mkdir(exist_ok=True)
FUEL_ORDER = ['RON 100', 'RON 97', 'RON 95', 'RON 91', 'DIESEL', 'DIESEL PLUS', 'KEROSENE']
BRANDS = ['PETRON', 'SHELL', 'CALTEX', 'PHOENIX', 'TOTAL', 'FLYING V', 'UNIOIL', 'SEAOIL', 'PTT', 'INDEPENDENT', 'OVERALL']
CITY_FIXES = {'Taguig Cty': 'Taguig City'}
ALERT_THRESHOLD = max(1, float(os.getenv('ALERT_THRESHOLD', '40')))
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
KNOWN_NCR_CITIES = ('Caloocan City','Las Piñas City','Makati City','Malabon City','Mandaluyong City','Manila City','Marikina City','Muntinlupa City','Navotas City','Parañaque City','Pasay City','Pasig City','Quezon City','San Juan City','Taguig City','Valenzuela City','Pateros')



def db():
    if 'db' not in g:
        g.db = pymysql.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', '3306')),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'gaswatch_db'),
            charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
            autocommit=True, connect_timeout=5,
        )
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop('db', None)
    if conn:
        conn.close()


def sql(query, params=(), one=False):
    with db().cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone() if one else cur.fetchall()


def change(query, params=()):
    with db().cursor() as cur:
        cur.execute(query, params)
        return cur.lastrowid


def ensure_admin_account():
    """Set the one supported admin account; keep legacy users for FK audit history.

    Accounts other than 'admin' are never permitted to log in. A fresh SQL import
    already contains this account; this function also fixes existing installations.
    """
    existing = sql('SELECT user_id, password, role FROM users WHERE username=%s', (ADMIN_USERNAME,), one=True)
    if existing:
        if existing['role'] != 'admin' or not check_password_hash(existing['password'], ADMIN_PASSWORD):
            change('UPDATE users SET password=%s, role=%s WHERE user_id=%s',
                   (generate_password_hash(ADMIN_PASSWORD), 'admin', existing['user_id']))
    else:
        change('INSERT INTO users (username,password,role) VALUES (%s,%s,%s)',
               (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD), 'admin'))


def current_user():
    if not session.get('user_id') or session.get('username') != ADMIN_USERNAME or session.get('role') != 'admin':
        return None
    return {'user_id': session['user_id'], 'username': session.get('username'), 'role': session.get('role')}


def login_required(admin=False):
    def deco(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not current_user():
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('login', next=request.path))
            if admin:
                role_row = sql('SELECT role FROM users WHERE user_id=%s', (session['user_id'],), one=True)
                if not role_row or role_row['role'] != 'admin':
                    abort(403)
                session['role'] = role_row['role']
            return view(*args, **kwargs)
        return wrapper
    return deco


@app.before_request
def csrf_protect():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        supplied = request.headers.get('X-CSRF-Token')
        if not supplied:
            supplied = (request.get_json(silent=True) or {}).get('csrf_token') if request.is_json else request.form.get('csrf_token')
        if not supplied or not secrets.compare_digest(str(supplied), str(session.get('_csrf', ''))):
            abort(400, 'Invalid form token. Refresh the page and try again.')


@app.context_processor
def inject_globals():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(24)
    return {'me': current_user(), 'csrf_token': session['_csrf'], 'current_year': date.today().year, 'alert_threshold': ALERT_THRESHOLD, 'ncr_cities': KNOWN_NCR_CITIES}


@app.template_filter('fuel_label')
def fuel_label(value):
    names = {'RON 91': 'Regular', 'RON 95': 'Premium',
             'DIESEL': 'Diesel', 'DIESEL PLUS': 'Diesel Plus', 'KEROSENE': 'Kerosene'}
    return names.get(str(value or '').upper(), value or '—')


@app.template_filter('peso')
def peso(value):
    try:
        return f'₱{Decimal(str(value)):,.2f}'
    except (TypeError, InvalidOperation):
        return '—'


@app.template_filter('fmtdate')
def fmtdate(value):
    if isinstance(value, (datetime, date)):
        return value.strftime('%b %d, %Y')
    return str(value or '—')


def number(value, allow_none=False):
    if allow_none and (value is None or str(value).strip() == ''):
        return None
    try:
        amount = Decimal(str(value).strip()).quantize(Decimal('.01'))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError('Enter a valid numeric price.')
    if amount < 0 or amount > Decimal('99999999.99'):
        raise ValueError('Prices must be nonnegative and within the allowed range.')
    return amount


def source_week_from_text(text):
    """Read the published DOE *week*, not the separate monitoring cutoff date."""
    m = re.search(r'week\s+of\s+(\w+\s+\d{1,2})\s*[-–]\s*(\w+\s+\d{1,2}),?\s*(20\d{2})', text, re.I)
    if not m:
        raise ValueError('Cannot find a monitoring week (start and end dates) in this PDF.')
    year = m.group(3)
    start = datetime.strptime(f'{m.group(1)}, {year}', '%B %d, %Y').date()
    end = datetime.strptime(f'{m.group(2)}, {year}', '%B %d, %Y').date()
    if end < start or (end - start).days > 30:
        raise ValueError('Invalid monitoring date range in the PDF.')
    return start, end


def parse_doe_pdf(pdf_bytes):
    """Parse the supplied text-based DOE NCR monitoring table by cell coordinates.

    Merged PDF brand cells cover seven product rows, so pdfplumber.extract_tables()
    alone would incorrectly assign one brand's values to the first fuel. We locate
    each numeric token using the actual product-row and brand-column boundaries.
    """
    rows = []
    notes = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages_text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        start, end = source_week_from_text(pages_text)
        if 'NCR' not in pages_text.upper() or 'LIQUID FUELS' not in pages_text.upper():
            raise ValueError('This importer requires a DOE NCR Liquid Fuels monitoring PDF.')
        for page_no, page in enumerate(pdf.pages, 1):
            tables = page.find_tables()
            candidates = [t for t in tables if len(t.columns) >= 14 and len(t.rows) >= 8]
            if not candidates:
                continue
            table = candidates[0]
            grid = table.extract()
            words = page.extract_words(x_tolerance=1, y_tolerance=2)
            col = table.columns
            # Ten brands + city-wide overall range, from source column coordinates.
            column_bounds = [(col[k].bbox[0], col[k + 1].bbox[0]) for k in range(2, 13)]
            city = ''
            for idx, table_row in enumerate(table.rows[1:], 1):
                raw_fuel = (grid[idx][1] or '').strip().upper().replace('\n', ' ')
                raw_fuel = re.sub(r'\s+', ' ', raw_fuel)
                if raw_fuel not in FUEL_ORDER:
                    continue
                if grid[idx][0]:
                    city = re.sub(r'\s+', ' ', grid[idx][0]).strip()
                    if 'MCuanlotioncluapna' in city:
                        # The provided 2026 PDF has *overlapping* old and new city
                        # text on page 2; the visible printed label is Muntinlupa.
                        city = 'Muntinlupa City'
                        notes.append('Page 2 contains overlapping city labels; Muntinlupa City was read from the visible table. Please verify in preview.')
                    city = CITY_FIXES.get(city, city)
                if not city:
                    continue
                cell = table_row.cells[1]
                if not cell:
                    continue
                y0, y1 = cell[1], cell[3]
                row_words = [w for w in words if y0 <= (w['top'] + w['bottom']) / 2 < y1]
                # Common price is a city/fuel value; attach only to OVERALL record.
                common_nums = [Decimal(w['text']) for w in row_words
                               if col[13].bbox[0] <= (w['x0'] + w['x1']) / 2 < col[13].bbox[2]
                               and re.fullmatch(r'\d{1,4}\.\d{2}', w['text'])]
                for brand_idx, (x0, x1) in enumerate(column_bounds):
                    found = [Decimal(w['text']) for w in row_words
                             if x0 <= (w['x0'] + w['x1']) / 2 < x1
                             and re.fullmatch(r'\d{1,4}\.\d{2}', w['text'])]
                    if not found:
                        continue
                    needs_review = len(found) > 2 or (len(found) > 1 and found[0] > found[1])
                    if needs_review:
                        notes.append(f'Check unusual figures: page {page_no}, {city}, {BRANDS[brand_idx]}, {raw_fuel}')
                    low, high = found[0], found[1] if len(found) > 1 else found[0]
                    rows.append({
                        'city': city, 'brand': BRANDS[brand_idx], 'fuel_name': raw_fuel,
                        'min_price': str(low), 'max_price': str(high),
                        'common_price': str(common_nums[0]) if brand_idx == 10 and common_nums else None,
                        'page': page_no, 'needs_review': needs_review or (page_no == 2 and city == 'Muntinlupa City'),
                    })
    if not rows:
        raise ValueError('No fuel-price rows found. Only text-based DOE NCR tables in the supplied layout are supported; scanned PDFs need a text layer.')
    return {'week_start': start.isoformat(), 'week_end': end.isoformat(), 'rows': rows, 'notes': sorted(set(notes))}


def add_preview_flags(rows, start):
    # Use latest recorded earlier week for comparisons. Values are historical city-brand ranges.
    earlier = sql('''SELECT r.city, r.brand, f.fuel_name, r.min_price, r.week_start
                     FROM regional_prices r JOIN fuel_types f ON f.fuel_id=r.fuel_id
                     WHERE r.week_start < %s ORDER BY r.week_start DESC LIMIT 15000''', (start,))
    previous = {}
    for row in earlier:
        previous.setdefault((row['city'], row['brand'], row['fuel_name']), row)
    known_cities = sorted(set(KNOWN_NCR_CITIES).union({k[0] for k in previous}))
    for row in rows:
        row['city_suggestions'] = get_close_matches(row['city'], known_cities, n=3, cutoff=.66)
        p = previous.get((row['city'], row['brand'], row['fuel_name']))
        row['previous'] = str(p['min_price']) if p else None
        row['change_pct'] = None
        if p and p['min_price'] > 0:
            row['change_pct'] = round(float((Decimal(row['min_price']) - p['min_price']) / p['min_price'] * 100), 1)
        row['needs_review'] = bool(row.get('needs_review')) or (row['change_pct'] is not None and abs(row['change_pct']) > ALERT_THRESHOLD)
    return rows


def latest_week():
    return sql('SELECT week_start,week_end,COUNT(*) AS rows_count FROM regional_prices GROUP BY week_start,week_end ORDER BY week_start DESC LIMIT 1', one=True)


def datasets():
    return sql('SELECT fuel_id,fuel_name FROM fuel_types ORDER BY FIELD(fuel_name, "RON 100","RON 97","RON 95","RON 91","DIESEL","DIESEL PLUS","KEROSENE"), fuel_name')


def dashboard_fuel_averages(week=None):
    '''Average fuel prices for the dashboard without inventing DOE station data.

    DOE mode averages only reported OVERALL city *common prices* in the latest
    imported week; missing (#N/A) values are excluded. Station mode averages
    one stored current price per active station/fuel. These are different
    samples, so the UI names the selected source explicitly.
    '''
    source = request.args.get('average_source', 'doe').strip().lower()
    if source not in ('doe', 'stations'):
        source = 'doe'
    city = request.args.get('average_city', '').strip()[:100]
    cities = sql('''SELECT DISTINCT city FROM (
                        SELECT city FROM regional_prices
                        UNION SELECT city FROM gas_stations WHERE status='active'
                     ) all_cities ORDER BY city''')
    valid_cities = {row['city'] for row in cities}
    if city not in valid_cities:
        city = ''
    if source == 'stations':
        where = ["s.status='active'"]
        args = []
        if city:
            where.append('s.city=%s')
            args.append(city)
        averages = sql('''SELECT p.fuel_id, ROUND(AVG(p.price_per_liter),2) AS average_price,
                                 COUNT(*) AS sample_count
                          FROM fuel_prices p
                          JOIN gas_stations s ON s.station_id=p.station_id
                          WHERE ''' + ' AND '.join(where) + '''
                          GROUP BY p.fuel_id''', args)
    else:
        where = ["r.brand='OVERALL'", 'r.common_price IS NOT NULL', 'r.week_start=%s']
        args = [week['week_start'] if week else date(1970, 1, 1)]
        if city:
            where.append('r.city=%s')
            args.append(city)
        averages = sql('''SELECT r.fuel_id, ROUND(AVG(r.common_price),2) AS average_price,
                                 COUNT(*) AS sample_count
                          FROM regional_prices r
                          WHERE ''' + ' AND '.join(where) + '''
                          GROUP BY r.fuel_id''', args)
    by_fuel = {row['fuel_id']: row for row in averages}
    cards = []
    for fuel in datasets():
        record = by_fuel.get(fuel['fuel_id'])
        cards.append({
            'fuel_name': fuel['fuel_name'],
            'average_price': record['average_price'] if record else None,
            'sample_count': int(record['sample_count']) if record else 0,
        })
    return {'source': source, 'city': city, 'cities': cities, 'cards': cards, 'week': week}


def city_price_overview(week):
    # Current city/brand/fuel source ranges, not individual station observations.
    cities = list(KNOWN_NCR_CITIES)
    city = request.args.get('map_city', 'Manila City').strip()
    if city not in cities:
        city = 'Manila City'
    fuel = request.args.get('map_fuel', 'RON 91').strip()
    if fuel not in FUEL_ORDER:
        fuel = 'RON 91'
    if not week:
        return {'cities': cities, 'entries': [], 'selected_city': city,
                'selected_fuel': fuel, 'availability': {}}
    entries = sql('''SELECT r.brand, r.min_price, r.max_price, r.common_price, f.fuel_name
                     FROM regional_prices r JOIN fuel_types f ON f.fuel_id=r.fuel_id
                     WHERE r.week_start=%s AND r.city=%s AND f.fuel_name=%s
                       AND r.brand <> 'OVERALL'
                     ORDER BY r.min_price, r.brand LIMIT 24''',
                  (week['week_start'], city, fuel))
    available = sql('''SELECT city, COUNT(*) AS records FROM regional_prices
                       WHERE week_start=%s AND brand <> 'OVERALL' GROUP BY city''',
                    (week['week_start'],))
    return {'cities': cities, 'entries': entries, 'selected_city': city,
            'selected_fuel': fuel, 'availability': {r['city']: r['records'] for r in available}}


@app.get('/')
def home():
    week = latest_week()
    return render_template('home.html', week=week,
                           fuel_averages=dashboard_fuel_averages(week))


@app.get('/cities')
def city_explorer():
    week = latest_week()
    return render_template('city_explorer.html', week=week,
                           city_overview=city_price_overview(week))


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = sql('SELECT * FROM users WHERE username=%s', (request.form.get('username','').strip(),), one=True)
        if (user and user['username'] == ADMIN_USERNAME and user['role'] == 'admin'
                and check_password_hash(user['password'], request.form.get('password',''))):
            session.clear()
            session.update(user_id=user['user_id'], username=user['username'], role=user['role'], _csrf=secrets.token_hex(24))
            flash('Welcome back.', 'success')
            dest = request.args.get('next', '')
            if (not dest.startswith('/') or dest.startswith('//') or dest.startswith('/register')
                    or dest.startswith('/admin/users')):
                dest = url_for('admin_dashboard')
            return redirect(dest)
        flash('Invalid username or password.', 'danger')
    return render_template('auth.html', active='login', mode='login')


@app.post('/logout')
def logout():
    session.clear()
    flash('You have logged out.', 'success')
    return redirect(url_for('home'))


@app.get('/stations')
def stations():
    return redirect(url_for('regional'))


@app.get('/prices')
def prices():
    return redirect(url_for('regional'))


@app.get('/regional')
def regional():
    week = latest_week()
    cities = sql('SELECT DISTINCT city FROM regional_prices ORDER BY city')
    city = request.args.get('city','').strip()
    brand = request.args.get('brand','').strip()
    fuel = request.args.get('fuel','').strip()
    where = ['r.week_start=%s']; args=[week['week_start'] if week else date(1970,1,1)]
    if city: where.append('r.city=%s');args.append(city)
    if brand: where.append('r.brand=%s');args.append(brand)
    if fuel: where.append('f.fuel_name=%s');args.append(fuel)
    rows = sql('''SELECT r.*,f.fuel_name,b.source_filename FROM regional_prices r
                  JOIN fuel_types f ON f.fuel_id=r.fuel_id
                  JOIN pdf_import_batches b ON b.import_id=r.import_id
                  WHERE '''+' AND '.join(where)+' ORDER BY r.city,f.fuel_name,r.min_price LIMIT 800',args)
    return render_template('regional.html', active='regional', rows=rows, week=week,cities=cities,
                           city=city,brand=brand,fuel=fuel,brands=BRANDS,fuels=datasets())


@app.get('/compare')
def compare():
    week = latest_week()
    mode = request.args.get('mode', 'regional').strip()
    if mode not in ('regional', 'stations'):
        mode = 'regional'
    cities = sql('''SELECT DISTINCT city FROM (
                     SELECT city FROM regional_prices UNION SELECT city FROM gas_stations WHERE status='active'
                     ) city_list ORDER BY city''')
    city = request.args.get('city','').strip()
    fuel = request.args.get('fuel','RON 95').strip()
    if mode == 'stations':
        where=["s.status='active'",'f.fuel_name=%s']; args=[fuel]
        if city: where.append('s.city=%s');args.append(city)
        rows=sql('''SELECT s.station_name,s.city,s.brand,p.price_per_liter,p.updated_at
                    FROM fuel_prices p JOIN gas_stations s ON s.station_id=p.station_id
                    JOIN fuel_types f ON f.fuel_id=p.fuel_id
                    WHERE '''+' AND '.join(where)+' ORDER BY p.price_per_liter,s.station_name LIMIT 250',args)
    else:
        where=['r.week_start=%s','f.fuel_name=%s',"r.brand!='OVERALL'"]
        args=[week['week_start'] if week else date(1970,1,1),fuel]
        if city: where.append('r.city=%s');args.append(city)
        rows=sql('''SELECT r.city,r.brand,f.fuel_name,r.min_price,r.max_price,r.week_start
                    FROM regional_prices r JOIN fuel_types f ON f.fuel_id=r.fuel_id
                    WHERE '''+' AND '.join(where)+' ORDER BY r.min_price,r.max_price LIMIT 250',args)
    return render_template('compare.html',active='compare',week=week,mode=mode,city=city,
                           fuel=fuel,cities=cities,fuels=datasets(),rows=rows)


@app.get('/history')
def history():
    city = request.args.get('city','').strip()
    brand = request.args.get('brand','OVERALL').strip()
    fuel = request.args.get('fuel','RON 95').strip()
    cities = sql('SELECT DISTINCT city FROM regional_prices ORDER BY city')
    where=['r.city=%s','r.brand=%s','f.fuel_name=%s']
    # Default to first listed monitored city if no city supplied.
    if not city and cities: city=cities[0]['city']
    rows = sql('''SELECT r.week_start,r.week_end,r.min_price,r.max_price,r.common_price
                  FROM regional_prices r JOIN fuel_types f ON r.fuel_id=f.fuel_id
                  WHERE '''+' AND '.join(where)+' ORDER BY r.week_start DESC LIMIT 100',(city,brand,fuel))
    rows.reverse()
    return render_template('history.html',active='history',rows=rows,
                           city=city,brand=brand,fuel=fuel,cities=cities,brands=BRANDS,fuels=datasets(),
                           chart_labels=[r['week_start'].isoformat() for r in rows],
                           chart_min=[float(r['min_price']) for r in rows],
                           chart_max=[float(r['max_price']) for r in rows])


def changes_for_alerts():
    # Infer alerts from existing historical/current tables; the supplied dictionary
    # intentionally does not define a notifications table.
    station = sql('''SELECT h.station_id,h.fuel_id,h.price_per_liter,h.recorded_at,
                     s.station_name,s.city,f.fuel_name FROM price_history h
                     JOIN gas_stations s ON s.station_id=h.station_id
                     JOIN fuel_types f ON f.fuel_id=h.fuel_id
                     ORDER BY h.recorded_at DESC,h.history_id DESC LIMIT 500''')
    seen={};compared=set();alerts=[]
    for r in station:
        key=(r['station_id'],r['fuel_id'])
        if key in seen and key not in compared:
            compared.add(key)
            old=seen[key]
            if r['price_per_liter']>0:
                pct=float((old['price_per_liter']-r['price_per_liter'])/r['price_per_liter']*100)
                if abs(pct)>ALERT_THRESHOLD:
                    alerts.append({'type':'Station','name':old['station_name'],'city':old['city'], 'fuel':old['fuel_name'],
                                   'previous':r['price_per_liter'],'current':old['price_per_liter'],'pct':pct,'when':old['recorded_at']})
        else: seen[key]=r
    # Compare most recent weekly imported regional rows with earlier same key.
    region = sql('''SELECT r.city,r.brand,r.fuel_id,r.min_price,r.week_start,f.fuel_name
                    FROM regional_prices r JOIN fuel_types f ON r.fuel_id=f.fuel_id
                    ORDER BY r.week_start DESC,r.regional_id DESC LIMIT 12000''')
    seen={};compared=set()
    for r in region:
        key=(r['city'],r['brand'],r['fuel_id'])
        if key in seen and key not in compared:
            compared.add(key)
            old=seen[key]
            if old['week_start'] != r['week_start'] and r['min_price']>0:
                pct=float((old['min_price']-r['min_price'])/r['min_price']*100)
                if abs(pct)>ALERT_THRESHOLD:
                    alerts.append({'type':'DOE regional','name':old['brand'],'city':old['city'],'fuel':old['fuel_name'],
                                   'previous':r['min_price'],'current':old['min_price'],'pct':pct,'when':old['week_start']})
            # Keep newest record to avoid repeats.
        else: seen[key]=r
    alerts.sort(key=lambda a: str(a['when']), reverse=True)
    return alerts[:100]


@app.get('/alerts')
def alerts():
    return redirect(url_for('history'))


def report_data():
    dataset = request.args.get('dataset', 'regional').strip()
    if dataset not in ('regional', 'stations', 'station_history'):
        abort(400, 'Unknown report source.')
    start = request.args.get('start','').strip()
    end = request.args.get('end','').strip()
    city = request.args.get('city','').strip()
    fuel = request.args.get('fuel','').strip()
    cond=[]; args=[]
    try:
        if start: start_date=date.fromisoformat(start)
        if end: end_date=date.fromisoformat(end)
        if start and end and start_date > end_date:
            raise ValueError('Start date must not exceed end date.')
    except ValueError as exc:
        abort(400, str(exc) if 'Start date' in str(exc) else 'Use YYYY-MM-DD for report dates.')
    if dataset=='regional':
        if start:cond.append('r.week_start >= %s');args.append(start)
        if end:cond.append('r.week_start <= %s');args.append(end)
        if city:cond.append('r.city=%s');args.append(city)
        if fuel:cond.append('f.fuel_name=%s');args.append(fuel)
        rows=sql('''SELECT r.week_start,r.week_end,r.city,r.brand,f.fuel_name,
                           r.min_price,r.max_price,r.common_price,b.source_filename
                    FROM regional_prices r JOIN fuel_types f ON f.fuel_id=r.fuel_id
                    JOIN pdf_import_batches b ON b.import_id=r.import_id
                    WHERE '''+(' AND '.join(cond) or '1=1')+
                 ' ORDER BY r.week_start DESC,r.city,r.brand,f.fuel_name LIMIT 20000',args)
        labels=['Week Start','Week End','City','Brand','Fuel Type','Minimum (PHP/L)','Maximum (PHP/L)','Common Price (PHP/L)','Source PDF']
        keys=['week_start','week_end','city','brand','fuel_name','min_price','max_price','common_price','source_filename']
    else:
        if dataset=='stations':
            src='''FROM fuel_prices p JOIN gas_stations s ON s.station_id=p.station_id
                   JOIN fuel_types f ON f.fuel_id=p.fuel_id'''
            datefield='p.updated_at'
        else:
            src='''FROM price_history p JOIN gas_stations s ON s.station_id=p.station_id
                   JOIN fuel_types f ON f.fuel_id=p.fuel_id'''
            datefield='p.recorded_at'
        if start:cond.append(datefield+' >= %s');args.append(start)
        if end:cond.append(datefield+' < %s');args.append((end_date+timedelta(days=1)).isoformat())
        if city:cond.append('s.city=%s');args.append(city)
        if fuel:cond.append('f.fuel_name=%s');args.append(fuel)
        rows=sql('SELECT '+datefield+' AS record_date,s.station_name,s.city,s.brand,f.fuel_name,'+
                 'p.price_per_liter AS price_per_liter '+src+' WHERE '+(' AND '.join(cond) or '1=1')+
                 ' ORDER BY '+datefield+' DESC,s.city LIMIT 20000',args)
        labels=['Record Date','Station','City','Brand','Fuel Type','Price per Liter (PHP)']
        keys=['record_date','station_name','city','brand','fuel_name','price_per_liter']
    return rows,{'start':start,'end':end,'city':city,'fuel':fuel,'dataset':dataset},labels,keys


@app.get('/reports')
@login_required(admin=True)
def reports():
    rows,filters,labels,keys=report_data()
    cities=sql('''SELECT DISTINCT city FROM (
                  SELECT city FROM regional_prices UNION SELECT city FROM gas_stations
                  ) reports_cities ORDER BY city''')
    return render_template('reports.html',active='reports',rows=rows[:150],total=len(rows),filters=filters,
                           labels=labels,keys=keys,cities=cities,fuels=datasets())


@app.get('/reports/download/<kind>')
@login_required(admin=True)
def export_report(kind):
    if kind not in ('csv','xlsx'): abort(404)
    rows,filters,labels,keys=report_data()
    def protect_text(value):
        if value is None: return ''
        if isinstance(value, (date,datetime,Decimal)):return str(value)
        value=str(value)
        return "'"+value if value and value[0] in '=+-@\t\r' else value
    if kind=='csv':
        f=io.StringIO();w=csv.writer(f);w.writerow(labels)
        for r in rows: w.writerow([protect_text(r[k]) for k in keys])
        buf=io.BytesIO(f.getvalue().encode('utf-8-sig'))
        return send_file(buf,as_attachment=True,download_name='gaswatch_'+filters['dataset']+'_report.csv',mimetype='text/csv')
    wb=Workbook();ws=wb.active;ws.title='GasWatch Report';ws.append(labels)
    for r in rows:
        values=[]
        for k in keys:
            val=r[k]
            if isinstance(val,Decimal): val=float(val)
            elif isinstance(val,str): val=protect_text(val)
            values.append(val)
        ws.append(values)
    for c in ws[1]:
        c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='14283B');c.alignment=Alignment(wrap_text=True)
    date_columns=[i for i,k in enumerate(keys,1) if k in ('week_start','week_end','record_date')]
    price_columns=[i for i,k in enumerate(keys,1) if k in ('min_price','max_price','common_price','price_per_liter')]
    for row in ws.iter_rows(min_row=2):
        for j in date_columns:row[j-1].number_format='yyyy-mm-dd hh:mm' if keys[j-1]=='record_date' else 'yyyy-mm-dd'
        for j in price_columns:row[j-1].number_format='"₱"#,##0.00'
    ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    from openpyxl.utils import get_column_letter
    for i,k in enumerate(keys,1):
        ws.column_dimensions[get_column_letter(i)].width=37 if k=='source_filename' else 24 if k in ('station_name','city') else 20
    buf=io.BytesIO();wb.save(buf);buf.seek(0)
    return send_file(buf,as_attachment=True,download_name='gaswatch_'+filters['dataset']+'_report.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.get('/admin')
@login_required(admin=True)
def admin_dashboard():
    counts=sql('''SELECT (SELECT COUNT(*) FROM users WHERE username='admin' AND role='admin') AS users,
                         (SELECT COUNT(*) FROM gas_stations) AS stations,
                         (SELECT COUNT(*) FROM fuel_prices) AS prices,
                         (SELECT COUNT(*) FROM pdf_import_batches) AS imports''',one=True)
    recent=sql('''SELECT b.*,u.username FROM pdf_import_batches b JOIN users u ON b.uploaded_by=u.user_id
                  ORDER BY b.imported_at DESC LIMIT 10''')
    week = latest_week()
    return render_template('admin_dashboard.html',active='admin',counts=counts,recent=recent,
                           week=week, fuel_averages=dashboard_fuel_averages(week))


@app.route('/admin/stations', methods=['GET','POST'])
@login_required(admin=True)
def admin_stations():
    if request.method=='POST':
        try:
            station_id=int(request.form.get('station_id') or 0)
            name=request.form.get('station_name','').strip()
            brand=request.form.get('brand','').strip().upper()
            city=request.form.get('city','').strip()
            status=request.form.get('status','active')
            if not all([name,brand,city]) or status not in ('active','inactive'):
                raise ValueError('Station name, brand and city are required.')
            args=(name[:100],brand[:50],city[:100],status)
            if station_id:
                change('''UPDATE gas_stations SET station_name=%s,brand=%s,city=%s,status=%s WHERE station_id=%s''',args+(station_id,))
            else:
                change('''INSERT INTO gas_stations (station_name,brand,city,status) VALUES (%s,%s,%s,%s)''',args)
            flash('Station saved.','success')
        except (ValueError,InvalidOperation) as exc:
            flash(str(exc),'danger')
        return redirect(url_for('admin_stations'))
    edit=request.args.get('edit',type=int)
    selected=sql('SELECT * FROM gas_stations WHERE station_id=%s',(edit,),one=True) if edit else None
    return render_template('admin_stations.html',active='admin',rows=sql('SELECT * FROM gas_stations ORDER BY city,station_name LIMIT 500'),selected=selected)


@app.route('/admin/fuels',methods=['GET','POST'])
@login_required(admin=True)
def admin_fuels():
    if request.method=='POST':
        name=request.form.get('fuel_name','').strip().upper()
        desc=request.form.get('description','').strip()
        fuel_id=int(request.form.get('fuel_id') or 0)
        if not name or len(name)>50:
            flash('Enter a fuel name of up to 50 characters.','danger')
        else:
            try:
                if fuel_id:
                    change('UPDATE fuel_types SET fuel_name=%s,description=%s WHERE fuel_id=%s',(name,desc[:255],fuel_id))
                else:
                    change('INSERT INTO fuel_types (fuel_name,description) VALUES (%s,%s)',(name,desc[:255]))
                flash('Fuel type saved.','success')
            except pymysql.err.IntegrityError:
                flash('This fuel name already exists.','danger')
        return redirect(url_for('admin_fuels'))
    edit=request.args.get('edit',type=int)
    selected=sql('SELECT * FROM fuel_types WHERE fuel_id=%s',(edit,),one=True) if edit else None
    return render_template('admin_fuels.html',active='admin',fuels=datasets(),selected=selected)


@app.route('/admin/prices',methods=['GET','POST'])
@login_required(admin=True)
def admin_prices():
    if request.method=='POST':
        try:
            station_id=int(request.form.get('station_id','0'))
            fuel_id=int(request.form.get('fuel_id','0'))
            amount=number(request.form.get('price_per_liter'))
            if not sql('SELECT station_id FROM gas_stations WHERE station_id=%s AND status=%s',(station_id,'active'),one=True):
                raise ValueError('Select an active station.')
            if not sql('SELECT fuel_id FROM fuel_types WHERE fuel_id=%s',(fuel_id,),one=True):
                raise ValueError('Select a valid fuel type.')
            conn=db();conn.begin()
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT price_per_liter FROM fuel_prices WHERE station_id=%s AND fuel_id=%s FOR UPDATE',(station_id,fuel_id))
                    old=cur.fetchone()
                    if old and old['price_per_liter']==amount:
                        conn.commit(); flash('Price is unchanged; no duplicate history entry created.','warning')
                        return redirect(url_for('admin_prices'))
                    cur.execute('''INSERT INTO fuel_prices (station_id,fuel_id,price_per_liter,updated_at,updated_by)
                                   VALUES (%s,%s,%s,NOW(),%s) ON DUPLICATE KEY UPDATE
                                   price_per_liter=VALUES(price_per_liter),updated_at=NOW(),updated_by=VALUES(updated_by)''',
                                (station_id,fuel_id,amount,session['user_id']))
                    cur.execute('''INSERT INTO price_history (station_id,fuel_id,price_per_liter,recorded_at,recorded_by)
                                   VALUES (%s,%s,%s,NOW(),%s)''',(station_id,fuel_id,amount,session['user_id']))
                conn.commit()
                flash('Station price saved, and price history recorded.','success')
            except Exception:
                conn.rollback();raise
        except (ValueError,InvalidOperation) as exc:
            flash(str(exc),'danger')
        return redirect(url_for('admin_prices'))
    recent=sql('''SELECT p.*,s.station_name,s.city,f.fuel_name FROM fuel_prices p
                  JOIN gas_stations s ON s.station_id=p.station_id JOIN fuel_types f ON f.fuel_id=p.fuel_id
                  ORDER BY p.updated_at DESC LIMIT 150''')
    return render_template('admin_prices.html',active='admin',stations=sql("SELECT * FROM gas_stations WHERE status='active' ORDER BY city,station_name"),
                           fuels=datasets(),recent=recent)


def draft_read(token):
    if not re.fullmatch(r'[a-f0-9]{32}',token):abort(404)
    path=DRAFTS/(token+'.json')
    if not path.exists():abort(404)
    data=json.loads(path.read_text(encoding='utf-8'))
    if data['owner']!=session['user_id'] or datetime.utcnow().timestamp()-data['timestamp']>7200:
        abort(403,'Preview expired or is not owned by this administrator.')
    return data,path


@app.route('/admin/import',methods=['GET','POST'])
@login_required(admin=True)
def admin_import():
    if request.method=='POST':
        file=request.files.get('pdf_file')
        if not file or not file.filename or not file.filename.lower().endswith('.pdf'):
            flash('Select a DOE PDF file.','danger')
            return redirect(url_for('admin_import'))
        pdf_bytes=file.read()
        if not pdf_bytes.startswith(b'%PDF-'):
            flash('The selected file is not a valid PDF.','danger')
            return redirect(url_for('admin_import'))
        try:
            parsed=parse_doe_pdf(pdf_bytes)
            parsed['rows']=add_preview_flags(parsed['rows'],parsed['week_start'])
            # Place suspicious rows at the top of preview, without changing saved row order.
            parsed['rows'].sort(key=lambda row: (not row['needs_review'], row['city'], row['fuel_name'], row['brand']))
        except Exception as exc:
            # PDF uploads from other layouts may fail; never silently fabricate rows.
            flash('PDF extraction failed: '+str(exc),'danger')
            return redirect(url_for('admin_import'))
        token=secrets.token_hex(16)
        digest=hashlib.sha256(pdf_bytes).hexdigest()
        (ARCHIVE/(digest+'.pdf')).write_bytes(pdf_bytes)
        parsed.update(owner=session['user_id'],timestamp=datetime.utcnow().timestamp(),
                      filename=secure_filename(file.filename)[:255],sha256=digest)
        (DRAFTS/(token+'.json')).write_text(json.dumps(parsed,ensure_ascii=False),encoding='utf-8')
        return redirect(url_for('admin_import_preview',token=token))
    recent=sql('''SELECT b.*,u.username FROM pdf_import_batches b JOIN users u ON b.uploaded_by=u.user_id
                  ORDER BY b.import_id DESC LIMIT 20''')
    return render_template('admin_import.html',active='admin',recent=recent)


@app.get('/admin/import/preview/<token>')
@login_required(admin=True)
def admin_import_preview(token):
    preview,_=draft_read(token)
    counts={'rows':len(preview['rows']),'flagged':sum(bool(r['needs_review']) for r in preview['rows']),
            'cities':len({r['city'] for r in preview['rows']})}
    return render_template('admin_preview.html',active='admin',token=token,preview=preview,counts=counts,
                           ncr_cities=KNOWN_NCR_CITIES)


@app.post('/admin/import/commit/<token>')
@login_required(admin=True)
def admin_import_commit(token):
    original,path=draft_read(token)
    payload=request.get_json(silent=True) or {}
    incoming=payload.get('rows',[])
    if not isinstance(incoming,list) or len(incoming)!=len(original['rows']):
        return jsonify(error='Preview rows do not match the upload.'),400
    try:
        fuel_ids={r['fuel_name']:r['fuel_id'] for r in datasets()}
        prepared=[]
        seen=set()
        for item,base in zip(incoming,original['rows']):
            if not isinstance(item,dict):raise ValueError('Invalid row in submitted data.')
            if not item.get('include'):continue
            city=str(item.get('city','')).strip()
            if not city or len(city)>100: raise ValueError('Every included row needs a valid city.')
            if base['fuel_name'] not in fuel_ids:raise ValueError('A fuel type is missing in the database.')
            low=number(item.get('min_price'))
            high=number(item.get('max_price'))
            common=number(item.get('common_price'),allow_none=True) if base['brand']=='OVERALL' else None
            if high<low: raise ValueError(f'Minimum price exceeds maximum for {city} / {base["fuel_name"]}.')
            if common is not None and (common<low or common>high):
                raise ValueError(f'Common price must be within the range for {city} / {base["fuel_name"]}.')
            edited = (city != base['city'] or low != number(base['min_price'])
                      or high != number(base['max_price'])
                      or (base['brand']=='OVERALL' and common != number(base['common_price'], allow_none=True)))
            if (base['needs_review'] or edited) and item.get('confirmed') is not True:
                raise ValueError('Confirm every flagged or edited row, or exclude it.')
            key=(city,base['brand'],base['fuel_name'])
            if key in seen:raise ValueError('Duplicate city / brand / fuel combination in preview.')
            seen.add(key)
            prepared.append((original['week_start'],original['week_end'],city,base['brand'],fuel_ids[base['fuel_name']],low,high,common))
        if not prepared: raise ValueError('Select at least one price row.')
        conn=db();conn.begin()
        try:
            with conn.cursor() as cur:
                cur.execute('''INSERT INTO pdf_import_batches (source_filename,file_sha256,week_start,week_end,uploaded_by,imported_rows)
                               VALUES (%s,%s,%s,%s,%s,%s)''',
                            (original['filename'],original['sha256'],original['week_start'],original['week_end'],session['user_id'],len(prepared)))
                batch=cur.lastrowid
                cur.executemany('''INSERT INTO regional_prices
                                   (import_id,week_start,week_end,city,brand,fuel_id,min_price,max_price,common_price)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON DUPLICATE KEY UPDATE import_id=VALUES(import_id),
                                   min_price=VALUES(min_price),max_price=VALUES(max_price),common_price=VALUES(common_price)''',
                                [(batch,)+r for r in prepared])
            conn.commit()
        except Exception:
            conn.rollback();raise
        path.unlink(missing_ok=True)
        flash(f'Imported {len(prepared)} DOE city/brand price ranges for {original["week_start"]} to {original["week_end"]}.','success')
        return jsonify(redirect=url_for('regional'),count=len(prepared))
    except (ValueError,InvalidOperation) as exc:
        return jsonify(error=str(exc)),400


@app.errorhandler(403)
def forbidden(exc):
    return render_template('message.html',active='',title='Access denied',message='You do not have permission to view this page.'),403


@app.errorhandler(404)
def not_found(exc):
    return render_template('message.html',active='',title='Page not found',message='That page does not exist.'),404


@app.errorhandler(413)
def large_file(exc):
    return render_template('message.html',active='',title='File too large',message='Use a PDF smaller than 12 MB.'),413


if __name__=='__main__':
    with app.app_context():
        ensure_admin_account()
    app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5000')),
            debug=os.getenv('FLASK_DEBUG','0')=='1')
