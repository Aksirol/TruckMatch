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


if __name__ == '__main__':
    unittest.main(verbosity=2)