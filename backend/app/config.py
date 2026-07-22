import os
from datetime import timedelta


def _setting(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f'{name} must be set in production')
    return value


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    PRODUCTION = bool(os.environ.get('RENDER'))
    SECRET_KEY = _setting(
        'SECRET_KEY',
        None if PRODUCTION else 'local_dev_secret_change_me',
        required=PRODUCTION,
    )
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = PRODUCTION

    # ── Email — SendGrid (HTTPS, works on Render free tier) ───────────────────
    # Set SENDGRID_API_KEY and MAIL_DEFAULT_SENDER in Render environment vars.
    SENDGRID_API_KEY    = _setting('SENDGRID_API_KEY',    '')
    MAIL_DEFAULT_SENDER = _setting('MAIL_DEFAULT_SENDER', '')

    # ── Database ──────────────────────────────────────────────────────────────
    if os.environ.get('RENDER'):
        DB_PATH = os.environ.get('DB_PATH', '/var/data/silo_management.db')
    else:
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               'instance', 'silo_management.db')

    # ── Default admin (used only when seeding an empty DB) ────────────────────
    ADMIN_EMAIL    = _setting('ADMIN_EMAIL',    'admin@localhost.invalid', required=PRODUCTION)
    ADMIN_PASSWORD = _setting('ADMIN_PASSWORD', 'change-me-local',        required=PRODUCTION)
    ADMIN_USERNAME = _setting('ADMIN_USERNAME', 'admin')
