"""
Database connection layer.

Production (Render):  connects to Turso Cloud via libsql over HTTP.
                      Requires TURSO_URL and TURSO_AUTH_TOKEN env vars.
Development (local):  falls back to a local SQLite file when those vars
                      are not set, so local dev needs no Turso account.
"""
import os
import sqlite3

from werkzeug.security import generate_password_hash

from app.config import Config


def _use_turso() -> bool:
    """Return True when Turso credentials are available."""
    return bool(Config.TURSO_URL and Config.TURSO_AUTH_TOKEN)


def get_db():
    """
    Return an open database connection with row_factory set to sqlite3.Row.
    Callers must close() the connection when done.
    """
    if _use_turso():
        import libsql
        conn = libsql.connect(
            database=Config.TURSO_URL,
            auth_token=Config.TURSO_AUTH_TOKEN,
        )
        # libsql exposes the same DB-API 2.0 interface as sqlite3
        conn.row_factory = libsql.Row
    else:
        db_dir = os.path.dirname(Config.DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(Config.DB_PATH)
        conn.row_factory = sqlite3.Row

    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    """Create all tables if they don't exist, then seed a default admin."""
    if not _use_turso():
        db_dir = os.path.dirname(Config.DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    conn = get_db()

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            email       TEXT UNIQUE,
            phone       TEXT,
            role        TEXT DEFAULT 'staff',
            full_name   TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS silos (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            silo_number      TEXT UNIQUE NOT NULL,
            location         TEXT,
            capacity_kg      REAL DEFAULT 0,
            current_stock_kg REAL DEFAULT 0,
            grain_type       TEXT,
            sensor_id        TEXT,
            status           TEXT DEFAULT 'active',
            deleted_at       TIMESTAMP,
            deleted_by       INTEGER,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deleted_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS farmers (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_number     TEXT UNIQUE,
            name              TEXT NOT NULL,
            phone             TEXT,
            email             TEXT,
            location          TEXT,
            total_delivered_kg REAL DEFAULT 0,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS grain_batches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_number TEXT UNIQUE,
            silo_id      INTEGER,
            grain_type   TEXT,
            quantity_kg  REAL,
            moisture     REAL,
            entry_date   DATE,
            farmer_id    INTEGER,
            status       TEXT DEFAULT 'active',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (silo_id) REFERENCES silos(id) ON DELETE SET NULL,
            FOREIGN KEY (farmer_id) REFERENCES farmers(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            silo_id          INTEGER,
            batch_id         INTEGER,
            transaction_type TEXT,
            quantity_kg      REAL,
            transaction_date DATE,
            notes            TEXT,
            created_by       INTEGER,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (silo_id) REFERENCES silos(id) ON DELETE SET NULL,
            FOREIGN KEY (batch_id) REFERENCES grain_batches(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            silo_id    INTEGER,
            alert_type TEXT,
            severity   TEXT,
            message    TEXT,
            is_read    BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (silo_id) REFERENCES silos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS pending_users (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name          TEXT,
            email              TEXT UNIQUE,
            phone              TEXT,
            preferred_username TEXT UNIQUE,
            requested_role     TEXT,
            status             TEXT DEFAULT 'pending',
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS password_resets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT,
            token      TEXT,
            expiry     TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    # Migrate: add soft-delete columns to silos for older DBs
    for col, typedef in [('deleted_at', 'TIMESTAMP'), ('deleted_by', 'INTEGER')]:
        try:
            conn.execute(f'ALTER TABLE silos ADD COLUMN {col} {typedef}')
            conn.commit()
        except Exception:
            pass

    # Seed default admin if none exists
    admin = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()

    if not admin:
        conn.execute(
            "INSERT INTO users (username, password, email, role, full_name) "
            "VALUES (?, ?, ?, 'admin', 'System Admin')",
            (
                Config.ADMIN_USERNAME,
                generate_password_hash(Config.ADMIN_PASSWORD),
                Config.ADMIN_EMAIL,
            ),
        )
        conn.commit()
        print(f'✅ Default admin created — '
              f'email: {Config.ADMIN_EMAIL}  '
              f'password: {Config.ADMIN_PASSWORD}')
        print('   ⚠️  Change the password immediately after first login!')

    conn.commit()
    conn.close()
    mode = 'Turso Cloud' if _use_turso() else f'SQLite ({Config.DB_PATH})'
    print(f'✅ Database ready — {mode}')


def rebuild_db():
    """Drop and recreate the database schema from scratch."""
    if not _use_turso():
        if not os.path.exists(os.path.dirname(Config.DB_PATH)):
            os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
        if os.path.exists(Config.DB_PATH):
            os.remove(Config.DB_PATH)
    init_db()


if __name__ == '__main__':
    print('Rebuilding the database schema...')
    rebuild_db()
    print('Database rebuild complete.')
