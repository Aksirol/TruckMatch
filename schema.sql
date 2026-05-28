-- schema.sql

-- Увімкнення підтримки зовнішніх ключів у SQLite
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS USERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CLIENTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CARRIERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    vehicle_type TEXT,
    capacity_tons REAL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS CARGO_REQUESTS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL,
    origin_city TEXT NOT NULL,
    destination_city TEXT NOT NULL,
    cargo_type TEXT,
    weight_tons REAL,
    desired_date DATE,
    status TEXT DEFAULT 'Нова',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES CLIENTS(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS CARRIER_OFFERS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL,
    origin_city TEXT NOT NULL,
    destination_city TEXT NOT NULL,
    vehicle_type TEXT,
    capacity_tons REAL,
    available_date DATE,
    status TEXT DEFAULT 'Активна',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (carrier_id) REFERENCES CARRIERS(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS DEALS (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    offer_id INTEGER NOT NULL,
    status TEXT DEFAULT 'В обробці',
    agreed_price REAL,
    confirmed_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (request_id) REFERENCES CARGO_REQUESTS(id) ON DELETE CASCADE,
    FOREIGN KEY (offer_id) REFERENCES CARRIER_OFFERS(id) ON DELETE CASCADE
);