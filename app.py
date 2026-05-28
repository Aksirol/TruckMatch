# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import db

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


@app.route('/statistics')
@login_required
def statistics():
    flash('Розділ "Статистика" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Статистика")


# Обробка помилок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', title="Сторінку не знайдено"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html', title="Внутрішня помилка сервера"), 500


if __name__ == '__main__':
    app.run(debug=True)