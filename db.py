# db.py
import sqlite3
import os

DB_PATH = 'truckmatch.db'

def get_db():
    """Створює підключення до бази даних SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Дозволяє звертатися до колонок за іменами
    conn.execute('PRAGMA foreign_keys = ON;') # Важливо для роботи зовнішніх ключів
    return conn

def init_db():
    """Ініціалізує базу даних, створюючи файл та таблиці, якщо вони відсутні або порожні."""
    # Перевіряємо, чи файлу не існує, АБО він абсолютно порожній (0 байт)
    if not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0:
        conn = get_db()
        with open('schema.sql', 'r', encoding='utf-8') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print("База даних успішно створена!")