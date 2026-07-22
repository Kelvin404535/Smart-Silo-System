from flask import (Blueprint, redirect, url_for, request,
                   session, render_template, current_app)

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

    ok, err = send_test_email(user['email'])
    if ok:
        return redirect(url_for(
            'alerts.alert_settings',
            message=err,
        ))
    return redirect(url_for(
        'alerts.alert_settings',
        error=f'Failed to send email: {err}',
    ))
