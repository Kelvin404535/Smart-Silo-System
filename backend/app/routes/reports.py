import io
import csv
from datetime import datetime

from flask import Blueprint, render_template, send_file

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from app.database import get_db
from app.decorators import login_required
from app.utils import calculate_risk

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/reports')
@login_required
def reports():
    return render_template('reports.html')


@reports_bp.route('/analytics')
@login_required
def analytics():
    conn   = get_db()
    trends = conn.execute(
        "SELECT date(entry_date) AS date, AVG(moisture) AS avg_moisture "
        "FROM grain_batches "
        "WHERE entry_date > date('now', '-30 days') "
        "GROUP BY date(entry_date) ORDER BY date"
    ).fetchall()

    silos       = conn.execute(
        "SELECT id FROM silos WHERE status = 'active'"
    ).fetchall()
    risk_counts = {'red': 0, 'yellow': 0, 'green': 0, 'gray': 0}

    for silo in silos:
        batch = conn.execute(
            'SELECT moisture, entry_date FROM grain_batches '
            'WHERE silo_id = ? ORDER BY entry_date DESC LIMIT 1',
            (silo['id'],),
        ).fetchone()
        if batch:
            try:
                days = (
                    datetime.now() -
                    datetime.strptime(batch['entry_date'], '%Y-%m-%d')
                ).days
                colour, _ = calculate_risk(batch['moisture'], days)
                risk_counts[colour] = risk_counts.get(colour, 0) + 1
            except Exception:
                risk_counts['gray'] += 1
        else:
            risk_counts['gray'] += 1

    conn.close()
    return render_template('analytics.html',
                           trends=trends, risk_counts=risk_counts)


@reports_bp.route('/inventory-flow')
@login_required
def inventory_flow():
    conn = get_db()
    totals = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN transaction_type = 'IN' "
        "THEN quantity_kg ELSE 0 END), 0) AS incoming, "
        "COALESCE(SUM(CASE WHEN transaction_type = 'OUT' "
        "THEN quantity_kg ELSE 0 END), 0) AS outgoing "
        "FROM transactions"
    ).fetchone()
    stock = conn.execute(
        "SELECT COALESCE(SUM(current_stock_kg), 0) AS current_stock, "
        "COALESCE(SUM(capacity_kg), 0) AS capacity "
        "FROM silos WHERE status = 'active'"
    ).fetchone()
    by_grain = conn.execute(
        "SELECT COALESCE(grain_type, 'Unspecified') AS grain_type, "
        "COALESCE(SUM(current_stock_kg), 0) AS stock "
        "FROM silos WHERE status = 'active' "
        "GROUP BY COALESCE(grain_type, 'Unspecified') "
        "ORDER BY stock DESC"
    ).fetchall()
    recent = conn.execute(
        "SELECT t.transaction_date, t.transaction_type, t.quantity_kg, "
        "s.silo_number FROM transactions t "
        "LEFT JOIN silos s ON s.id = t.silo_id "
        "ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return render_template('inventory_flow.html', totals=totals, stock=stock,
                           by_grain=by_grain, recent=recent)


@reports_bp.route('/quality-alerts')
@login_required
def quality_alerts():
    conn = get_db()
    silos = conn.execute(
        "SELECT s.silo_number, s.location, s.grain_type, s.current_stock_kg, "
        "gb.moisture, gb.entry_date "
        "FROM silos s LEFT JOIN grain_batches gb ON gb.id = ("
        "SELECT id FROM grain_batches WHERE silo_id = s.id "
        "ORDER BY entry_date DESC LIMIT 1) "
        "WHERE s.status = 'active' ORDER BY s.silo_number"
    ).fetchall()
    alerts = conn.execute(
        "SELECT a.message, a.severity, a.created_at, s.silo_number "
        "FROM alerts a LEFT JOIN silos s ON s.id = a.silo_id "
        "WHERE a.is_read = 0 ORDER BY a.created_at DESC LIMIT 10"
    ).fetchall()
    conn.close()

    quality_rows = []
    for silo in silos:
        moisture = silo['moisture']
        if moisture is None:
            status = 'No reading'
        elif moisture > 14:
            status = 'Critical'
        elif moisture > 12.5:
            status = 'Warning'
        else:
            status = 'Normal'
        quality_rows.append({**dict(silo), 'status': status})

    return render_template('quality_alerts.html', silos=quality_rows,
                           alerts=alerts)


@reports_bp.route('/export_pdf')
@login_required
def export_pdf():
    conn  = get_db()
    silos = conn.execute(
        "SELECT * FROM silos WHERE status = 'active'"
    ).fetchall()
    conn.close()

    buf  = io.BytesIO()
    doc  = SimpleDocTemplate(buf, pagesize=letter)
    styl = getSampleStyleSheet()

    rows = [['Silo', 'Location', 'Grain Type', 'Stock (kg)', 'Capacity (kg)']]
    for s in silos:
        rows.append([
            s['silo_number'],
            s['location'] or '-',
            s['grain_type'] or '-',
            str(s['current_stock_kg'] or 0),
            str(s['capacity_kg'] or 0),
        ])

    tbl = Table(rows)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1,  0), colors.grey),
        ('TEXTCOLOR',   (0, 0), (-1,  0), colors.whitesmoke),
        ('ALIGN',       (0, 0), (-1, -1), 'CENTER'),
        ('GRID',        (0, 0), (-1, -1), 1, colors.black),
    ]))

    doc.build([Paragraph('Silo Management Report', styl['Title']), tbl])
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='silo_report.pdf',
                     mimetype='application/pdf')


@reports_bp.route('/export_csv')
@login_required
def export_csv():
    conn  = get_db()
    silos = conn.execute(
        "SELECT * FROM silos WHERE status = 'active'"
    ).fetchall()
    conn.close()

    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(['Silo Number', 'Location', 'Grain Type',
                'Stock (kg)', 'Capacity (kg)'])
    for s in silos:
        w.writerow([s['silo_number'], s['location'] or '',
                    s['grain_type'] or '',
                    s['current_stock_kg'] or 0, s['capacity_kg'] or 0])
    out.seek(0)
    return send_file(
        io.BytesIO(out.getvalue().encode()),
        as_attachment=True,
        download_name='silos.csv',
        mimetype='text/csv',
    )
