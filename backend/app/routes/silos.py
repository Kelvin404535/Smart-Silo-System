from datetime import datetime

from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, jsonify)

from app.database import get_db
from app.decorators import login_required, admin_required

silos_bp = Blueprint('silos', __name__)


@silos_bp.route('/silo/<int:silo_id>', methods=['GET', 'POST'])
@login_required
def edit_silo(silo_id):
    if request.method == 'POST':
        grain_type  = request.form['grain_type']
        moisture    = float(request.form['moisture'])
        quantity    = float(request.form['quantity'])
        entry_date  = request.form['entry_date']
        farmer_id   = request.form.get('farmer_id') or None

        batch_number = (
            f"BATCH-{silo_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        conn = get_db()
        conn.execute(
            'UPDATE silos SET grain_type = ?, '
            'current_stock_kg = current_stock_kg + ? WHERE id = ?',
            (grain_type, quantity, silo_id),
        )
        conn.execute(
            'INSERT INTO grain_batches '
            '(batch_number, silo_id, grain_type, quantity_kg, moisture, entry_date, farmer_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (batch_number, silo_id, grain_type, quantity, moisture, entry_date, farmer_id),
        )
        conn.execute(
            'INSERT INTO transactions '
            '(silo_id, batch_id, transaction_type, quantity_kg, transaction_date, created_by) '
            'SELECT ?, id, "IN", ?, ?, ? FROM grain_batches WHERE batch_number = ?',
            (silo_id, quantity, entry_date, session['user_id'], batch_number),
        )
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard.dashboard'))

    conn = get_db()
    silo    = conn.execute('SELECT * FROM silos WHERE id = ?', (silo_id,)).fetchone()
    farmers = conn.execute('SELECT id, name FROM farmers ORDER BY name').fetchall()
    conn.close()
    return render_template('edit_silo.html', silo=silo, farmers=farmers)


@silos_bp.route('/add_silo', methods=['POST'])
@login_required
@admin_required
def add_silo():
    data = request.get_json() or {}
    silo_number = (data.get('silo_number') or '').strip()
    location = (data.get('location') or '').strip()
    capacity = data.get('capacity_kg')

    if not silo_number:
        return jsonify({'success': False, 'error': 'Silo number is required.'}), 400
    if not location:
        return jsonify({'success': False, 'error': 'Location is required.'}), 400
    try:
        capacity = float(capacity)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Capacity must be a valid number.'}), 400
    if capacity <= 0:
        return jsonify({'success': False, 'error': 'Capacity must be greater than zero.'}), 400

    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO silos (silo_number, location, capacity_kg) VALUES (?, ?, ?)',
            (silo_number, location, capacity),
        )
        conn.commit()
    except Exception as exc:
        conn.close()
        return jsonify({'success': False, 'error': 'Unable to add silo. It may already exist.'}), 400
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return jsonify({'success': True})


@silos_bp.route('/remove_silo/<int:silo_id>', methods=['DELETE'])
@login_required
@admin_required
def remove_silo(silo_id):
    conn = get_db()
    conn.execute("UPDATE silos SET status = 'inactive' WHERE id = ?", (silo_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@silos_bp.route('/remove_stock', methods=['POST'])
@login_required
def remove_stock():
    data = request.get_json()
    conn = get_db()
    silo = conn.execute(
        'SELECT current_stock_kg FROM silos WHERE id = ?', (data['silo_id'],)
    ).fetchone()

    if silo['current_stock_kg'] < data['quantity']:
        conn.close()
        return jsonify({'success': False, 'error': 'Insufficient stock'}), 400

    conn.execute(
        'UPDATE silos SET current_stock_kg = current_stock_kg - ? WHERE id = ?',
        (data['quantity'], data['silo_id']),
    )
    conn.execute(
        "INSERT INTO transactions "
        "(silo_id, transaction_type, quantity_kg, transaction_date, notes, created_by) "
        "VALUES (?, 'OUT', ?, date('now'), ?, ?)",
        (data['silo_id'], data['quantity'],
         data.get('reason', ''), session['user_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})
