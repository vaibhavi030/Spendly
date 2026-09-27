import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = "spendly.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            monthly_budget REAL NOT NULL DEFAULT 12000,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Create a demo account on first run so the project opens immediately.
    user = conn.execute(
        "SELECT id FROM users LIMIT 1"
    ).fetchone()

    if user is None:
        cursor = conn.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
            """,
            (
                "Vaibhavi",
                "vaibhavi@example.com",
                generate_password_hash("password"),
            )
        )
        user_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO budgets (user_id, monthly_budget)
            VALUES (?, ?)
            """,
            (user_id, 12000)
        )
    else:
        user_id = user["id"]

        budget = conn.execute(
            "SELECT id FROM budgets WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if budget is None:
            conn.execute(
                """
                INSERT INTO budgets (user_id, monthly_budget)
                VALUES (?, ?)
                """,
                (user_id, 12000)
            )

    conn.commit()
    conn.close()
