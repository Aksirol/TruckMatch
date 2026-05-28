# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
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


# Інші захищені маршрути-заглушки
@app.route('/requests')
@login_required
def cargo_requests():
    flash('Розділ "Заявки" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Заявки")


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
    # Тут у майбутньому ми будемо завантажувати історію угод для цього клієнта (Фаза 5)
    conn.close()
    if client is None:
        return render_template('404.html'), 404
    return render_template('clients/view.html', client=client, title=client['full_name'])


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
    conn.close()
    if carrier is None:
        return render_template('404.html'), 404
    return render_template('carriers/view.html', carrier=carrier, title=carrier['full_name'])


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


@app.route('/deals')
@login_required
def deals():
    flash('Розділ "Угоди" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Угоди")


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