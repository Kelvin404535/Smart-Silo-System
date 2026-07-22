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

    # Use the preferred username they registered with
    username = pending['preferred_username']
    role     = pending['requested_role'] or 'staff'

    # Generate a secure temporary password
    chars    = string.ascii_letters + string.digits + '!@#$%^&*'
    temp_pwd = ''.join(random.choice(chars) for _ in range(12))

    # Create the user account with the correct role
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
    api_key    = current_app.config.get('RESEND_API_KEY', '')
    from_email = current_app.config.get('MAIL_DEFAULT_SENDER', '')
    email_sent = False

    if not api_key:
        print('⚠️  RESEND_API_KEY not set — approval email skipped.')
    elif not from_email:
        print('⚠️  MAIL_DEFAULT_SENDER not set — approval email skipped.')

    if api_key and from_email:
        print(f'📧 Sending approval email to {pending["email"]} (api_key set: {bool(api_key)}, from: {from_email})...')
        role_label = role.capitalize()
        html = f'''
        <html><body style="font-family:Arial,sans-serif;background:#f9fafb;padding:20px;margin:0">
          <div style="max-width:560px;margin:auto;background:#ffffff;border-radius:12px;
                      border-top:5px solid #10b981;padding:32px;box-shadow:0 4px 20px rgba(0,0,0,0.08)">

            <h2 style="color:#10b981;margin-top:0">Your Account is Approved!</h2>
            <p style="color:#374151;font-size:15px">
              Dear <strong>{pending['full_name']}</strong>,<br><br>
              Your Smart Silo System account has been approved.
              Use the credentials below to log in.
            </p>

            <div style="background:#f0fdf4;border:1px solid #a7f3d0;border-radius:10px;
                        padding:20px;margin:20px 0">
              <table style="width:100%;border-collapse:collapse;font-size:15px">
                <tr>
                  <td style="padding:6px 0;color:#6b7280;width:140px">Username</td>
                  <td style="padding:6px 0;color:#111827"><strong>{username}</strong></td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b7280">Temporary Password</td>
                  <td style="padding:6px 0">
                    <code style="background:#e5e7eb;padding:3px 8px;border-radius:5px;
                                 font-size:14px;color:#111827">{temp_pwd}</code>
                  </td>
                </tr>
                <tr>
                  <td style="padding:6px 0;color:#6b7280">Role</td>
                  <td style="padding:6px 0;color:#111827">{role_label}</td>
                </tr>
              </table>
            </div>

            <p style="color:#d97706;font-size:13px;margin-bottom:20px">
              ⚠️ Please change your password immediately after your first login.
            </p>

            <a href="{base_url}/login"
               style="display:inline-block;background:#10b981;color:white;padding:12px 28px;
                      text-decoration:none;border-radius:8px;font-weight:bold;font-size:15px">
              Login to Smart Silo →
            </a>

            <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
            <p style="color:#9ca3af;font-size:12px;margin:0">
              Smart Silo Management System — do not reply to this email.
            </p>
          </div>
        </body></html>'''

        ok, err = _resend_send(
            api_key, from_email, [pending['email']],
            'Your Smart Silo Account is Approved', html)
        email_sent = ok
        if not ok:
            print(f'❌ Approval email failed: {err}')

    if email_sent:
        flash(f'✅ {pending["full_name"]} approved as {role}! '
              f'Login credentials sent to {pending["email"]}', 'success')
    else:
        flash(f'✅ {pending["full_name"]} approved as {role}. '
              f'Username: {username} | Temp password: {temp_pwd} '
              '(Email failed — share credentials manually)', 'warning')

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
            html = '''
            <html><body style="font-family:Arial,sans-serif;padding:20px">
              <div style="max-width:500px;margin:auto;background:#fff;border-radius:10px;
                          border-top:5px solid #ef4444;padding:28px">
                <h2 style="color:#ef4444;margin-top:0">Registration Update</h2>
                <p>Thank you for your interest in Smart Silo System.</p>
                <p>Unfortunately your registration request has been declined.</p>
                <p>Please contact the system administrator for more information.</p>
                <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
                <small style="color:#9ca3af">Smart Silo Management System</small>
              </div>
            </body></html>'''
            _resend_send(
                api_key, from_email, [pending['email']],
                'Smart Silo Registration Update', html)

        flash(f'❌ {pending["full_name"]} has been rejected.', 'warning')

    conn.close()
    return redirect(url_for('admin.admin_pending_users'))
