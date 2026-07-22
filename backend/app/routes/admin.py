import random
import string

from flask import (Blueprint, render_template, redirect,
                   url_for, session, flash, current_app)

from app.database import get_db
from app.decorators import login_required, admin_required
from app.utils import hash_password, get_base_url, _resend_send

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin-pending-users')
@login_required
@admin_required
def admin_pending_users():
    conn    = get_db()
    pending = conn.execute(
        "SELECT * FROM pending_users WHERE status = 'pending' "
        'ORDER BY created_at DESC'
    ).fetchall()
    conn.close()
    return render_template('admin_pending_users.html', pending_users=pending)


@admin_bp.route('/approve-user/<int:user_id>')
@login_required
@admin_required
def approve_user(user_id):
    conn    = get_db()
    pending = conn.execute(
        'SELECT * FROM pending_users WHERE id = ?', (user_id,)
    ).fetchone()

    if not pending:
        conn.close()
        return redirect(url_for('admin.admin_pending_users'))

    # Generate worker number
    last = conn.execute(
        "SELECT username FROM users WHERE username LIKE 'WK-%' "
        'ORDER BY id DESC LIMIT 1'
    ).fetchone()
    num    = int(last['username'].split('-')[1]) + 1 if last else 1
    worker = f'WK-{num:04d}'

    chars    = string.ascii_letters + string.digits + '!@#$%^&*'
    temp_pwd = ''.join(random.choice(chars) for _ in range(12))

    conn.execute(
        'INSERT INTO users (username, password, email, phone, full_name, role) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (worker, hash_password(temp_pwd),
         pending['email'], pending['phone'],
         pending['full_name'], pending['requested_role']),
    )
    conn.execute(
        "UPDATE pending_users SET status = 'approved' WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()

    base_url   = get_base_url()
    api_key    = current_app.config.get('RESEND_API_KEY', '')
    from_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')
    email_sent = False

    if api_key and from_email:
        html = f'''
        <div style="font-family:Arial;padding:20px;background:#f0fdf4;border-radius:10px">
            <h2 style="color:#10b981">Welcome to Smart Silo System!</h2>
            <p>Dear <strong>{pending['full_name']}</strong>, your account has been approved.</p>
            <div style="background:white;padding:15px;border-radius:8px;margin:15px 0">
                <p><strong>Worker Number:</strong> {worker}</p>
                <p><strong>Temporary Password:</strong> <code>{temp_pwd}</code></p>
                <p><strong>Email:</strong> {pending['email']}</p>
            </div>
            <p style="color:#e67e22">Change your password after first login.</p>
            <a href="{base_url}/login">Login here</a>
        </div>'''
        ok, err = _resend_send(
            api_key, from_email, [pending['email']],
            'Account Approved - Smart Silo System', html)
        email_sent = ok
        if not ok:
            print(f'❌ Approval email failed: {err}')

    if email_sent:
        flash(f'✅ {pending["full_name"]} approved! Credentials sent to '
              f'{pending["email"]}', 'success')
    else:
        flash(f'✅ {pending["full_name"]} approved! '
              f'Worker: {worker}  Temp password: {temp_pwd}  '
              '(Email not sent — share credentials manually)', 'warning')

    return redirect(url_for('admin.admin_pending_users'))


@admin_bp.route('/reject-user/<int:user_id>')
@login_required
@admin_required
def reject_user(user_id):
    conn    = get_db()
    pending = conn.execute(
        'SELECT * FROM pending_users WHERE id = ?', (user_id,)
    ).fetchone()

    if pending:
        conn.execute(
            "UPDATE pending_users SET status = 'rejected' WHERE id = ?",
            (user_id,),
        )
        conn.commit()

        api_key    = current_app.config.get('RESEND_API_KEY', '')
        from_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')
        if api_key and from_email:
            _resend_send(
                api_key, from_email, [pending['email']],
                'Account Update - Smart Silo System',
                '<p>Your registration has been declined. '
                'Please contact the administrator.</p>')

    conn.close()
    return redirect(url_for('admin.admin_pending_users'))
