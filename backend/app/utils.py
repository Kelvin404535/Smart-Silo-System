"""
Shared helpers: password validation, risk calculation, alert logic, email.
"""
import re
from datetime import datetime

from flask import request
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash


# ── Password helpers ──────────────────────────────────────────────────────────

def is_strong_password(password: str):
    """Return (True, 'Strong') or (False, reason)."""
    checks = [
        (len(password) >= 8,                        'At least 8 characters required'),
        (bool(re.search(r'[A-Z]', password)),        'Need 1 uppercase letter'),
        (bool(re.search(r'[a-z]', password)),        'Need 1 lowercase letter'),
        (bool(re.search(r'[0-9]', password)),        'Need 1 number'),
        (bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
         'Need 1 special character'),
    ]
    for ok, msg in checks:
        if not ok:
            return False, msg
    return True, 'Strong password'


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return check_password_hash(hashed, password)


# ── Account lockout ───────────────────────────────────────────────────────────

_failed_attempts: dict = {}
_locked_accounts: dict = {}


def check_account_lockout(identifier: str):
    from datetime import timedelta
    if identifier in _locked_accounts:
        remaining = _locked_accounts[identifier] - datetime.now()
        if remaining.total_seconds() > 0:
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            return True, (
                f"Too many failed attempts. Try again after {minutes}m {seconds}s."), _locked_accounts[identifier]
        # Lock expired — clean up
        del _locked_accounts[identifier]
        _failed_attempts.pop(identifier, None)
    return False, None, None


def record_failed_attempt(identifier: str):
    from datetime import timedelta
    now = datetime.now()
    if identifier in _locked_accounts and now < _locked_accounts[identifier]:
        _locked_accounts[identifier] = _locked_accounts[identifier] + timedelta(minutes=5)
        return

    _failed_attempts[identifier] = _failed_attempts.get(identifier, 0) + 1
    if _failed_attempts[identifier] >= 5:
        _locked_accounts[identifier] = now + timedelta(minutes=2)
        _failed_attempts.pop(identifier, None)


def reset_failed_attempts(identifier: str):
    _failed_attempts.pop(identifier, None)
    _locked_accounts.pop(identifier, None)


# ── Risk calculation ──────────────────────────────────────────────────────────

def calculate_risk(moisture, days_stored):
    """Return (colour, message) where colour is 'red'|'yellow'|'green'|'gray'."""
    if not moisture:
        return 'gray', 'No data entered'
    if moisture > 14 or days_stored > 90:
        return 'red',    f'CRITICAL: {moisture}% moisture, {days_stored} days'
    if moisture > 12.5 or days_stored > 60:
        return 'yellow', f'WARNING: {moisture}% moisture, {days_stored} days'
    return 'green',  f'SAFE: {moisture}% moisture, {days_stored} days'


# ── Alert persistence ─────────────────────────────────────────────────────────

def save_alert_to_db(silo_id, alert_type, severity, message):
    from app.database import get_db
    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM alerts "
            "WHERE silo_id = ? AND alert_type = ? AND severity = ? "
            "AND is_read = 0 LIMIT 1",
            (silo_id, alert_type, severity),
        ).fetchone()
        if existing:
            conn.close()
            return False
        conn.execute(
            "INSERT INTO alerts (silo_id, alert_type, severity, message, is_read) "
            "VALUES (?, ?, ?, ?, 0)",
            (silo_id, alert_type, severity, message),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f'❌ Alert save error: {exc}')
        return False


def check_and_send_alerts():
    from app.database import get_db
    print('🔍 Checking silos for risks...')
    try:
        conn = get_db()
        silos = conn.execute('''
            SELECT s.*,
                   COALESCE(
                       (SELECT moisture   FROM grain_batches
                        WHERE silo_id = s.id ORDER BY entry_date DESC LIMIT 1), 0
                   ) AS moisture,
                   (SELECT entry_date FROM grain_batches
                    WHERE silo_id = s.id ORDER BY entry_date DESC LIMIT 1
                   ) AS entry_date
            FROM silos s WHERE s.status = "active"
        ''').fetchall()

        created = 0
        for silo in silos:
            days = 0
            if silo['entry_date']:
                try:
                    days = (
                        datetime.now() -
                        datetime.strptime(silo['entry_date'], '%Y-%m-%d')
                    ).days
                except Exception:
                    pass

            moisture = silo['moisture'] or 0
            capacity = silo['capacity_kg'] or 0
            stock    = silo['current_stock_kg'] or 0
            pct      = (stock / capacity * 100) if capacity > 0 else 100

            if moisture > 14 or days > 90:
                if moisture > 14:
                    created += save_alert_to_db(
                        silo['id'], 'high_moisture', 'critical',
                        f'CRITICAL: {moisture}% moisture')
                if days > 90:
                    created += save_alert_to_db(
                        silo['id'], 'storage_age', 'critical',
                        f'CRITICAL: grain stored for {days} days')
            elif moisture > 12.5 or days > 60:
                if moisture > 12.5:
                    created += save_alert_to_db(
                        silo['id'], 'high_moisture', 'warning',
                        f'WARNING: {moisture}% moisture')
                if days > 60:
                    created += save_alert_to_db(
                        silo['id'], 'storage_age', 'warning',
                        f'WARNING: grain stored for {days} days')

            if 0 < stock and pct < 10:
                created += save_alert_to_db(
                    silo['id'], 'low_stock', 'warning',
                    f'LOW STOCK: {stock}kg remaining ({pct:.1f}% capacity)')

        conn.close()
        print(f'✅ Alert check complete. {created} alerts created.')
    except Exception as exc:
        print(f'❌ Alert check error: {exc}')


# ── Email helpers ─────────────────────────────────────────────────────────────

def get_base_url() -> str:
    """Return the public base URL (works locally and on Render)."""
    try:
        host = request.host
        if host.startswith(('127.0.0.1', 'localhost')):
            return 'http://localhost:5000'
        return f'https://{host}'
    except RuntimeError:
        return 'http://localhost:5000'


def send_test_email(mail, recipient: str) -> bool:
    try:
        msg = Message('Test Alert - Smart Silo System', recipients=[recipient])
        msg.html = '''
        <html><body style="font-family:Arial">
        <div style="padding:20px;background:#f0fdf4;border-radius:10px">
            <h2 style="color:#10b981">✅ Test Alert</h2>
            <p>Your Smart Silo alert system is working correctly!</p>
            <ul>
                <li>🔴 Critical: moisture &gt;14% or storage &gt;90 days</li>
                <li>🟡 Warning: moisture &gt;12.5% or storage &gt;60 days</li>
                <li>📦 Low stock: less than 10% capacity</li>
            </ul>
            <hr><small>Smart Silo Management System</small>
        </div></body></html>'''
        mail.send(msg)
        return True
    except Exception as exc:
        print(f'Email error: {exc}')
        return False
