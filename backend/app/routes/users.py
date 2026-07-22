from flask import Blueprint, render_template, request, session, jsonify

from app.database import get_db
from app.decorators import login_required, admin_required
from app.utils import is_strong_password, hash_password

users_bp = Blueprint('users', __name__)


@users_bp.route('/users')
@login_required
@admin_required
def users():
    conn = get_db()
    user_list = conn.execute(
        'SELECT id, username, email, role, full_name, created_at FROM users'
    ).fetchall()
    conn.close()
    return render_template('users.html', users=user_list)


@users_bp.route('/add_user', methods=['POST'])
@login_required
@admin_required
def add_user():
    import sqlite3
    data = request.get_json()
    ok, msg = is_strong_password(data['password'])
    if not ok:
        return jsonify({'success': False, 'error': msg}), 400

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password, email, role, full_name) '
            'VALUES (?, ?, ?, ?, ?)',
            (data['username'], hash_password(data['password']),
             data.get('email', ''), data['role'], data.get('full_name', '')),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'Username already exists'}), 400
    conn.close()
    return jsonify({'success': True})


@users_bp.route('/delete_user/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'success': False, 'error': 'User not found'}), 404
    if user_id == session['user_id']:
        conn.close()
        return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 403
    if user['role'] == 'admin':
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin'"
        ).fetchone()['c']
        if cnt <= 1:
            conn.close()
            return jsonify({'success': False,
                            'error': 'Cannot delete last admin'}), 403
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@users_bp.route('/delete_users', methods=['DELETE'])
@login_required
@admin_required
def delete_users():
    data     = request.get_json()
    user_ids = data.get('user_ids', [])
    if not user_ids:
        return jsonify({'success': False, 'error': 'No user IDs provided'}), 400

    conn    = get_db()
    deleted = 0
    errors  = []

    for uid in user_ids:
        user = conn.execute(
            'SELECT * FROM users WHERE id = ?', (uid,)
        ).fetchone()
        if not user:
            errors.append(f'User ID {uid} not found'); continue
        if uid == session['user_id']:
            errors.append(f'Cannot delete own account (ID: {uid})'); continue
        if user['role'] == 'admin':
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role = 'admin'"
            ).fetchone()['c']
            if cnt <= 1:
                errors.append(f'Cannot delete last admin (ID: {uid})'); continue
        conn.execute('DELETE FROM users WHERE id = ?', (uid,))
        deleted += 1

    conn.commit()
    conn.close()
    msg = f'Deleted {deleted} user(s).'
    if errors:
        msg += ' Errors: ' + ', '.join(errors)
    return jsonify({'success': True, 'message': msg, 'errors': errors})
