from flask import Blueprint, render_template, request, session, jsonify

from app.database import get_db
from app.decorators import login_required, admin_required

farmers_bp = Blueprint('farmers', __name__)


@farmers_bp.route('/farmers')
@login_required
def farmers():
    conn = get_db()
    farmer_list = conn.execute(
        'SELECT f.*, COUNT(gb.id) AS delivery_count '
        'FROM farmers f '
        'LEFT JOIN grain_batches gb ON f.id = gb.farmer_id '
        'GROUP BY f.id ORDER BY f.name'
    ).fetchall()
    conn.close()
    return render_template('farmers.html',
                           farmers=farmer_list, role=session['role'])


@farmers_bp.route('/add_farmer', methods=['POST'])
@login_required
def add_farmer():
    data = request.get_json()
    conn = get_db()
    conn.execute(
        'INSERT INTO farmers (farmer_number, name, phone, email, location) '
        'VALUES (?, ?, ?, ?, ?)',
        (data['farmer_number'], data['name'], data['phone'],
         data.get('email', ''), data.get('location', '')),
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@farmers_bp.route('/delete_farmer/<int:farmer_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_farmer(farmer_id):
    conn = get_db()
    farmer = conn.execute(
        'SELECT * FROM farmers WHERE id = ?', (farmer_id,)
    ).fetchone()
    if not farmer:
        conn.close()
        return jsonify({'success': False, 'error': 'Farmer not found'}), 404

    batches = conn.execute(
        'SELECT COUNT(*) AS c FROM grain_batches WHERE farmer_id = ?',
        (farmer_id,),
    ).fetchone()
    if batches['c'] > 0:
        conn.close()
        return jsonify({
            'success': False,
            'error': f"Cannot delete farmer with {batches['c']} grain batch(es)",
        }), 400

    conn.execute('DELETE FROM farmers WHERE id = ?', (farmer_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Farmer deleted successfully'})


@farmers_bp.route('/delete_farmers', methods=['DELETE'])
@login_required
@admin_required
def delete_farmers():
    data       = request.get_json()
    farmer_ids = data.get('farmer_ids', [])
    if not farmer_ids:
        return jsonify({'success': False, 'error': 'No farmer IDs provided'}), 400

    conn    = get_db()
    deleted = 0
    errors  = []

    for fid in farmer_ids:
        farmer = conn.execute(
            'SELECT * FROM farmers WHERE id = ?', (fid,)
        ).fetchone()
        if not farmer:
            errors.append(f'Farmer ID {fid} not found')
            continue
        batches = conn.execute(
            'SELECT COUNT(*) AS c FROM grain_batches WHERE farmer_id = ?', (fid,)
        ).fetchone()
        if batches['c'] > 0:
            errors.append(f"'{farmer['name']}' has {batches['c']} batch(es)")
            continue
        conn.execute('DELETE FROM farmers WHERE id = ?', (fid,))
        deleted += 1

    conn.commit()
    conn.close()

    msg = f'Deleted {deleted} farmer(s).'
    if errors:
        msg += ' Errors: ' + ', '.join(errors)
    return jsonify({'success': True, 'message': msg, 'errors': errors})
