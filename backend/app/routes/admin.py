import random
import string

from flask import (Blueprint, render_template, redirect,
                   url_for, session, flash, current_app)
from flask_mail import Message

from app.database import get_db
from app.decorators import login_required, admin_required
from app.utils import hash_password, get_base_url, _dispatch_email

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
    from app import mail

    conn    = get_db()
    pending = conn.execute(
        'SELECT * FROM pending_users WHERE id = ?', (user_id,)
    ).fetchone()

    if not pending:
        conn.close()
        return redirect(url_for('admin.admin_pending_users'))

    username = pending['preferred_username']
    role     = pending['requested_role'] or 'staff'

    chars    = string.ascii_letters + string.digits + '!@#$%^&*'
    temp_pwd = ''.join(random.choice(chars) for _ in range(12))

    conn.execute(
        'INSERT INTO users (username, password, email, phone, full_name, role) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (username, hash_password(temp_pwd),
         pending['email'], pending['phone'],
         pending['full_name'], role),
    )
    conn.execute(
        "UPDATE pending_users SET status = 'approved' WHERE id = ?", (user_id,)
    )
    conn.commit()
    conn.close()

    base_url   = get_base_url()
    email_sent = False

    mail_configured = bool(
        current_app.config.get('MAIL_USERNAME') and
        current_app.config.get('MAIL_PASSWORD')
    )

    if mail_configured:
        try:
            email_sent = _dispatch_email(
                'Your Smart Silo Account is Approved',
                [pending['email']],
                f'''
                <html><body style="font-family:Arial,sans-serif;background:#f9fafb;padding:20px;margin:0">
                  <div style="max-width:560px;margin:auto;background:#fff;border-radius:12px;
                              border-top:5px solid #10b981;padding:32px">
                    <h2 style="color:#10b981;margin-top:0">Your Account is Approved!</h2>
                    <p>Dear <strong>{pending['full_name']}</strong>,<br><br>
                       Your Smart Silo System account has been approved.
                       Use the credentials below to log in.</p>
                    <div style="background:#f0fdf4;border:1px solid #a7f3d0;
                                border-radius:10px;padding:20px;margin:20px 0">
                      <table style="width:100%;font-size:15px">
                        <tr>
                          <td style="color:#6b7280;padding:6px 0;width:160px">Username</td>
                          <td><strong>{username}</strong></td>
                        </tr>
                        <tr>
                          <td style="color:#6b7280;padding:6px 0">Temporary Password</td>
                          <td><code style="background:#e5e7eb;padding:3px 8px;
                                           border-radius:5px">{temp_pwd}</code></td>
                        </tr>
                        <tr>
                          <td style="color:#6b7280;padding:6px 0">Role</td>
                          <td>{role.capitalize()}</td>
                        </tr>
                      </table>
                    </div>
                    <p style="color:#d97706;font-size:13px">
                      &#9888; Change your password immediately after first login.
                    </p>
                    <a href="{base_url}/login"
                       style="display:inline-block;background:#10b981;color:white;
                              padding:12px 28px;text-decoration:none;border-radius:8px;
                              font-weight:bold">Login to Smart Silo &rarr;</a>
                    <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
                    <small style="color:#9ca3af">Smart Silo Management System</small>
                  </div>
                </body></html>'''
            )
            print(f'✅ Approval email queued for {pending["email"]}')
        except Exception as exc:
            print(f'❌ Approval email failed: {exc}')

    if email_sent:
        flash(f'✅ {pending["full_name"]} approved as {role}! '
              f'Credentials email queued for {pending["email"]}.', 'success')
    else:
        flash(f'✅ {pending["full_name"]} approved as {role}. '
              f'Username: {username} | Temp password: {temp_pwd} '
              '(Email delivery not queued — share credentials manually)', 'warning')

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

        mail_configured = bool(
            current_app.config.get('MAIL_USERNAME') and
            current_app.config.get('MAIL_PASSWORD')
        )
        if mail_configured:
            try:
                _dispatch_email(
                    'Smart Silo Registration Update',
                    [pending['email']],
                    '''
                    <html><body style="font-family:Arial;padding:20px">
                      <div style="max-width:500px;margin:auto;background:#fff;
                                  border-radius:10px;border-top:5px solid #ef4444;padding:28px">
                        <h2 style="color:#ef4444;margin-top:0">Registration Update</h2>
                        <p>Your registration request has been declined.</p>
                        <p>Please contact the system administrator for more information.</p>
                        <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
                        <small style="color:#9ca3af">Smart Silo Management System</small>
                      </div>
                    </body></html>'''
                )
            except Exception as exc:
                print(f'❌ Rejection email failed: {exc}')

        flash(f'❌ {pending["full_name"]} has been rejected.', 'warning')

    conn.close()
    return redirect(url_for('admin.admin_pending_users'))
