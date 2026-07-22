"""
Shared helpers: password validation, risk calculation, alert logic, email.
"""
import re
import threading
from datetime import datetime

from flask import request
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
                f"Too many failed attempts. Try again after {minutes}m {seconds}s."
            ), _locked_accounts[identifier]
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


# ── Resend email helper ───────────────────────────────────────────────────────

def _resend_send(api_key: str, from_email: str, recipients: list,
                 subject: str, html_body: str):
    """
    Send an email via Resend HTTP API (https://resend.com).
    Returns (True, None) on success or (False, error_str) on failure.
    Uses only stdlib urllib — no extra package needed at call time.
    """
    import json
    import urllib.request
    import urllib.error

    payload = {
        'from':    from_email,
        'to':      recipients,
        'subject': subject,
        'html':    html_body,
    }
    data = json.dumps(payload).encode('utf-8')
    req  = urllib.request.Request(
        'https://api.resend.com/emails',
        data    = data,
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type':  'application/json',
        },
        method  = 'POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f'✅ Resend accepted email for {recipients} (HTTP {resp.status})')
            return True, None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        msg  = f'Resend HTTP {exc.code}: {body}'
        print(f'❌ {msg}')
        return False, msg
    except Exception as exc:
        print(f'❌ Resend error ({type(exc).__name__}): {exc}')
        return False, str(exc)


def _dispatch_email(recipients: list, subject: str, html_body: str):
    """
    Fire email in a non-daemon background thread so it never blocks a request.
    """
    from flask import current_app
    api_key    = current_app.config.get('RESEND_API_KEY', '')
    from_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')

    if not api_key:
        print('⚠️  RESEND_API_KEY not set — email skipped.')
        return
    if not from_email:
        print('⚠️  MAIL_DEFAULT_SENDER not set — email skipped.')
        return

    def _run():
        _resend_send(api_key, from_email, recipients, subject, html_body)

    t = threading.Thread(target=_run, daemon=False)
    t.start()


# ── Alert HTML template ───────────────────────────────────────────────────────

