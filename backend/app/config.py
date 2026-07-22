import os
from datetime import timedelta


def _setting(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f'{name} must be set in production')
    return value


class Config:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY = _setting('SECRET_KEY', 'local_dev_secret_change_me')
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE   = False   # set True if behind HTTPS proxy

    # ── Email — Gmail SMTP (works on PythonAnywhere free tier) ───────────────
    # Set these as environment variables in PythonAnywhere or a .env file.
    MAIL_SERVER         = _setting('MAIL_SERVER',  'smtp.gmail.com')
    MAIL_PORT           = int(_setting('MAIL_PORT', '587'))
    MAIL_USE_TLS        = True
    MAIL_USE_SSL        = False
    MAIL_USERNAME       = _setting('MAIL_USERNAME',  '')   # your Gmail address
    MAIL_PASSWORD       = _setting('MAIL_PASSWORD',  '')   # Gmail App Password
    MAIL_DEFAULT_SENDER = _setting('MAIL_DEFAULT_SENDER', '')

    # ── Database ──────────────────────────────────────────────────────────────
    # PythonAnywhere: set DB_PATH env var to an absolute path under /home/<user>/
    DB_PATH = _setting(
        'DB_PATH',
        os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     'instance', 'silo_management.db'),
    )

    # ── Default admin (used only when seeding an empty DB) ────────────────────
    ADMIN_EMAIL    = _setting('ADMIN_EMAIL',    'admin@example.com')
    ADMIN_PASSWORD = _setting('ADMIN_PASSWORD', 'ChangeMe123!')
    ADMIN_USERNAME = _setting('ADMIN_USERNAME', 'admin')
