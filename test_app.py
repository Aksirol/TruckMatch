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


if __name__ == '__main__':
    unittest.main(verbosity=2)