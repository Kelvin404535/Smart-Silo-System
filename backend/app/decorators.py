"""
Route decorators: login_required, admin_required.
"""
from functools import wraps
from flask import session, redirect, url_for


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            return 'Access Denied', 403
        return f(*args, **kwargs)
    return decorated
