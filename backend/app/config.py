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


def _resolve_db_path():
    """
    Use DB_PATH env var if set AND its parent directory exists (or can be
    created). This handles Render paid (disk mounted at /data) gracefully.
    Falls back to backend/instance/ so the free tier and local dev always work.
    """
    configured = _setting('DB_PATH', '').strip()
    if configured:
        parent = os.path.dirname(configured)
        if not parent:
            return configured
        if os.path.isdir(parent):
            return configured
        # Try to create the parent — succeeds on paid Render, fails on free tier
        try:
            os.makedirs(parent, exist_ok=True)
            return configured
        except (PermissionError, OSError):
            print(f'⚠️  Cannot access {parent} — falling back to instance/ directory.')

    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'instance', 'silo_management.db',
    )


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = _setting('SECRET_KEY', 'local_dev_secret_change_me')
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE   = bool(_setting('RAILWAY_ENVIRONMENT'))

    # ── Email — Brevo (smtp-relay.brevo.com) ──────────────────────────────────
    MAIL_SERVER         = _setting('MAIL_SERVER',  'smtp-relay.brevo.com')
    MAIL_PORT           = int(_setting('MAIL_PORT', '587'))
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_USERNAME       = _setting('MAIL_USERNAME',  '')
    MAIL_PASSWORD       = _setting('MAIL_PASSWORD',  '')
    MAIL_DEFAULT_SENDER = _setting('MAIL_DEFAULT_SENDER', '')
    MAIL_DEBUG          = bool(_setting('MAIL_DEBUG', ''))

    # ── Database ──────────────────────────────────────────────────────────────
    # Render paid: set DB_PATH=/data/silo_management.db + mount disk at /data.
    # Render free / local: falls back to backend/instance/silo_management.db.
    DB_PATH = _resolve_db_path()

    # ── Default admin ─────────────────────────────────────────────────────────
    ADMIN_EMAIL    = _setting('ADMIN_EMAIL',    'admin@example.com')
    ADMIN_PASSWORD = _setting('ADMIN_PASSWORD', 'ChangeMe123!')
    ADMIN_USERNAME = _setting('ADMIN_USERNAME', 'admin')