def _alert_html(label: str, colour: str, silo_number: str, message: str) -> str:
    return f'''
    <html><body style="font-family:Arial,sans-serif;background:#f9fafb;padding:20px">
      <div style="max-width:600px;margin:auto;background:#fff;border-radius:10px;
                  border-top:5px solid {colour};padding:30px">
        <h2 style="color:{colour};margin-top:0">&#9888; {label} &mdash; Silo {silo_number}</h2>
        <p style="font-size:16px">{message}</p>
        <hr style="border:none;border-top:1px solid #e5e7eb">
        <small style="color:#6b7280">Smart Silo Management System &mdash; automated alert</small>
      </div>
    </body></html>'''


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
    from flask import current_app

    print('🔍 Checking silos for risks...')
    try:
        conn = get_db()

        recipient_rows = conn.execute(
            "SELECT email FROM users WHERE email IS NOT NULL AND email != ''"
        ).fetchall()
        recipients = [r['email'] for r in recipient_rows]

        silos = conn.execute('''
            SELECT s.*,
                   COALESCE(
                       (SELECT moisture FROM grain_batches
                        WHERE silo_id = s.id ORDER BY entry_date DESC LIMIT 1), 0
                   ) AS moisture,
                   (SELECT entry_date FROM grain_batches
                    WHERE silo_id = s.id ORDER BY entry_date DESC LIMIT 1
                   ) AS entry_date
            FROM silos s WHERE s.status = "active"
        ''').fetchall()

        mail_configured = bool(current_app.config.get('SENDGRID_API_KEY'))
        if not mail_configured:
            print('⚠️  SENDGRID_API_KEY not set — alerts saved to DB only.')

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
            silo_num = silo['silo_number']

            if moisture > 14 or days > 90:
                if moisture > 14:
                    msg = f'CRITICAL: Silo {silo_num} has {moisture}% moisture (limit: 14%)'
                    saved = save_alert_to_db(silo['id'], 'high_moisture', 'critical', msg)
                    created += saved
                    if saved and mail_configured and recipients:
                        _dispatch_email(
                            recipients,
                            f'CRITICAL: High Moisture - Silo {silo_num}',
                            _alert_html('CRITICAL ALERT', '#ef4444', silo_num, msg))
                if days > 90:
                    msg = f'CRITICAL: Silo {silo_num} grain stored for {days} days (limit: 90)'
                    saved = save_alert_to_db(silo['id'], 'storage_age', 'critical', msg)
                    created += saved
                    if saved and mail_configured and recipients:
                        _dispatch_email(
                            recipients,
                            f'CRITICAL: Long Storage - Silo {silo_num}',
                            _alert_html('CRITICAL ALERT', '#ef4444', silo_num, msg))

            elif moisture > 12.5 or days > 60:
                if moisture > 12.5:
                    msg = f'WARNING: Silo {silo_num} has {moisture}% moisture (limit: 12.5%)'
                    saved = save_alert_to_db(silo['id'], 'high_moisture', 'warning', msg)
                    created += saved
                    if saved and mail_configured and recipients:
                        _dispatch_email(
                            recipients,
                            f'WARNING: High Moisture - Silo {silo_num}',
                            _alert_html('WARNING', '#f59e0b', silo_num, msg))
                if days > 60:
                    msg = f'WARNING: Silo {silo_num} grain stored for {days} days (limit: 60)'
                    saved = save_alert_to_db(silo['id'], 'storage_age', 'warning', msg)
                    created += saved
                    if saved and mail_configured and recipients:
                        _dispatch_email(
                            recipients,
                            f'WARNING: Long Storage - Silo {silo_num}',
                            _alert_html('WARNING', '#f59e0b', silo_num, msg))

            if 0 < stock and pct < 10:
                msg = f'LOW STOCK: Silo {silo_num} has {stock}kg remaining ({pct:.1f}% capacity)'
                saved = save_alert_to_db(silo['id'], 'low_stock', 'warning', msg)
                created += saved
                if saved and mail_configured and recipients:
                    _dispatch_email(
                        recipients,
                        f'WARNING: Low Stock - Silo {silo_num}',
                        _alert_html('WARNING', '#f59e0b', silo_num, msg))

        conn.close()
        print(f'✅ Alert check complete. {created} alerts created.')
    except Exception as exc:
        print(f'❌ Alert check error: {exc}')


# ── Test email ────────────────────────────────────────────────────────────────

def send_test_email(recipient: str):
    """
    Send a test email via Resend synchronously.
    Returns (True, None) on success or (False, error_str) on failure.
    """
    from flask import current_app
    api_key    = current_app.config.get('RESEND_API_KEY', '')
    from_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')

    if not api_key:
        return False, 'RESEND_API_KEY is not set in Render environment variables.'
    if not from_email:
        return False, 'MAIL_DEFAULT_SENDER is not set in Render environment variables.'

    html = '''
    <html><body style="font-family:Arial">
    <div style="padding:20px;background:#f0fdf4;border-radius:10px">
        <h2 style="color:#10b981">&#10003; Test Alert</h2>
        <p>Your Smart Silo alert system is working correctly!</p>
        <ul>
            <li>&#128308; Critical: moisture &gt;14% or storage &gt;90 days</li>
            <li>&#128993; Warning: moisture &gt;12.5% or storage &gt;60 days</li>
            <li>&#128230; Low stock: less than 10% capacity</li>
        </ul>
        <hr><small>Smart Silo Management System</small>
    </div></body></html>'''

    print(f'📧 Sending test email to {recipient} via Resend...')
    return _resend_send(api_key, from_email, [recipient],
                        'Test Alert - Smart Silo System', html)


# ── URL helper ────────────────────────────────────────────────────────────────

def get_base_url() -> str:
    """Return the public base URL (works locally and on Render)."""
    try:
        host = request.host
        if host.startswith(('127.0.0.1', 'localhost')):
            return 'http://localhost:5000'
        return f'https://{host}'
    except RuntimeError:
        return 'http://localhost:5000'
