"""
Route decorators: login_required + role-based access control.

Role hierarchy (highest → lowest privilege):
    admin           — full access, system management
    silo_manager    — operational control, reports, farmers, stock
    silo_attendant  — field worker: grain intake + inspections only
    board_director  — read-only: dashboard, reports, analytics, transactions
    staff           — general: add grain, inspections, view farmers
"""
from functools import wraps
from flask import session, redirect, url_for, abort


# ── Privilege groups ───────────────────────────────────────────────────────────

ADMIN            = {'admin'}
MANAGER_UP       = {'admin', 'silo_manager'}
OPERATIONAL      = {'admin', 'silo_manager', 'silo_attendant', 'staff'}
REPORTERS        = {'admin', 'silo_manager', 'board_director'}
CAN_ADD_GRAIN    = {'admin', 'silo_manager', 'silo_attendant', 'staff'}
CAN_REMOVE_STOCK = {'admin', 'silo_manager'}
CAN_INSPECT      = {'admin', 'silo_manager', 'silo_attendant', 'staff'}
CAN_SEE_FARMERS  = {'admin', 'silo_manager', 'silo_attendant', 'staff'}
CAN_EDIT_FARMERS = {'admin', 'silo_manager'}
CAN_SEE_TX       = {'admin', 'silo_manager', 'board_director'}
ALL_ROLES        = {'admin', 'silo_manager', 'silo_attendant', 'board_director', 'staff'}


# ── Base decorator ─────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def _role_guard(allowed_roles: set):
    """Return a decorator that restricts access to the given role set."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if session.get('role') not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Named decorators (use these in routes) ─────────────────────────────────────

def admin_required(f):
    """Admin only."""
    return _role_guard(ADMIN)(f)

def manager_required(f):
    """Admin or Silo Manager."""
    return _role_guard(MANAGER_UP)(f)

def reporter_required(f):
    """Roles that can view reports/analytics/exports: admin, manager, board_director."""
    return _role_guard(REPORTERS)(f)

def can_add_grain(f):
    """Roles that can add grain: admin, manager, attendant, staff."""
    return _role_guard(CAN_ADD_GRAIN)(f)

def can_remove_stock(f):
    """Roles that can remove stock: admin, manager."""
    return _role_guard(CAN_REMOVE_STOCK)(f)

def can_inspect(f):
    """Roles that can record/view inspections: admin, manager, attendant, staff."""
    return _role_guard(CAN_INSPECT)(f)

def can_see_farmers(f):
    """Roles that can view farmers: admin, manager, attendant, staff."""
    return _role_guard(CAN_SEE_FARMERS)(f)

def can_edit_farmers(f):
    """Roles that can add/delete farmers: admin, manager."""
    return _role_guard(CAN_EDIT_FARMERS)(f)

def can_see_transactions(f):
    """Roles that can view transactions: admin, manager, board_director."""
    return _role_guard(CAN_SEE_TX)(f)
