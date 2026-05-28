import json
from flask import Response
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import db
import sys
import os

# Визначаємо шлях до ресурсів
if getattr(sys, 'frozen', False):
    # Якщо програма запущена як exe
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    # Якщо програма запущена через python app.py
    app = Flask(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-truckmatch'

# Ініціалізація бази даних при запуску застосунку
with app.app_context():
    db.init_db()


# Декоратор для захисту маршрутів
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# Маршрут першого запуску (встановлення пароля)
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    conn = db.get_db()
    user = conn.execute("SELECT * FROM USERS LIMIT 1").fetchone()
    conn.close()

    if user:  # Якщо користувач вже є, перенаправляємо на сторінку входу
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password')
        if len(password) < 4:
            flash('Пароль має бути не коротше 4 символів.', 'error')
        else:
            hashed_pw = generate_password_hash(password)
            conn = db.get_db()
            conn.execute("INSERT INTO USERS (username, password_hash) VALUES (?, ?)", ('admin', hashed_pw))
            conn.commit()
            conn.close()
            flash('Пароль успішно встановлено! Тепер ви можете увійти.', 'success')
            return redirect(url_for('login'))

    return render_template('setup.html', title="Перший запуск")


# Маршрут входу
@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = db.get_db()
    user = conn.execute("SELECT * FROM USERS LIMIT 1").fetchone()
    conn.close()

    if not user:
        return redirect(url_for('setup'))

    if request.method == 'POST':
        password = request.form.get('password')
        if check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            return redirect(url_for('index'))
        else:
            flash('Невірний пароль!', 'error')

    return render_template('login.html', title="Вхід у систему")


# Маршрут виходу
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Ви вийшли з системи.', 'info')
    return redirect(url_for('login'))


# Головна сторінка (захищена)
@app.route('/')
@login_required
def index():
    return render_template('dashboard.html', title="Головна")


# ==========================================
# МОДУЛЬ 3: ЗАЯВКИ НА ВАНТАЖОПЕРЕВЕЗЕННЯ (F1, F6)
# ==========================================

@app.route('/requests')
@login_required
def cargo_requests():
    # Зчитування параметрів фільтрації
    status = request.args.get('status', '')
    origin = request.args.get('origin', '')
    destination = request.args.get('destination', '')
    date = request.args.get('date', '')
    cargo_type = request.args.get('cargo_type', '')

    # Динамічна побудова SQL-запиту
    query = '''
        SELECT CR.*, C.full_name as client_name, C.phone as client_phone 
        FROM CARGO_REQUESTS CR
        JOIN CLIENTS C ON CR.client_id = C.id
        WHERE 1=1
    '''
    params = []
    if status: query += ' AND CR.status = ?'; params.append(status)
    if origin: query += ' AND CR.origin_city LIKE ?'; params.append(f'%{origin}%')
    if destination: query += ' AND CR.destination_city LIKE ?'; params.append(f'%{destination}%')
    if date: query += ' AND CR.desired_date = ?'; params.append(date)
    if cargo_type: query += ' AND CR.cargo_type LIKE ?'; params.append(f'%{cargo_type}%')

    query += ' ORDER BY CR.created_at DESC'

    conn = db.get_db()
    requests_list = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('requests/index.html', requests=requests_list, request_args=request.args,
                           title="Заявки замовників")


@app.route('/requests/add', methods=['GET', 'POST'])
@login_required
def add_request():
    conn = db.get_db()
    if request.method == 'POST':
        conn.execute('''INSERT INTO CARGO_REQUESTS 
                        (client_id, origin_city, destination_city, cargo_type, weight_tons, desired_date, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (request.form['client_id'], request.form['origin_city'], request.form['destination_city'],
                      request.form['cargo_type'], request.form['weight_tons'], request.form['desired_date'],
                      request.form['notes']))
        conn.commit()
        conn.close()
        flash('Заявку на перевезення успішно створено!', 'success')
        return redirect(url_for('cargo_requests'))

    # Завантажуємо список клієнтів для випадаючого списку
    clients = conn.execute('SELECT id, full_name FROM CLIENTS ORDER BY full_name').fetchall()
    conn.close()
    return render_template('requests/form.html', clients=clients, title="Нова заявка від замовника")


# ==========================================
# МОДУЛЬ 4: ПРОПОЗИЦІЇ ПЕРЕВІЗНИКІВ (ВІЛЬНІ АВТО) (F2, F6)
# ==========================================

@app.route('/offers')
@login_required
def offers():
    status = request.args.get('status', '')
    origin = request.args.get('origin', '')
    destination = request.args.get('destination', '')
    date = request.args.get('date', '')

    query = '''
        SELECT CO.*, C.full_name as carrier_name, C.phone as carrier_phone 
        FROM CARRIER_OFFERS CO
        JOIN CARRIERS C ON CO.carrier_id = C.id
        WHERE 1=1
    '''
    params = []
    if status: query += ' AND CO.status = ?'; params.append(status)
    if origin: query += ' AND CO.origin_city LIKE ?'; params.append(f'%{origin}%')
    if destination: query += ' AND CO.destination_city LIKE ?'; params.append(f'%{destination}%')
    if date: query += ' AND CO.available_date = ?'; params.append(date)

    query += ' ORDER BY CO.created_at DESC'

    conn = db.get_db()
    offers_list = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('offers/index.html', offers=offers_list, request_args=request.args,
                           title="Вільний транспорт")


@app.route('/offers/add', methods=['GET', 'POST'])
@login_required
def add_offer():
    conn = db.get_db()
    if request.method == 'POST':
        conn.execute('''INSERT INTO CARRIER_OFFERS 
                        (carrier_id, origin_city, destination_city, vehicle_type, capacity_tons, available_date, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (request.form['carrier_id'], request.form['origin_city'], request.form['destination_city'],
                      request.form['vehicle_type'], request.form['capacity_tons'], request.form['available_date'],
                      request.form['notes']))
        conn.commit()
        conn.close()
        flash('Пропозицію вільного авто успішно опубліковано!', 'success')
        return redirect(url_for('offers'))

    carriers = conn.execute(
        'SELECT id, full_name, vehicle_type, capacity_tons FROM CARRIERS ORDER BY full_name').fetchall()
    conn.close()
    return render_template('offers/form.html', carriers=carriers, title="Додати вільне авто")


# ==========================================
# МОДУЛЬ 1: ЗАМОВНИКИ (CLIENTS)
# ==========================================

@app.route('/clients')
@login_required
def clients():
    search = request.args.get('search', '')
    conn = db.get_db()
    if search:
        query = 'SELECT * FROM CLIENTS WHERE full_name LIKE ? OR phone LIKE ? ORDER BY created_at DESC'
        clients_list = conn.execute(query, (f'%{search}%', f'%{search}%')).fetchall()
    else:
        clients_list = conn.execute('SELECT * FROM CLIENTS ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('clients/index.html', clients=clients_list, search=search, title="Замовники")


@app.route('/clients/add', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        email = request.form['email']
        notes = request.form['notes']

        conn = db.get_db()
        conn.execute('INSERT INTO CLIENTS (full_name, phone, email, notes) VALUES (?, ?, ?, ?)',
                     (full_name, phone, email, notes))
        conn.commit()
        conn.close()
        flash('Замовника успішно додано!', 'success')
        return redirect(url_for('clients'))
    return render_template('clients/form.html', title="Додати замовника", client=None)


@app.route('/clients/<int:id>')
@login_required
def view_client(id):
    conn = db.get_db()
    client = conn.execute('SELECT * FROM CLIENTS WHERE id = ?', (id,)).fetchone()

    if client is None:
        conn.close()
        return render_template('404.html'), 404

    deals = conn.execute('''
            SELECT D.id, D.status, D.agreed_price, D.created_at, CR.origin_city, CR.destination_city
            FROM DEALS D
            JOIN CARGO_REQUESTS CR ON D.request_id = CR.id
            WHERE CR.client_id = ?
            ORDER BY D.created_at DESC
        ''', (id,)).fetchall()
    conn.close()

    return render_template('clients/view.html', client=client, deals=deals, title=client['full_name'])


@app.route('/clients/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_client(id):
    conn = db.get_db()
    client = conn.execute('SELECT * FROM CLIENTS WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        conn.execute('''UPDATE CLIENTS SET full_name = ?, phone = ?, email = ?, notes = ? WHERE id = ?''',
                     (request.form['full_name'], request.form['phone'], request.form['email'], request.form['notes'],
                      id))
        conn.commit()
        conn.close()
        flash('Дані замовника оновлено!', 'success')
        return redirect(url_for('view_client', id=id))

    conn.close()
    return render_template('clients/form.html', title="Редагування замовника", client=client)


@app.route('/clients/<int:id>/delete', methods=['POST'])
@login_required
def delete_client(id):
    conn = db.get_db()
    # Заборона видалення, якщо є заявки
    requests_count = conn.execute('SELECT COUNT(*) FROM CARGO_REQUESTS WHERE client_id = ?', (id,)).fetchone()[0]
    if requests_count > 0:
        flash('Неможливо видалити замовника: існують пов\'язані заявки!', 'error')
    else:
        conn.execute('DELETE FROM CLIENTS WHERE id = ?', (id,))
        conn.commit()
        flash('Замовника видалено.', 'success')
    conn.close()
    return redirect(url_for('clients'))


# ==========================================
# МОДУЛЬ 2: ПЕРЕВІЗНИКИ (CARRIERS)
# ==========================================

@app.route('/carriers')
@login_required
def carriers():
    search = request.args.get('search', '')
    conn = db.get_db()
    if search:
        query = 'SELECT * FROM CARRIERS WHERE full_name LIKE ? OR vehicle_type LIKE ? ORDER BY created_at DESC'
        carriers_list = conn.execute(query, (f'%{search}%', f'%{search}%')).fetchall()
    else:
        carriers_list = conn.execute('SELECT * FROM CARRIERS ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('carriers/index.html', carriers=carriers_list, search=search, title="Перевізники")


@app.route('/carriers/add', methods=['GET', 'POST'])
@login_required
def add_carrier():
    if request.method == 'POST':
        conn = db.get_db()
        conn.execute('''INSERT INTO CARRIERS (full_name, phone, email, vehicle_type, capacity_tons, notes) 
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (request.form['full_name'], request.form['phone'], request.form['email'],
                      request.form['vehicle_type'], request.form['capacity_tons'], request.form['notes']))
        conn.commit()
        conn.close()
        flash('Перевізника успішно додано!', 'success')
        return redirect(url_for('carriers'))
    return render_template('carriers/form.html', title="Додати перевізника", carrier=None)


@app.route('/carriers/<int:id>')
@login_required
def view_carrier(id):
    conn = db.get_db()
    carrier = conn.execute('SELECT * FROM CARRIERS WHERE id = ?', (id,)).fetchone()

    if carrier is None:
        conn.close()
        return render_template('404.html'), 404

    deals = conn.execute('''
            SELECT D.id, D.status, D.agreed_price, D.created_at, CO.origin_city, CO.destination_city
            FROM DEALS D
            JOIN CARRIER_OFFERS CO ON D.offer_id = CO.id
            WHERE CO.carrier_id = ?
            ORDER BY D.created_at DESC
        ''', (id,)).fetchall()
    conn.close()

    return render_template('carriers/view.html', carrier=carrier, deals=deals, title=carrier['full_name'])


@app.route('/carriers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_carrier(id):
    conn = db.get_db()
    carrier = conn.execute('SELECT * FROM CARRIERS WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        conn.execute(
            '''UPDATE CARRIERS SET full_name = ?, phone = ?, email = ?, vehicle_type = ?, capacity_tons = ?, notes = ? WHERE id = ?''',
            (request.form['full_name'], request.form['phone'], request.form['email'],
             request.form['vehicle_type'], request.form['capacity_tons'], request.form['notes'], id))
        conn.commit()
        conn.close()
        flash('Дані перевізника оновлено!', 'success')
        return redirect(url_for('view_carrier', id=id))

    conn.close()
    return render_template('carriers/form.html', title="Редагування перевізника", carrier=carrier)


@app.route('/carriers/<int:id>/delete', methods=['POST'])
@login_required
def delete_carrier(id):
    conn = db.get_db()
    offers_count = conn.execute('SELECT COUNT(*) FROM CARRIER_OFFERS WHERE carrier_id = ?', (id,)).fetchone()[0]
    if offers_count > 0:
        flash('Неможливо видалити перевізника: існують пов\'язані пропозиції!', 'error')
    else:
        conn.execute('DELETE FROM CARRIERS WHERE id = ?', (id,))
        conn.commit()
        flash('Перевізника видалено.', 'success')
    conn.close()
    return redirect(url_for('carriers'))


# ==========================================
# МОДУЛЬ 5: ПІДБІР ТА УГОДИ (DEALS) (F3, F4, F5)
# ==========================================

@app.route('/requests/<int:id>/match')
@login_required
def match_request(id):
    """F3: Пошук відповідності (Match)"""
    conn = db.get_db()
    req = conn.execute('SELECT * FROM CARGO_REQUESTS WHERE id = ?', (id,)).fetchone()

    if not req:
        conn.close()
        return render_template('404.html'), 404

    # Шукаємо активні пропозиції: збіг міст та достатня вантажопідйомність
    query = '''
        SELECT CO.*, C.full_name as carrier_name, C.phone as carrier_phone 
        FROM CARRIER_OFFERS CO
        JOIN CARRIERS C ON CO.carrier_id = C.id
        WHERE CO.status = 'Активна'
          AND CO.origin_city LIKE ?
          AND CO.destination_city LIKE ?
          AND CO.capacity_tons >= ?
        ORDER BY CO.capacity_tons ASC
    '''
    offers = conn.execute(query,
                          (f"%{req['origin_city']}%", f"%{req['destination_city']}%", req['weight_tons'])).fetchall()
    conn.close()

    return render_template('deals/match.html', req=req, offers=offers, title="Підбір перевізника")


@app.route('/deals/create', methods=['POST'])
@login_required
def create_deal():
    """F4: Підтвердження угоди (Зв'язування)"""
    req_id = request.form['request_id']
    offer_id = request.form['offer_id']
    price = request.form.get('agreed_price', 0)

    conn = db.get_db()

    # 5.9: Валідація — чи не зайняті вже заявка або пропозиція
    req_status = conn.execute("SELECT status FROM CARGO_REQUESTS WHERE id = ?", (req_id,)).fetchone()['status']
    offer_status = conn.execute("SELECT status FROM CARRIER_OFFERS WHERE id = ?", (offer_id,)).fetchone()['status']

    if req_status != 'Нова' or offer_status != 'Активна':
        conn.close()
        flash('Помилка: Заявка або авто вже зайняті в іншій угоді!', 'error')
        return redirect(url_for('cargo_requests'))

    # Створюємо угоду
    conn.execute('''INSERT INTO DEALS (request_id, offer_id, agreed_price, status)
                    VALUES (?, ?, ?, 'Нова')''', (req_id, offer_id, price))
    deal_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Оновлюємо статуси
    conn.execute("UPDATE CARGO_REQUESTS SET status = 'В обробці' WHERE id = ?", (req_id,))
    conn.execute("UPDATE CARRIER_OFFERS SET status = 'В обробці' WHERE id = ?", (offer_id,))

    conn.commit()
    conn.close()
    flash('Пару успішно зведено! Угоду створено.', 'success')
    return redirect(url_for('view_deal', id=deal_id))


@app.route('/deals')
@login_required
def deals():
    """Список усіх угод"""
    conn = db.get_db()
    query = '''
        SELECT D.*, 
               CR.origin_city, CR.destination_city, CR.cargo_type,
               C1.full_name as client_name,
               C2.full_name as carrier_name
        FROM DEALS D
        JOIN CARGO_REQUESTS CR ON D.request_id = CR.id
        JOIN CARRIER_OFFERS CO ON D.offer_id = CO.id
        JOIN CLIENTS C1 ON CR.client_id = C1.id
        JOIN CARRIERS C2 ON CO.carrier_id = C2.id
        ORDER BY D.created_at DESC
    '''
    deals_list = conn.execute(query).fetchall()
    conn.close()
    return render_template('deals/index.html', deals=deals_list, title="Управління угодами")


@app.route('/deals/<int:id>', methods=['GET', 'POST'])
@login_required
def view_deal(id):
    """F5: Машина станів угоди та перегляд деталей"""
    conn = db.get_db()

    if request.method == 'POST':
        new_status = request.form['status']
        deal = conn.execute("SELECT status, request_id, offer_id FROM DEALS WHERE id = ?", (id,)).fetchone()

        # 5.6: Валідація недопустимого переходу
        if deal['status'] in ['Завершена', 'Скасована']:
            conn.close()
            flash('Неможливо змінити статус закритої або скасованої угоди.', 'error')
            return redirect(url_for('view_deal', id=id))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_query = "UPDATE DEALS SET status = ?"
        params = [new_status]

        if new_status == 'Підтверджена':
            update_query += ", confirmed_at = ?"
            params.append(now)
        elif new_status == 'Завершена':
            update_query += ", completed_at = ?"
            params.append(now)

        update_query += " WHERE id = ?"
        params.append(id)
        conn.execute(update_query, tuple(params))

        # 5.7: Логіка синхронізації статусів заявок
        if new_status == 'Скасована':
            # Повертаємо в пул
            conn.execute("UPDATE CARGO_REQUESTS SET status = 'Нова' WHERE id = ?", (deal['request_id'],))
            conn.execute("UPDATE CARRIER_OFFERS SET status = 'Активна' WHERE id = ?", (deal['offer_id'],))
        elif new_status == 'Завершена':
            conn.execute("UPDATE CARGO_REQUESTS SET status = 'Завершена' WHERE id = ?", (deal['request_id'],))
            conn.execute("UPDATE CARRIER_OFFERS SET status = 'Завершена' WHERE id = ?", (deal['offer_id'],))
        else:
            conn.execute("UPDATE CARGO_REQUESTS SET status = 'В обробці' WHERE id = ?", (deal['request_id'],))
            conn.execute("UPDATE CARRIER_OFFERS SET status = 'В обробці' WHERE id = ?", (deal['offer_id'],))

        conn.commit()
        flash(f'Статус угоди змінено на "{new_status}"', 'success')
        return redirect(url_for('view_deal', id=id))

    deal_query = '''
        SELECT D.*, 
               CR.origin_city, CR.destination_city, CR.cargo_type, CR.weight_tons, CR.desired_date,
               C1.full_name as client_name, C1.phone as client_phone,
               CO.vehicle_type, CO.capacity_tons,
               C2.full_name as carrier_name, C2.phone as carrier_phone
        FROM DEALS D
        JOIN CARGO_REQUESTS CR ON D.request_id = CR.id
        JOIN CARRIER_OFFERS CO ON D.offer_id = CO.id
        JOIN CLIENTS C1 ON CR.client_id = C1.id
        JOIN CARRIERS C2 ON CO.carrier_id = C2.id
        WHERE D.id = ?
    '''
    deal_details = conn.execute(deal_query, (id,)).fetchone()
    conn.close()

    if not deal_details:
        return render_template('404.html'), 404

    return render_template('deals/view.html', deal=deal_details, title=f"Угода #{deal_details['id']}")


# ==========================================
# МОДУЛЬ 6: СТАТИСТИКА ТА ЗВІТНІСТЬ (F8)
# ==========================================

@app.route('/statistics')
@login_required
def statistics():
    # 1. Визначення дат для фільтрації (за замовчуванням - поточний місяць)
    today = datetime.today()
    first_day_of_month = today.replace(day=1).strftime('%Y-%m-%d')
    current_day = today.strftime('%Y-%m-%d')

    start_date = request.args.get('start_date', first_day_of_month)
    end_date = request.args.get('end_date', current_day)

    conn = db.get_db()

    # 2. Агреговані показники закритих угод за період
    stats_query = '''
        SELECT 
            COUNT(D.id) as deals_count,
            SUM(CR.weight_tons) as total_weight,
            SUM(D.agreed_price) as total_revenue
        FROM DEALS D
        JOIN CARGO_REQUESTS CR ON D.request_id = CR.id
        WHERE D.status = 'Завершена'
          AND DATE(D.completed_at) >= ? 
          AND DATE(D.completed_at) <= ?
    '''
    stats = conn.execute(stats_query, (start_date, end_date)).fetchone()

    completed_deals = stats['deals_count'] or 0
    total_weight = round(stats['total_weight'] or 0, 1)
    total_revenue = round(stats['total_revenue'] or 0, 2)

    # 3. Аналітика скасованих угод за цей же період (для графіку співвідношення)
    canceled_deals = conn.execute('''
        SELECT COUNT(*) as count FROM DEALS 
        WHERE status = 'Скасована'
          AND DATE(created_at) >= ? AND DATE(created_at) <= ?
    ''', (start_date, end_date)).fetchone()['count']

    # 4. Поточний стан "ринку" (не залежить від дати - це зріз на даний момент)
    active_requests = conn.execute("SELECT COUNT(*) as c FROM CARGO_REQUESTS WHERE status = 'Нова'").fetchone()['c']
    active_offers = conn.execute("SELECT COUNT(*) as c FROM CARRIER_OFFERS WHERE status = 'Активна'").fetchone()['c']

    conn.close()

    # Розрахунок відсотка успішності для простого графіка
    total_processed = completed_deals + canceled_deals
    success_rate = int((completed_deals / total_processed * 100)) if total_processed > 0 else 0

    return render_template('statistics/index.html',
                           start_date=start_date,
                           end_date=end_date,
                           completed_deals=completed_deals,
                           canceled_deals=canceled_deals,
                           success_rate=success_rate,
                           total_weight=total_weight,
                           total_revenue=total_revenue,
                           active_requests=active_requests,
                           active_offers=active_offers,
                           title="Статистика та звіти")


# Обробка помилок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', title="Сторінку не знайдено"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html', title="Внутрішня помилка сервера"), 500


# ==========================================
# МОДУЛЬ 7: РЕЗЕРВНЕ КОПІЮВАННЯ ТА ПОРТАТИВНІСТЬ (F9)
# ==========================================

@app.route('/backup')
@login_required
def backup_page():
    return render_template('backup/index.html', title="Резервне копіювання")


@app.route('/backup/export')
@login_required
def export_backup():
    """Експорт усіх бізнес-даних у JSON"""
    conn = db.get_db()
    # Експортуємо всі таблиці, окрім USERS (щоб не перетерти пароль при відновленні на іншому ПК)
    tables = ['CLIENTS', 'CARRIERS', 'CARGO_REQUESTS', 'CARRIER_OFFERS', 'DEALS']
    backup_data = {}

    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        backup_data[table] = [dict(row) for row in rows]
    conn.close()

    # Формуємо JSON-текст
    json_data = json.dumps(backup_data, ensure_ascii=False, indent=4)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")

    # Повертаємо як файл для завантаження
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename=truckmatch_backup_{date_str}.json"}
    )


@app.route('/backup/import', methods=['POST'])
@login_required
def import_backup():
    """Відновлення даних із JSON-файлу"""
    if 'backup_file' not in request.files:
        flash('Файл не вибрано.', 'error')
        return redirect(url_for('backup_page'))

    file = request.files['backup_file']
    if file.filename == '':
        flash('Файл не вибрано.', 'error')
        return redirect(url_for('backup_page'))

    if file and file.filename.endswith('.json'):
        try:
            backup_data = json.load(file)
            conn = db.get_db()

            # Тимчасово вимикаємо перевірку зовнішніх ключів, щоб уникнути конфліктів при видаленні
            conn.execute('PRAGMA foreign_keys = OFF;')

            # Порядок видалення: від залежних до головних
            tables_to_clear = ['DEALS', 'CARGO_REQUESTS', 'CARRIER_OFFERS', 'CLIENTS', 'CARRIERS']
            for table in tables_to_clear:
                conn.execute(f"DELETE FROM {table}")

            # Порядок вставки: від головних до залежних
            tables_to_restore = ['CLIENTS', 'CARRIERS', 'CARGO_REQUESTS', 'CARRIER_OFFERS', 'DEALS']
            for table in tables_to_restore:
                if table in backup_data:
                    for row in backup_data[table]:
                        columns = ', '.join(row.keys())
                        placeholders = ', '.join(['?' for _ in row])
                        values = tuple(row.values())
                        # Вставляємо записи із збереженням їх оригінальних ID
                        conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", values)

            # Вмикаємо ключі назад
            conn.execute('PRAGMA foreign_keys = ON;')
            conn.commit()
            conn.close()
            flash('Дані успішно відновлено з резервної копії!', 'success')
        except Exception as e:
            flash(f'Помилка при відновленні даних. Переконайтеся, що файл коректний. Деталі: {str(e)}', 'error')
    else:
        flash('Будь ласка, завантажте файл у форматі .json', 'error')

    return redirect(url_for('backup_page'))

if __name__ == '__main__':
    app.run(debug=True)