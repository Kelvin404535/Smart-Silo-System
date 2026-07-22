from flask import Blueprint, redirect, url_for, request, session

from app.database import get_db
from app.decorators import login_required
from app.utils import send_test_email

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/alert-settings', methods=['GET', 'POST'])
@login_required
def alert_settings():
    from flask import render_template
    from app import mail

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
    from flask import current_app

    # Surface missing config immediately so it shows on screen
    missing = [k for k in ('MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER')
               if not current_app.config.get(k)]
    if missing:
        return redirect(url_for(
            'alerts.alert_settings',
            error=f"Email not configured on server. Missing: {', '.join(missing)}",
        ))

    conn = get_db()
    user = conn.execute(
        'SELECT email FROM users WHERE id = ?', (session['user_id'],)
    ).fetchone()
    conn.close()

    if not user or not user['email']:
        return redirect(url_for(
            'alerts.alert_settings',
            error='No email configured. Add your email in settings first.',
        ))

    ok, err_msg = send_test_email(mail, user['email'])
    if ok:
        return redirect(url_for(
            'alerts.alert_settings',
            message='Test email sent successfully! Check your inbox.',
        ))
    return redirect(url_for(
        'alerts.alert_settings',
        error=f'Failed to send email: {err_msg}',
    ))
