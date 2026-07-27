"""
Inspections blueprint — daily/weekly silo condition recording.

Routes:
    GET  /inspection                    → form to record a new inspection
    POST /save-inspection               → save the inspection to DB
    GET  /inspection-history/<silo_id>  → view all inspections for a silo
    POST /delete-inspection/<id>        → admin-only hard delete
"""
from datetime import date

from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash)

from app.database import get_db
from app.decorators import login_required, admin_required, can_inspect

inspections_bp = Blueprint('inspections', __name__)


# ── helpers ────────────────────────────────────────────────────────────────────

def _int_checkbox(field: str) -> int:
    """Return 1 if checkbox was ticked, else 0."""
    return 1 if request.form.get(field) else 0


def _validate_inspection(form) -> list:
    errors = []
    if not form.get('silo_id'):
        errors.append('Please select a silo.')
    if not form.get('inspection_date'):
        errors.append('Inspection date is required.')
    moisture = form.get('moisture', '').strip()
    if moisture:
        try:
            v = float(moisture)
            if not (0 <= v <= 100):
                errors.append('Moisture must be between 0 and 100 %.')
        except ValueError:
            errors.append('Moisture must be a number.')
    temperature = form.get('temperature', '').strip()
    if temperature:
        try:
            v = float(temperature)
            if not (-10 <= v <= 80):
                errors.append('Temperature must be between -10 and 80 °C.')
        except ValueError:
            errors.append('Temperature must be a number.')
    stock_kg = form.get('stock_kg', '').strip()
    if stock_kg:
        try:
            v = float(stock_kg)
            if v < 0:
                errors.append('Stock cannot be negative.')
        except ValueError:
            errors.append('Stock must be a number.')
    return errors


def _get_silos(conn):
    return conn.execute(
        "SELECT id, silo_number, location FROM silos "
        "WHERE status = 'active' ORDER BY silo_number"
    ).fetchall()


# ── routes ─────────────────────────────────────────────────────────────────────

@inspections_bp.route('/inspection')
@login_required
@can_inspect
def inspection_form():
    conn  = get_db()
    silos = _get_silos(conn)
    conn.close()

    preselected = request.args.get('silo_id', '')
    today       = date.today().isoformat()

    return render_template(
        'inspections.html',
        silos=silos,
        preselected=preselected,
        today=today,
        username=session['username'],
        role=session['role'],
    )


@inspections_bp.route('/save-inspection', methods=['POST'])
@login_required
@can_inspect
def save_inspection():
    form   = request.form
    errors = _validate_inspection(form)

    if errors:
        conn  = get_db()
        silos = _get_silos(conn)
        conn.close()
        return render_template(
            'inspections.html',
            silos=silos,
            errors=errors,
            form_data=form,
            preselected=form.get('silo_id', ''),
            today=date.today().isoformat(),
            username=session['username'],
            role=session['role'],
        ), 422

    silo_id         = int(form['silo_id'])
    inspection_date = form['inspection_date']
    temperature     = float(form['temperature']) if form.get('temperature') else None
    moisture        = float(form['moisture'])    if form.get('moisture')    else None
    stock_kg        = float(form['stock_kg'])    if form.get('stock_kg')    else None
    pest_present    = _int_checkbox('pest_present')
    aeration_done   = _int_checkbox('aeration_done')
    odour_normal    = _int_checkbox('odour_normal')
    notes           = form.get('notes', '').strip()

    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO inspections
               (silo_id, inspection_date, temperature, moisture,
                pest_present, aeration_done, odour_normal,
                stock_kg, notes, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (silo_id, inspection_date, temperature, moisture,
             pest_present, aeration_done, odour_normal,
             stock_kg, notes, session['user_id']),
        )
        conn.commit()
    except Exception as exc:
        conn.close()
        conn  = get_db()
        silos = _get_silos(conn)
        conn.close()
        return render_template(
            'inspections.html',
            silos=silos,
            errors=[f'Database error: {exc}'],
            form_data=form,
            preselected=form.get('silo_id', ''),
            today=date.today().isoformat(),
            username=session['username'],
            role=session['role'],
        ), 500
    conn.close()

    flash('✅ Inspection saved successfully.', 'success')
    return redirect(url_for('inspections.inspection_history', silo_id=silo_id))


@inspections_bp.route('/inspection-history/<int:silo_id>')
@login_required
@can_inspect
def inspection_history(silo_id):
    conn = get_db()

    silo = conn.execute(
        "SELECT id, silo_number, location, grain_type FROM silos WHERE id = ?",
        (silo_id,),
    ).fetchone()

    if not silo:
        conn.close()
        flash('Silo not found.', 'error')
        return redirect(url_for('dashboard.dashboard'))

    records = conn.execute(
        '''SELECT i.*,
                  u.username AS inspector_name
           FROM inspections i
           LEFT JOIN users u ON u.id = i.created_by
           WHERE i.silo_id = ?
           ORDER BY i.inspection_date DESC, i.created_at DESC''',
        (silo_id,),
    ).fetchall()

    silos = _get_silos(conn)
    conn.close()

    return render_template(
        'inspection_history.html',
        silo=silo,
        records=records,
        silos=silos,
        username=session['username'],
        role=session['role'],
    )


@inspections_bp.route('/delete-inspection/<int:inspection_id>', methods=['POST'])
@login_required
@admin_required
def delete_inspection(inspection_id):
    conn = get_db()
    row  = conn.execute(
        'SELECT silo_id FROM inspections WHERE id = ?', (inspection_id,)
    ).fetchone()
    if row:
        conn.execute('DELETE FROM inspections WHERE id = ?', (inspection_id,))
        conn.commit()
    conn.close()
    flash('Inspection record deleted.', 'success')
    silo_id = row['silo_id'] if row else None
    if silo_id:
        return redirect(url_for('inspections.inspection_history', silo_id=silo_id))
    return redirect(url_for('dashboard.dashboard'))
