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


@app.route('/carriers')
@login_required
def carriers():
    flash('Розділ "Перевізники" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Перевізники")


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