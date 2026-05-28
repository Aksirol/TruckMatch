import os
import tempfile
import sqlite3
import unittest
from werkzeug.security import check_password_hash

import app
import db


class TruckMatchTestCase(unittest.TestCase):
    def setUp(self):
        """Виконується ПЕРЕД кожним тестом. Налаштовує тестове середовище."""
        # Створюємо тимчасовий файл і відразу закриваємо його системний дескриптор
        fd, self.db_path = tempfile.mkstemp()
        os.close(fd)

        # Видаляємо цей порожній файл, щоб db.init_db() створив його з нуля
        os.unlink(self.db_path)

        db.DB_PATH = self.db_path
        app.app.config['TESTING'] = True
        self.client = app.app.test_client()

        with app.app.app_context():
            db.init_db()

    def tearDown(self):
        """Виконується ПІСЛЯ кожного тесту. Очищує середовище."""
        # Намагаємося видалити тестову БД
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                # У Windows SQLite іноді тримає лок на долю секунди довше,
                # тому ігноруємо помилку, якщо файл не вдалося видалити миттєво
                pass

    # Допоміжні методи для тестів
    def setup_admin(self, password='correcthorse'):
        """Швидке створення пароля (імітація першого запуску)"""
        return self.client.post('/setup', data=dict(password=password), follow_redirects=True)

    def login(self, password):
        """Швидкий логін"""
        return self.client.post('/login', data=dict(password=password), follow_redirects=True)

    # ==========================================
    # ТЕСТОВІ СЦЕНАРІЇ ЗГІДНО З ТЕСТ-ПЛАНОМ
    # ==========================================

    def test_2_1_and_2_2_database_creation_and_schema(self):
        """2.1 (Створення БД) та 2.2 (Перевірка схеми та полів)"""
        # Перевірка, що файл фізично створено
        self.assertTrue(os.path.exists(self.db_path))

        # Підключаємося та отримуємо список усіх таблиць
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        conn.close()

        # Перевіряємо наявність усіх 6 цільових таблиць (sqlite_sequence створюється автоінкрементом)
        expected_tables = ['USERS', 'CLIENTS', 'CARRIERS', 'CARGO_REQUESTS', 'CARRIER_OFFERS', 'DEALS']
        for table in expected_tables:
            self.assertIn(table, tables)

    def test_2_3_setup_password_hashing(self):
        """2.3 Задання пароля при першому запуску"""
        test_password = 'mysecretpassword'
        self.setup_admin(test_password)

        # Читаємо безпосередньо з БД, що там збереглося
        conn = db.get_db()
        user = conn.execute("SELECT * FROM USERS WHERE username = 'admin'").fetchone()
        conn.close()

        self.assertIsNotNone(user, "Користувач не створений у БД")
        # Пароль НЕ повинен бути відкритим текстом
        self.assertNotEqual(user['password_hash'], test_password)
        # Хеш має успішно проходити перевірку
        self.assertTrue(check_password_hash(user['password_hash'], test_password))

    def test_2_4_valid_login(self):
        """2.4 Вхід із правильним паролем"""
        self.setup_admin('testpass')
        response = self.login('testpass')

        # Після успішного входу нас має перенаправити на головну (dashboard)
        self.assertEqual(response.request.path, '/')
        # Перевіряємо наявність привітального тексту з дашборду
        self.assertIn(b'TruckMatch', response.data)

    def test_2_5_invalid_login(self):
        """2.5 Вхід із неправильним паролем"""
        self.setup_admin('testpass')
        response = self.login('wrongpass')

        # Маємо залишитись на сторінці логіну
        self.assertEqual(response.request.path, '/login')
        # Має з'явитися повідомлення про помилку (шукаємо його в HTML)
        self.assertIn('Невірний пароль!'.encode('utf-8'), response.data)

    def test_2_6_access_internal_page_without_login(self):
        """2.6 Відкриття внутрішньої сторінки без входу"""
        self.setup_admin()  # Створюємо юзера, щоб система не кидала на /setup

        # Спроба зайти на захищену сторінку заявок
        response = self.client.get('/requests', follow_redirects=True)

        # Перевіряємо перенаправлення на сторінку входу
        self.assertEqual(response.request.path, '/login')

    def test_2_7_logout_and_retry(self):
        """2.7 Logout і повторна спроба доступу"""
        self.setup_admin('testpass')
        self.login('testpass')  # Увійшли

        # Виконуємо вихід
        logout_response = self.client.get('/logout', follow_redirects=True)
        self.assertIn('Ви вийшли з системи'.encode('utf-8'), logout_response.data)

        # Намагаємося зайти на закриту сторінку
        retry_response = self.client.get('/deals', follow_redirects=True)
        self.assertEqual(retry_response.request.path, '/login')

    def test_2_8_foreign_key_constraint(self):
        """2.8 Спроба зв'язку з неіснуючим записом (перевірка FK)"""
        # У нас увімкнено PRAGMA foreign_keys = ON; у БД
        conn = db.get_db()

        # Намагаємося додати заявку на вантаж для client_id = 9999, якого немає в CLIENTS
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city) VALUES (?, ?, ?)",
                (9999, 'Київ', 'Одеса')
            )
            conn.commit()

        conn.close()

    # ==========================================
    # ТЕСТОВІ СЦЕНАРІЇ ДЛЯ ФАЗИ 3 (КОНТАКТИ)
    # ==========================================

    def test_3_1_add_valid_client(self):
        """3.1 Додати замовника з валідними даними"""
        self.setup_admin('testpass')
        self.login('testpass')

        # Відправляємо форму додавання
        response = self.client.post('/clients/add', data={
            'full_name': 'ТОВ ТрансЛогістік',
            'phone': '+380501234567',
            'email': 'info@translog.com.ua',
            'notes': 'Надійний платник'
        }, follow_redirects=True)

        self.assertEqual(response.request.path, '/clients')
        self.assertIn('Замовника успішно додано!'.encode('utf-8'), response.data)

        # Перевіряємо безпосередньо в БД
        conn = db.get_db()
        client = conn.execute("SELECT * FROM CLIENTS WHERE full_name = 'ТОВ ТрансЛогістік'").fetchone()
        conn.close()
        self.assertIsNotNone(client)
        self.assertEqual(client['phone'], '+380501234567')

    def test_3_2_add_carrier_numeric_fields(self):
        """3.2 Додати перевізника (перевірка числових полів)"""
        self.setup_admin('testpass')
        self.login('testpass')

        self.client.post('/carriers/add', data={
            'full_name': 'ФОП Коваленко',
            'phone': '0670001122',
            'email': 'koval@ukr.net',
            'vehicle_type': 'Рефрижератор',
            'capacity_tons': '22.5',
            'notes': 'Температурний режим'
        }, follow_redirects=True)

        conn = db.get_db()
        carrier = conn.execute("SELECT * FROM CARRIERS WHERE full_name = 'ФОП Коваленко'").fetchone()
        conn.close()

        self.assertIsNotNone(carrier)
        self.assertEqual(carrier['vehicle_type'], 'Рефрижератор')
        # Перевіряємо, що вантажопідйомність збереглася як число з рухомою комою (float)
        self.assertEqual(carrier['capacity_tons'], 22.5)

    def test_3_3_edit_contact(self):
        """3.3 Редагувати контакт"""
        self.setup_admin('testpass')
        self.login('testpass')

        # Спочатку створюємо клієнта
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CLIENTS (full_name, phone) VALUES (?, ?)", ('Старе Імя', '111'))
        client_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Тепер редагуємо його через інтерфейс
        response = self.client.post(f'/clients/{client_id}/edit', data={
            'full_name': 'Нове Імя',
            'phone': '222',
            'email': '',
            'notes': 'Оновлено'
        }, follow_redirects=True)

        self.assertIn('Дані замовника оновлено!'.encode('utf-8'), response.data)

        # Перевіряємо БД на зміни
        conn = db.get_db()
        updated_client = conn.execute("SELECT * FROM CLIENTS WHERE id = ?", (client_id,)).fetchone()
        conn.close()
        self.assertEqual(updated_client['full_name'], 'Нове Імя')
        self.assertEqual(updated_client['phone'], '222')

    def test_3_4_view_contact_card(self):
        """3.4 Відкрити картку сторони (F7)"""
        self.setup_admin('testpass')
        self.login('testpass')

        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CLIENTS (full_name, phone, email, notes) VALUES (?, ?, ?, ?)",
                       ('Унікальний Клієнт', '099-999-99-99', 'test@test.com', 'Супер примітка'))
        client_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Відкриваємо сторінку перегляду
        response = self.client.get(f'/clients/{client_id}')
        html = response.data.decode('utf-8')

        # Перевіряємо наявність усіх даних на сторінці
        self.assertIn('Унікальний Клієнт', html)
        self.assertIn('099-999-99-99', html)
        self.assertIn('test@test.com', html)
        self.assertIn('Супер примітка', html)

    def test_3_5_search_contacts(self):
        """3.5 Пошук за ПІБ/телефоном"""
        self.setup_admin('testpass')
        self.login('testpass')

        conn = db.get_db()
        conn.execute("INSERT INTO CLIENTS (full_name, phone) VALUES ('Альфа ТОВ', '0501112233')")
        conn.execute("INSERT INTO CLIENTS (full_name, phone) VALUES ('Бета ФОП', '0679998877')")
        conn.commit()
        conn.close()

        # Пошук за назвою "Альфа"
        response1 = self.client.get('/clients?search=Альфа')
        html1 = response1.data.decode('utf-8')
        self.assertIn('Альфа ТОВ', html1)
        self.assertNotIn('Бета ФОП', html1)

        # Пошук за фрагментом телефону "9988"
        response2 = self.client.get('/clients?search=9988')
        html2 = response2.data.decode('utf-8')
        self.assertIn('Бета ФОП', html2)
        self.assertNotIn('Альфа ТОВ', html2)

    def test_3_6_delete_contact_without_links(self):
        """3.6 Видалити контакт без зв'язків"""
        self.setup_admin('testpass')
        self.login('testpass')

        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CLIENTS (full_name) VALUES ('Клієнт на видалення')")
        client_id = cursor.lastrowid
        conn.commit()
        conn.close()

        response = self.client.post(f'/clients/{client_id}/delete', follow_redirects=True)
        self.assertIn('Замовника видалено.'.encode('utf-8'), response.data)

        # Переконуємося, що запису більше немає в БД
        conn = db.get_db()
        deleted_client = conn.execute("SELECT * FROM CLIENTS WHERE id = ?", (client_id,)).fetchone()
        conn.close()
        self.assertIsNone(deleted_client)

    def test_3_7_delete_contact_with_links_blocked(self):
        """3.7 Видалити контакт із пов'язаними заявками (блокування)"""
        self.setup_admin('testpass')
        self.login('testpass')

        conn = db.get_db()
        cursor = conn.cursor()
        # 1. Створюємо клієнта
        cursor.execute("INSERT INTO CLIENTS (full_name) VALUES ('Клієнт із заявкою')")
        client_id = cursor.lastrowid

        # 2. Створюємо прив'язану заявку
        cursor.execute("INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city) VALUES (?, ?, ?)",
                       (client_id, 'Київ', 'Львів'))
        conn.commit()
        conn.close()

        # Спроба видалити
        response = self.client.post(f'/clients/{client_id}/delete', follow_redirects=True)
        html_data = response.data.decode('utf-8')

        # Перевіряємо наявність повідомлення про помилку
        # (враховуємо, що Jinja2 перетворює апостроф на &#39;)
        self.assertIn('Неможливо видалити замовника', html_data)
        self.assertIn('пов&#39;язані заявки!', html_data)

        # Переконуємося, що запис в БД ЗБЕРІГСЯ
        conn = db.get_db()
        client = conn.execute("SELECT * FROM CLIENTS WHERE id = ?", (client_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(client)

    # ==========================================
    # ТЕСТОВІ СЦЕНАРІЇ ДЛЯ ФАЗИ 4 (ЗАЯВКИ ТА ПРОПОЗИЦІЇ)
    # ==========================================

    def setup_data_for_phase4(self):
        """Допоміжний метод: створює замовника та перевізника для тестів 4-ї фази"""
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CLIENTS (full_name) VALUES ('ТОВ Тест Замовник')")
        client_id = cursor.lastrowid
        cursor.execute("INSERT INTO CARRIERS (full_name) VALUES ('ФОП Тест Перевізник')")
        carrier_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return client_id, carrier_id

    def test_4_1_create_cargo_request(self):
        """4.1 Створити заявку (F1)"""
        self.setup_admin('testpass')
        self.login('testpass')
        client_id, _ = self.setup_data_for_phase4()

        response = self.client.post('/requests/add', data={
            'client_id': client_id,
            'origin_city': 'Київ',
            'destination_city': 'Львів',
            'cargo_type': 'Будматеріали',
            'weight_tons': '5.5',
            'desired_date': '2026-06-10',
            'notes': 'Терміново'
        }, follow_redirects=True)

        html = response.data.decode('utf-8')
        self.assertIn('Заявку на перевезення успішно створено!', html)

        # Перевірка в БД (статус 'Нова')
        conn = db.get_db()
        req = conn.execute("SELECT * FROM CARGO_REQUESTS WHERE client_id = ?", (client_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(req)
        self.assertEqual(req['status'], 'Нова')
        self.assertEqual(req['origin_city'], 'Київ')

    def test_4_2_create_carrier_offer(self):
        """4.2 Створити пропозицію (F2)"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, carrier_id = self.setup_data_for_phase4()

        response = self.client.post('/offers/add', data={
            'carrier_id': carrier_id,
            'origin_city': 'Одеса',
            'destination_city': 'Дніпро',
            'vehicle_type': 'Тент',
            'capacity_tons': '22',
            'available_date': '2026-06-12',
            'notes': 'Вільний повністю'
        }, follow_redirects=True)

        self.assertIn('Пропозицію вільного авто успішно опубліковано!', response.data.decode('utf-8'))

        # Перевірка в БД
        conn = db.get_db()
        offer = conn.execute("SELECT * FROM CARRIER_OFFERS WHERE carrier_id = ?", (carrier_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(offer)
        self.assertEqual(offer['destination_city'], 'Дніпро')

    def test_4_3_and_4_4_filter_requests(self):
        """4.3 та 4.4 Фільтрація заявок (статус, маршрут, дата)"""
        self.setup_admin('testpass')
        self.login('testpass')
        client_id, _ = self.setup_data_for_phase4()

        conn = db.get_db()
        conn.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city, desired_date, status) VALUES (?, 'Київ', 'Львів', '2026-06-01', 'Нова')",
            (client_id,))
        conn.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city, desired_date, status) VALUES (?, 'Одеса', 'Дніпро', '2026-06-02', 'В обробці')",
            (client_id,))
        conn.commit()
        conn.close()

        # 4.3 Фільтр за статусом
        resp_status = self.client.get('/requests?status=Нова')
        html_status = resp_status.data.decode('utf-8')
        self.assertIn('Київ &rarr; Львів', html_status)
        self.assertNotIn('Одеса &rarr; Дніпро', html_status)

        # 4.4 Комбінований фільтр (маршрут + дата)
        resp_combo = self.client.get('/requests?origin=Одеса&date=2026-06-02')
        html_combo = resp_combo.data.decode('utf-8')
        self.assertIn('Одеса &rarr; Дніпро', html_combo)
        self.assertNotIn('Київ &rarr; Львів', html_combo)

    def test_4_5_to_4_7_html_validations(self):
        """4.5 - 4.7 Перевірка валідації форм (обов'язкові поля, типи, від'ємні значення)"""
        self.setup_admin('testpass')
        self.login('testpass')

        # Завантажуємо форму створення заявки
        response = self.client.get('/requests/add')
        html = response.data.decode('utf-8')

        # 4.5 Порожні обов'язкові поля блокуються атрибутом required
        self.assertIn('id="origin_city" name="origin_city" required', html)
        self.assertIn('id="destination_city" name="destination_city" required', html)

        # 4.6 Нечислова вага / некоректна дата (перевірка типів полів)
        self.assertIn('type="number"', html)
        self.assertIn('type="date"', html)

        # 4.7 Вага <= 0 блокується атрибутом min="0.1"
        self.assertIn('min="0.1"', html)

    def test_4_8_clear_filters(self):
        """4.8 Скинути фільтри (відновлення списку)"""
        self.setup_admin('testpass')
        self.login('testpass')
        client_id, _ = self.setup_data_for_phase4()

        conn = db.get_db()
        conn.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city) VALUES (?, 'Місто А', 'Місто Б')",
            (client_id,))
        conn.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city) VALUES (?, 'Місто В', 'Місто Г')",
            (client_id,))
        conn.commit()
        conn.close()

        # Фільтруємо так, щоб нічого не знайти (щоб перевірити, що фільтр працює)
        resp_filtered = self.client.get('/requests?origin=Неіснуюче')
        self.assertNotIn('Місто А', resp_filtered.data.decode('utf-8'))

        # Скидаємо фільтри (GET запит без параметрів)
        resp_cleared = self.client.get('/requests')
        html_cleared = resp_cleared.data.decode('utf-8')

        # Усі записи знову відображаються
        self.assertIn('Місто А &rarr; Місто Б', html_cleared)
        self.assertIn('Місто В &rarr; Місто Г', html_cleared)

    # ==========================================
    # ТЕСТОВІ СЦЕНАРІЇ ДЛЯ ФАЗИ 5 (ПІДБІР ТА УГОДИ)
    # ==========================================

    def setup_deal_data(self):
        """Допоміжний метод: створює тестові дані для угод"""
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO CLIENTS (full_name) VALUES ('Клієнт 5')")
        client_id = cursor.lastrowid
        cursor.execute("INSERT INTO CARRIERS (full_name) VALUES ('Перевізник 5')")
        carrier_id = cursor.lastrowid

        # Заявка: 10 тонн, Київ-Львів
        cursor.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city, weight_tons, status) VALUES (?, 'Київ', 'Львів', 10, 'Нова')",
            (client_id,))
        req_id = cursor.lastrowid

        # Ідеальна пропозиція (Підходить)
        cursor.execute(
            "INSERT INTO CARRIER_OFFERS (carrier_id, origin_city, destination_city, capacity_tons, status, vehicle_type) VALUES (?, 'Київ', 'Львів', 20, 'Активна', 'Тент 1')",
            (carrier_id,))
        offer_good_id = cursor.lastrowid

        # Пропозиція з недостатньою вагою (Не підходить)
        cursor.execute(
            "INSERT INTO CARRIER_OFFERS (carrier_id, origin_city, destination_city, capacity_tons, status, vehicle_type) VALUES (?, 'Київ', 'Львів', 5, 'Активна', 'Тент 2')",
            (carrier_id,))

        # Пропозиція з іншим містом (Не підходить)
        cursor.execute(
            "INSERT INTO CARRIER_OFFERS (carrier_id, origin_city, destination_city, capacity_tons, status, vehicle_type) VALUES (?, 'Одеса', 'Львів', 20, 'Активна', 'Тент 3')",
            (carrier_id,))

        conn.commit()
        conn.close()
        return client_id, carrier_id, req_id, offer_good_id

    def test_5_1_and_5_2_match_logic(self):
        """5.1 Підбір для заявки (фільтрація) та 5.2 (порожній список)"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, _, req_id, _ = self.setup_deal_data()

        # Відкриваємо сторінку підбору
        response = self.client.get(f'/requests/{req_id}/match')
        html = response.data.decode('utf-8')

        # 5.1: Має бути лише Тент 1 (бо вага >= 10 і міста збігаються)
        self.assertIn('Тент 1', html)
        self.assertNotIn('Тент 2', html)  # Недостатня вага
        self.assertNotIn('Тент 3', html)  # Інший маршрут

        # 5.2 Перевірка на відсутність пропозицій
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO CARGO_REQUESTS (client_id, origin_city, destination_city, weight_tons, status) VALUES (1, 'Париж', 'Рим', 10, 'Нова')")
        empty_req_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp_empty = self.client.get(f'/requests/{empty_req_id}/match')
        self.assertIn('Не знайдено жодного вільного авто', resp_empty.data.decode('utf-8'))

    def test_5_3_and_5_4_create_deal(self):
        """5.3 Зв'язати заявку й пропозицію та 5.4 Перевірка запису DEALS"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, _, req_id, offer_id = self.setup_deal_data()

        # Відправляємо запит на створення угоди
        response = self.client.post('/deals/create', data={
            'request_id': req_id,
            'offer_id': offer_id,
            'agreed_price': 15000
        }, follow_redirects=True)

        self.assertIn('Угоду створено', response.data.decode('utf-8'))

        # 5.4 Перевірка БД
        conn = db.get_db()
        deal = conn.execute("SELECT * FROM DEALS WHERE request_id = ?", (req_id,)).fetchone()
        req = conn.execute("SELECT status FROM CARGO_REQUESTS WHERE id = ?", (req_id,)).fetchone()
        offer = conn.execute("SELECT status FROM CARRIER_OFFERS WHERE id = ?", (offer_id,)).fetchone()
        conn.close()

        self.assertIsNotNone(deal)
        self.assertEqual(deal['offer_id'], offer_id)
        self.assertEqual(deal['agreed_price'], 15000.0)
        self.assertEqual(deal['status'], 'Нова')

        # 5.3 Перевірка оновлення статусів пов'язаних записів
        self.assertEqual(req['status'], 'В обробці')
        self.assertEqual(offer['status'], 'В обробці')

    def test_5_5_and_5_6_status_transitions(self):
        """5.5 Переходи по статусах та 5.6 Недопустимий перехід"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, _, req_id, offer_id = self.setup_deal_data()

        # Створюємо угоду безпосередньо в БД
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO DEALS (request_id, offer_id, status) VALUES (?, ?, 'Нова')", (req_id, offer_id))
        deal_id = cursor.lastrowid
        conn.commit()

        # 5.5 Дозволений перехід та фіксація дати (Підтверджена)
        self.client.post(f'/deals/{deal_id}', data={'status': 'Підтверджена'})
        deal = conn.execute("SELECT status, confirmed_at FROM DEALS WHERE id = ?", (deal_id,)).fetchone()
        self.assertEqual(deal['status'], 'Підтверджена')
        self.assertIsNotNone(deal['confirmed_at'])  # Дата має проставитись

        # Переводимо в Завершена
        self.client.post(f'/deals/{deal_id}', data={'status': 'Завершена'})
        deal = conn.execute("SELECT status, completed_at FROM DEALS WHERE id = ?", (deal_id,)).fetchone()
        self.assertEqual(deal['status'], 'Завершена')
        self.assertIsNotNone(deal['completed_at'])

        # 5.6 Недопустимий перехід (із Завершеної назад у Нову)
        resp_invalid = self.client.post(f'/deals/{deal_id}', data={'status': 'Нова'}, follow_redirects=True)
        self.assertIn('Неможливо змінити статус закритої або скасованої угоди.', resp_invalid.data.decode('utf-8'))

        # Статус має залишитись "Завершена"
        deal_final = conn.execute("SELECT status FROM DEALS WHERE id = ?", (deal_id,)).fetchone()
        self.assertEqual(deal_final['status'], 'Завершена')
        conn.close()

    def test_5_7_cancel_deal(self):
        """5.7 Скасувати угоду (повернення в пул)"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, _, req_id, offer_id = self.setup_deal_data()

        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO DEALS (request_id, offer_id, status) VALUES (?, ?, 'Нова')", (req_id, offer_id))
        deal_id = cursor.lastrowid
        conn.commit()

        # Скасовуємо угоду
        self.client.post(f'/deals/{deal_id}', data={'status': 'Скасована'})

        # Перевіряємо статуси
        deal = conn.execute("SELECT status FROM DEALS WHERE id = ?", (deal_id,)).fetchone()
        req = conn.execute("SELECT status FROM CARGO_REQUESTS WHERE id = ?", (req_id,)).fetchone()
        offer = conn.execute("SELECT status FROM CARRIER_OFFERS WHERE id = ?", (offer_id,)).fetchone()
        conn.close()

        self.assertEqual(deal['status'], 'Скасована')
        self.assertEqual(req['status'], 'Нова')  # Заявка повернулась в пул
        self.assertEqual(offer['status'], 'Активна')  # Авто повернулось в пул

    def test_5_8_contact_card_history(self):
        """5.8 Картка сторони після угоди (F7)"""
        self.setup_admin('testpass')
        self.login('testpass')
        client_id, _, req_id, offer_id = self.setup_deal_data()

        conn = db.get_db()
        conn.execute(
            "INSERT INTO DEALS (request_id, offer_id, status, agreed_price) VALUES (?, ?, 'Підтверджена', 9999)",
            (req_id, offer_id))
        conn.commit()
        conn.close()

        response = self.client.get(f'/clients/{client_id}')
        html = response.data.decode('utf-8')

        # В історії замовника має відображатись угода (ціна та статус)
        self.assertIn('9999.0', html)
        self.assertIn('Підтверджена', html)

    def test_5_9_prevent_duplicate_deals(self):
        """5.9 Зв'язати вже зайняту пропозицію (блокування дублів)"""
        self.setup_admin('testpass')
        self.login('testpass')
        _, _, req_id, offer_id = self.setup_deal_data()

        # Робимо заявку та пропозицію зайнятими
        conn = db.get_db()
        conn.execute("UPDATE CARGO_REQUESTS SET status = 'В обробці' WHERE id = ?", (req_id,))
        conn.execute("UPDATE CARRIER_OFFERS SET status = 'В обробці' WHERE id = ?", (offer_id,))
        conn.commit()
        conn.close()

        # Намагаємося створити угоду ще раз
        response = self.client.post('/deals/create', data={
            'request_id': req_id,
            'offer_id': offer_id,
            'agreed_price': 1000
        }, follow_redirects=True)

        self.assertIn('Заявка або авто вже зайняті в іншій угоді!', response.data.decode('utf-8'))

        # Переконуємось, що угода не створилась
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) FROM DEALS WHERE request_id = ?", (req_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)