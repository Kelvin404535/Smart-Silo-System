from flask import Blueprint, render_template, session, jsonify

from app.database import get_db
from app.decorators import login_required, admin_required

recycle_bin_bp = Blueprint('recycle_bin', __name__)


@recycle_bin_bp.route('/recycle-bin')
@login_required
@admin_required
def recycle_bin():
    conn = get_db()
    silos = conn.execute(
        'SELECT s.*, u.username AS deleted_by_name '
        'FROM silos s '
        'LEFT JOIN users u ON s.deleted_by = u.id '
        "WHERE s.status = 'deleted' "
        'ORDER BY s.deleted_at DESC'
    ).fetchall()
    conn.close()
    return render_template('recycle_bin.html', silos=silos)


@recycle_bin_bp.route('/silo/<int:silo_id>/delete', methods=['POST'])
@login_required
@admin_required
def soft_delete_silo(silo_id):
    conn = get_db()
    silo = conn.execute(
        "SELECT * FROM silos WHERE id = ? AND status = 'active'", (silo_id,)
    ).fetchone()
    if not silo:
        conn.close()
        return jsonify({'success': False, 'error': 'Silo not found'}), 404
    if silo['current_stock_kg'] > 0:
        conn.close()
        return jsonify({'success': False,
                        'error': 'Cannot delete silo with stock.'}), 400
    conn.execute(
        "UPDATE silos SET status='deleted', deleted_at=datetime('now'), "
        'deleted_by=? WHERE id=?',
        (session['user_id'], silo_id),
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Silo moved to recycle bin'})


@recycle_bin_bp.route('/silo/<int:silo_id>/restore', methods=['POST'])
@login_required
@admin_required
def restore_silo(silo_id):
    conn = get_db()
    silo = conn.execute(
        "SELECT * FROM silos WHERE id = ? AND status = 'deleted'", (silo_id,)
    ).fetchone()
    if not silo:
        conn.close()
        return jsonify({'success': False,
                        'error': 'Silo not found in recycle bin'}), 404
    conn.execute(
        "UPDATE silos SET status='active', deleted_at=NULL, "
        'deleted_by=NULL WHERE id=?',
        (silo_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Silo restored'})


@recycle_bin_bp.route('/silo/<int:silo_id>/permanent_delete', methods=['DELETE'])
@login_required
@admin_required
def permanent_delete_silo(silo_id):
    conn = get_db()
    silo = conn.execute(
        "SELECT * FROM silos WHERE id = ? AND status = 'deleted'", (silo_id,)
    ).fetchone()
    if not silo:
        conn.close()
        return jsonify({'success': False,
                        'error': 'Silo not found in recycle bin'}), 404
    for tbl in ('grain_batches', 'transactions', 'alerts'):
        conn.execute(f'DELETE FROM {tbl} WHERE silo_id = ?', (silo_id,))
    conn.execute('DELETE FROM silos WHERE id = ?', (silo_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Silo permanently deleted'})


@recycle_bin_bp.route('/recycle-bin/empty', methods=['DELETE'])
@login_required
@admin_required
def empty_recycle_bin():
    conn    = get_db()
    deleted = conn.execute(
        "SELECT id FROM silos WHERE status = 'deleted'"
    ).fetchall()
    for silo in deleted:
        for tbl in ('grain_batches', 'transactions', 'alerts'):
            conn.execute(f'DELETE FROM {tbl} WHERE silo_id = ?', (silo['id'],))
        conn.execute('DELETE FROM silos WHERE id = ?', (silo['id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True,
                    'message': f'Permanently deleted {len(deleted)} silos'})


@recycle_bin_bp.route('/recycle-bin/auto-delete', methods=['POST'])
@login_required
@admin_required
def auto_delete_old():
    conn = get_db()
    old  = conn.execute(
        "SELECT id FROM silos WHERE status = 'deleted' "
        "AND deleted_at < datetime('now', '-30 days')"
    ).fetchall()
    for silo in old:
        for tbl in ('grain_batches', 'transactions', 'alerts'):
            conn.execute(f'DELETE FROM {tbl} WHERE silo_id = ?', (silo['id'],))
        conn.execute('DELETE FROM silos WHERE id = ?', (silo['id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True,
                    'message': f'Auto-deleted {len(old)} old silos'})
