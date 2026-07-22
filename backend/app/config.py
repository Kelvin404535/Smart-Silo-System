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

    # ── Email (set these env vars in Render or production) ────────────────
    MAIL_SERVER         = _setting('MAIL_SERVER', 'smtp.gmail.com', required=PRODUCTION)
    MAIL_PORT           = int(_setting('MAIL_PORT', '587', required=PRODUCTION))
    MAIL_USE_TLS        = _setting('MAIL_USE_TLS', 'True', required=PRODUCTION).strip().lower() in ('true', '1', 'yes')
    MAIL_USE_SSL        = _setting('MAIL_USE_SSL', 'False', required=PRODUCTION).strip().lower() in ('true', '1', 'yes')
    MAIL_USERNAME       = _setting('MAIL_USERNAME', None if PRODUCTION else '', required=PRODUCTION)
    MAIL_PASSWORD       = _setting('MAIL_PASSWORD', None if PRODUCTION else '', required=PRODUCTION)
    MAIL_DEFAULT_SENDER = _setting('MAIL_DEFAULT_SENDER', None if PRODUCTION else '', required=PRODUCTION)
    MAIL_DEBUG          = False   # set True only during local debugging

    # ── Database ──────────────────────────────────────────────────────────────
    # Render mounts a persistent disk at /var/data; locally the instance/ folder is used.
    if os.environ.get('RENDER'):
        DB_PATH = os.environ.get('DB_PATH', '/var/data/silo_management.db')
    else:
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               'instance', 'silo_management.db')

    # ── Default admin (used only when seeding an empty DB) ────────────────────
    ADMIN_EMAIL    = _setting('ADMIN_EMAIL', 'admin@localhost.invalid', required=PRODUCTION)
    ADMIN_PASSWORD = _setting('ADMIN_PASSWORD', 'change-me-local', required=PRODUCTION)
    ADMIN_USERNAME = _setting('ADMIN_USERNAME', 'admin')
