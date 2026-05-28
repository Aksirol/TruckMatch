from flask import Flask, render_template, flash

app = Flask(__name__)
# Секретний ключ для сесій та flash-повідомлень
app.config['SECRET_KEY'] = 'dev-secret-key-truckmatch'

# Головна сторінка (Дашборд)
@app.route('/')
def index():
    return render_template('dashboard.html', title="Головна")

# Маршрути-заглушки для майбутніх розділів
@app.route('/requests')
def cargo_requests():
    flash('Розділ "Заявки" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Заявки")

@app.route('/carriers')
def carriers():
    flash('Розділ "Перевізники" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Перевізники")

@app.route('/deals')
def deals():
    flash('Розділ "Угоди" знаходиться в розробці.', 'info')
    return render_template('dashboard.html', title="Угоди")

@app.route('/statistics')
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