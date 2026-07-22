from flask import Blueprint, render_template, request, jsonify

from app.database import get_db
from app.decorators import login_required, admin_required

transactions_bp = Blueprint('transactions', __name__)


@transactions_bp.route('/transactions')
@login_required
def transactions():
    conn = get_db()
    tx_list = conn.execute(
        'SELECT t.*, s.silo_number, gb.batch_number, '
        '       u.username AS created_by_name '
        'FROM transactions t '
        'JOIN silos s ON t.silo_id = s.id '
        'LEFT JOIN grain_batches gb ON t.batch_id = gb.id '
        'LEFT JOIN users u ON t.created_by = u.id '
        'ORDER BY t.created_at DESC LIMIT 100'
    ).fetchall()
    conn.close()
    return render_template('transactions.html', transactions=tx_list)


@transactions_bp.route('/clear_transactions', methods=['DELETE'])
@login_required
@admin_required
def clear_transactions():
    data = request.get_json()
    ids  = data.get('transaction_ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'No IDs provided'}), 400

    conn         = get_db()
    placeholders = ','.join(['?'] * len(ids))
    conn.execute(f'DELETE FROM transactions WHERE id IN ({placeholders})', ids)
    deleted = conn.total_changes
    conn.commit()
    conn.close()
    return jsonify({'success': True,
                    'message': f'Deleted {deleted} transaction(s)'})


@transactions_bp.route('/clear_all_transactions', methods=['DELETE'])
@login_required
@admin_required
def clear_all_transactions():
    conn  = get_db()
    total = conn.execute(
        'SELECT COUNT(*) AS c FROM transactions'
    ).fetchone()['c']
    conn.execute('DELETE FROM transactions')
    conn.commit()
    conn.close()
    return jsonify({'success': True,
                    'message': f'Deleted all {total} transactions'})
