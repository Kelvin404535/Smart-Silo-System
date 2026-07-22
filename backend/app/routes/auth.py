import secrets

from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, current_app)
from datetime import datetime, timedelta

from app.database import get_db
from app.utils import (is_strong_password, hash_password, verify_password,
                       check_account_lockout, record_failed_attempt,
                       reset_failed_attempts, get_base_url, _sendgrid_send)
from app.decorators import login_required, admin_required

auth_bp = Blueprint('auth', __name__)


# ── Index redirect ────────────────────────────────────────────────────────────

@auth_bp.route('/')
def index():
    return redirect(url_for('auth.login'))


# ── Login / Logout ────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']

        is_locked, lock_msg, lock_until = check_account_lockout(email)
        if is_locked:
            return render_template(
                'login.html',
                error=lock_msg,
                lock_until=lock_until.isoformat() if lock_until else None,
            )

        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()
        conn.close()

        if user and verify_password(password, user['password']):
            reset_failed_attempts(email)
            session.permanent = True
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['email']    = user['email']
            session['role']     = user['role']
            return redirect(url_for('dashboard.dashboard'))
        else:
            record_failed_attempt(email)
            return render_template('login.html', error='Invalid email or password')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name          = request.form.get('full_name', '').strip()
        email              = request.form.get('email', '').strip()
        phone              = request.form.get('phone', '').strip()
        preferred_username = request.form.get('preferred_username', '').strip()
        role               = request.form.get('role', 'staff')

        errors = []
        if not full_name:
            errors.append('Full name is required')
        if not email or '@' not in email:
            errors.append('Valid email address is required')
        if len(preferred_username) < 3:
            errors.append('Preferred username must be at least 3 characters')

        if not errors:
            conn = get_db()
            if conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
                errors.append('Email already registered.')
            if conn.execute('SELECT id FROM users WHERE username = ?',
                            (preferred_username,)).fetchone():
                errors.append('Username already taken.')
            conn.close()

        if errors:
            return render_template('register.html',
                                   errors=errors, form_data=request.form)

        conn = get_db()
        conn.execute(
            "INSERT INTO pending_users "
            "(full_name, email, phone, preferred_username, requested_role, status) "
            "VALUES (?, ?, ?, ?, ?, 'pending')",
            (full_name, email, phone, preferred_username, role),
        )
        conn.commit()
        conn.close()
        return render_template('registration_pending.html', name=full_name)

    return render_template('register.html', form_data={})


# ── Forgot / Reset password ───────────────────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        conn  = get_db()
        user  = conn.execute(
            'SELECT * FROM users WHERE email = ?', (email,)
        ).fetchone()

        if user:
            token      = secrets.token_urlsafe(32)
            expiry     = datetime.now() + timedelta(hours=1)
            conn.execute('DELETE FROM password_resets WHERE email = ?', (email,))
            conn.execute(
                'INSERT INTO password_resets (email, token, expiry) VALUES (?, ?, ?)',
                (email, token, expiry),
            )
            conn.commit()
            conn.close()

            reset_link  = f'{get_base_url()}/reset-password/{token}'
            api_key     = current_app.config.get('SENDGRID_API_KEY', '')
            from_email  = current_app.config.get('MAIL_DEFAULT_SENDER', '')

            if api_key and from_email:
                html = (
                    f'<h2>Password Reset</h2>'
                    f'<p>Click the link below to reset your password (expires in 1 hour):</p>'
                    f'<p><a href="{reset_link}">{reset_link}</a></p>'
                )
                ok, err = _sendgrid_send(
                    api_key, from_email, [email],
                    'Password Reset - Smart Silo System', html)
                if not ok:
                    print(f'Password reset email error: {err}')
            else:
                print(f'Password reset link (email not configured): {reset_link}')
        else:
            conn.close()

        # Always show the same message to avoid user enumeration
        return render_template('forgot_password.html',
                               message='If that email exists, a reset link will be sent.')

    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn  = get_db()
    reset = conn.execute(
        "SELECT * FROM password_resets WHERE token = ? AND expiry > datetime('now')",
        (token,),
    ).fetchone()

    if not reset:
        conn.close()
        return render_template('reset_password.html',
                               error='Invalid or expired link.')

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if password != confirm:
            conn.close()
            return render_template('reset_password.html',
                                   error='Passwords do not match.')
        ok, msg = is_strong_password(password)
        if not ok:
            conn.close()
            return render_template('reset_password.html', error=msg)

        conn.execute('UPDATE users SET password = ? WHERE email = ?',
                     (hash_password(password), reset['email']))
        conn.execute('DELETE FROM password_resets WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        return redirect(url_for('auth.login'))

    conn.close()
    return render_template('reset_password.html')


# ── Change password ───────────────────────────────────────────────────────────

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current  = request.form.get('current_password', '')
        new_pwd  = request.form.get('new_password', '')
        confirm  = request.form.get('confirm_password', '')

        if new_pwd != confirm:
            return render_template('change_password.html',
                                   error='Passwords do not match')
        ok, msg = is_strong_password(new_pwd)
        if not ok:
            return render_template('change_password.html', error=msg)

        conn = get_db()
        user = conn.execute(
            'SELECT password FROM users WHERE id = ?', (session['user_id'],)
        ).fetchone()

        if not verify_password(current, user['password']):
            conn.close()
            return render_template('change_password.html',
                                   error='Current password is incorrect')

        conn.execute('UPDATE users SET password = ? WHERE id = ?',
                     (hash_password(new_pwd), session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard.dashboard'))

    return render_template('change_password.html')
