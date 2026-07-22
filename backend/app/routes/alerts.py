from flask import Blueprint, redirect, url_for, request, session, render_template, current_app

from app.database import get_db
from app.decorators import login_required
from app.utils import send_test_email

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/alert-settings', methods=['GET', 'POST'])
@login_required
def alert_settings():
    message = request.args.get('message')
    error   = request.args.get('error')

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        conn  = get_db()
        conn.execute(
            'UPDATE users SET email = ?, phone = ? WHERE id = ?',
            (email, phone, session['user_id']),
        )
        conn.commit()
        conn.close()
        message = 'Settings saved!'

    conn = get_db()
    user = conn.execute(
        'SELECT email, phone FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    conn.close()
    return render_template('alert_settings.html',
                           user=user, message=message, error=error)


@alerts_bp.route('/send-test-alert')
@login_required
def send_test_alert():
    from app import mail

    # Check env vars are set
    missing = [k for k in ('MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER')
               if not current_app.config.get(k)]
    if missing:
        return redirect(url_for(
            'alerts.alert_settings',
            error=f"Email not configured. Missing env vars: {', '.join(missing)}",
        ))

    conn = get_db()
    user = conn.execute(
        'SELECT email FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    conn.close()

    if not user or not user['email']:
        return redirect(url_for(
            'alerts.alert_settings',
            error='No email saved. Enter your email above and click Save Settings first.',
        ))

    # Send directly (synchronous) — fast enough for a single email, no thread needed
    print(f'📧 Test email queued for {user["email"]}')
    ok, err = send_test_email(mail, user['email'])
    if ok:
        return redirect(url_for(
            'alerts.alert_settings',
            message='Test email sent! Check your inbox.',
        ))
    return redirect(url_for(
        'alerts.alert_settings',
        error=f'Failed to send email: {err}',
    ))
