import os
from datetime import timedelta


def _load_local_env():
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        '.env',
    )
    if not os.path.exists(env_path):
        return

    with open(env_path, 'r', encoding='utf-8') as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"\'')
            if value and key not in os.environ:
                os.environ[key] = value


_load_local_env()


def _setting(name, default=None):
    return os.environ.get(name, default)


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = _setting('SECRET_KEY', 'local_dev_secret_change_me')
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE   = bool(_setting('RAILWAY_ENVIRONMENT') or _setting('RENDER'))

    # ── Email — Brevo (smtp-relay.brevo.com) ──────────────────────────────────
    MAIL_SERVER         = _setting('MAIL_SERVER',  'smtp-relay.brevo.com')
    MAIL_PORT           = int(_setting('MAIL_PORT', '587'))
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_USERNAME       = _setting('MAIL_USERNAME',  '')
    MAIL_PASSWORD       = _setting('MAIL_PASSWORD',  '')
    MAIL_DEFAULT_SENDER = _setting('MAIL_DEFAULT_SENDER', '')
    MAIL_DEBUG          = bool(_setting('MAIL_DEBUG', ''))

    # ── Database — Turso (libsql over HTTP) ───────────────────────────────────
    # Set TURSO_URL and TURSO_AUTH_TOKEN in Render dashboard and local .env.
    # Falls back to a local SQLite file for development without Turso credentials.
    TURSO_URL        = _setting('TURSO_URL', '')
    TURSO_AUTH_TOKEN = _setting('TURSO_AUTH_TOKEN', '')

    # Local SQLite fallback path (used when TURSO_URL is not set)
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance', 'silo_management.db',
    )

    # ── Default admin ─────────────────────────────────────────────────────────
    ADMIN_EMAIL    = _setting('ADMIN_EMAIL',    'admin@example.com')
    ADMIN_PASSWORD = _setting('ADMIN_PASSWORD', 'ChangeMe123!')
    ADMIN_USERNAME = _setting('ADMIN_USERNAME', 'admin')
