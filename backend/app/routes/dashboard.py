from datetime import datetime

from flask import Blueprint, render_template, session

from app.database import get_db
from app.decorators import login_required
from app.utils import calculate_risk, check_and_send_alerts

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    check_and_send_alerts()
    conn = get_db()

    silos = conn.execute('''
        SELECT s.*,
               COALESCE(
                   (SELECT moisture FROM grain_batches
                    WHERE silo_id = s.id ORDER BY entry_date DESC LIMIT 1), 0
               ) AS moisture
        FROM silos s
        WHERE s.status = "active"
        ORDER BY s.silo_number
    ''').fetchall()

    silo_data    = []
    red = yellow = green = 0
    total_stock  = 0

    for silo in silos:
        batch = conn.execute(
            'SELECT entry_date FROM grain_batches '
            'WHERE silo_id = ? ORDER BY entry_date DESC LIMIT 1',
            (silo['id'],),
        ).fetchone()

        days = 0
        if batch:
            try:
                days = (datetime.now() -
                        datetime.strptime(batch['entry_date'], '%Y-%m-%d')).days
            except Exception:
                pass

        moisture = silo['moisture'] or 0
        colour, message = calculate_risk(moisture, days)

        if colour == 'red':    red    += 1
        elif colour == 'yellow': yellow += 1
        elif colour == 'green':  green  += 1
        total_stock += silo['current_stock_kg'] or 0

        silo_data.append({
            'id':        silo['id'],
            'number':    silo['silo_number'],
            'location':  silo['location'] or '-',
            'grain_type': silo['grain_type'] or 'Empty',
            'stock':     silo['current_stock_kg'] or 0,
            'capacity':  silo['capacity_kg'] or 0,
            'moisture':  round(moisture, 1) if moisture else '-',
            'color':     colour,
            'message':   message,
        })

    recycle_count = (
        conn.execute(
            "SELECT COUNT(*) AS c FROM silos WHERE status = 'deleted'"
        ).fetchone()['c']
    )
    conn.close()

    return render_template(
        'dashboard.html',
        silos=silo_data,
        total_silos=len(silo_data),
        total_stock=round(total_stock / 1000, 1),
        red_count=red,
        yellow_count=yellow,
        green_count=green,
        username=session['username'],
        role=session['role'],
        recycle_count=recycle_count,
    )
