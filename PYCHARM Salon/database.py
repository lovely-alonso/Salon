import sqlite3
from werkzeug.security import generate_password_hash

DB_NAME = "salon.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # USERS TABLE (1 admin + unlimited customers)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'customer'))
        )
    """)

    # INSERT DEFAULT ADMIN (only added once)
    cur.execute("SELECT * FROM users WHERE role='admin'")
    admin_exists = cur.fetchone()
    if not admin_exists:
        hashed_password = generate_password_hash('admin123')
        cur.execute("""
            INSERT INTO users (username, password, role)
            VALUES ('admin', ?, 'admin')
        """, (hashed_password,))

    # APPOINTMENTS TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            name TEXT,
            phone TEXT,
            gender TEXT,
            service TEXT,
            appointment_time TEXT,
            message TEXT,
            cart TEXT,
            total REAL,
            status TEXT DEFAULT 'Upcoming',
            FOREIGN KEY(customer_id) REFERENCES users(id)
        )
    """)

    # REVIEWS TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            name TEXT,
            rating INTEGER,
            comment TEXT,
            date TEXT,
            FOREIGN KEY(customer_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
