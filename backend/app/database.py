"""
Database connection layer.

Production (Render + Turso):
    Talks to Turso Cloud via its HTTP API using the requests library.
    No Rust compilation required — works on any platform.
    Requires TURSO_URL and TURSO_AUTH_TOKEN env vars.

Development (local):
    Falls back to a local SQLite file when Turso credentials are not set.
"""
import os
import sqlite3

import requests
from werkzeug.security import generate_password_hash

from app.config import Config


# ── Turso HTTP client ──────────────────────────────────────────────────────────

def _use_turso() -> bool:
    return bool(Config.TURSO_URL and Config.TURSO_AUTH_TOKEN)


def _turso_url() -> str:
    """Convert libsql:// URL to https:// for the HTTP API."""
    url = Config.TURSO_URL.strip()
    if url.startswith('libsql://'):
        url = 'https://' + url[len('libsql://'):]
    return url.rstrip('/')


def _cast_value(cell: dict):
    """
    Convert a Turso API cell dict to a native Python type.
    Turso returns: {"type": "integer"|"real"|"text"|"null", "value": "..."}
    """
    if cell is None:
        return None
    t = cell.get('type', 'text')
    v = cell.get('value')
    if t == 'null' or v is None:
        return None
    if t == 'integer':
        try:
            return int(v)
        except (ValueError, TypeError):
            return v
    if t == 'real':
        try:
            return float(v)
        except (ValueError, TypeError):
            return v
    return v  # text, blob — return as-is


class TursoRow:
    """Mimics sqlite3.Row so existing code works unchanged."""
    def __init__(self, columns, values):
        self._columns = [c.lower() for c in columns]
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        try:
            return self._values[self._columns.index(key.lower())]
        except ValueError:
            raise KeyError(f'Column {key!r} not found. Available: {self._columns}')

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._columns

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


class TursoConnection:
    """
    Minimal DB-API 2.0-like wrapper around the Turso HTTP API.
    """

    def __init__(self):
        self._base = _turso_url()
        self._headers = {
            'Authorization': f'Bearer {Config.TURSO_AUTH_TOKEN}',
            'Content-Type': 'application/json',
        }
        self._last_rows = []
        self._last_columns = []
        self.total_changes = 0

    # ── internal ──────────────────────────────────────────────────────────────

    def _build_arg(self, v):
        """Convert a Python value to a Turso typed argument."""
        if v is None:
            return {'type': 'null', 'value': None}
        if isinstance(v, bool):
            return {'type': 'integer', 'value': str(int(v))}
        if isinstance(v, int):
            return {'type': 'integer', 'value': str(v)}
        if isinstance(v, float):
            return {'type': 'real', 'value': str(v)}
        return {'type': 'text', 'value': str(v)}

    def _send(self, statements: list) -> list:
        """Send statements to Turso pipeline API and return result sets."""
        payload = {
            'requests': [
                {
                    'type': 'execute',
                    'stmt': {
                        'sql': s['sql'],
                        'args': [self._build_arg(v) for v in s.get('args', [])],
                    },
                }
                for s in statements
            ] + [{'type': 'close'}]
        }
        resp = requests.post(
            f'{self._base}/v2/pipeline',
            headers=self._headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get('results', []):
            if item.get('type') == 'error':
                raise Exception(item.get('error', {}).get('message', 'Turso error'))
            if item.get('type') == 'ok':
                res = item.get('response', {}).get('result', {})
                cols = [c['name'] for c in res.get('cols', [])]
                rows = [
                    TursoRow(cols, [_cast_value(cell) for cell in row])
                    for row in res.get('rows', [])
                ]
                self.total_changes += res.get('affected_row_count', 0)
                results.append((cols, rows))
        return results

    # ── public API ────────────────────────────────────────────────────────────

    def execute(self, sql: str, args=()):
        results = self._send([{'sql': sql.strip(), 'args': list(args)}])
        if results:
            self._last_columns, self._last_rows = results[0]
        else:
            self._last_columns, self._last_rows = [], []
        return self

    def executescript(self, script: str):
        """Execute multiple semicolon-separated statements."""
        statements = [
            {'sql': s.strip()}
            for s in script.split(';')
            if s.strip()
        ]
        if statements:
            self._send(statements)
        self._last_columns, self._last_rows = [], []
        return self

    def fetchone(self):
        return self._last_rows[0] if self._last_rows else None

    def fetchall(self):
        return list(self._last_rows)

    def commit(self):
        pass   # Turso auto-commits each HTTP request

    def close(self):
        pass   # No persistent connection to close

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_db():
    """
    Return an open database connection.
    Uses Turso HTTP API in production, local SQLite in development.
    """
    if _use_turso():
        return TursoConnection()

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
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_number      TEXT UNIQUE,
            name               TEXT NOT NULL,
            phone              TEXT,
            email              TEXT,
            location           TEXT,
            total_delivered_kg REAL DEFAULT 0,
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            FOREIGN KEY (silo_id)   REFERENCES silos(id)   ON DELETE SET NULL,
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
            FOREIGN KEY (silo_id)    REFERENCES silos(id)         ON DELETE SET NULL,
            FOREIGN KEY (batch_id)   REFERENCES grain_batches(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)         ON DELETE SET NULL
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
        )
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
