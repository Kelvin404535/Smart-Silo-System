import os
from flask import Flask, jsonify, session

from app.config import Config


def create_app():
    """Application factory."""
    app_dir      = os.path.dirname(__file__)
    backend_dir  = os.path.dirname(app_dir)
    base_dir     = os.path.dirname(backend_dir)
    template_dir = os.path.join(base_dir, 'frontend', 'templates')
    static_dir   = os.path.join(base_dir, 'frontend', 'static')

    app = Flask(__name__,
                template_folder=template_dir,
                static_folder=static_dir)

    app.config.from_object(Config)

    @app.route('/health')
    def health():
        return jsonify(status='ok')

    # Register all blueprints
    from app.routes.auth         import auth_bp
    from app.routes.dashboard    import dashboard_bp
    from app.routes.silos        import silos_bp
    from app.routes.farmers      import farmers_bp
    from app.routes.transactions import transactions_bp
    from app.routes.users        import users_bp
    from app.routes.reports      import reports_bp
    from app.routes.alerts       import alerts_bp
    from app.routes.admin        import admin_bp
    from app.routes.recycle_bin  import recycle_bin_bp

    for bp in (auth_bp, dashboard_bp, silos_bp, farmers_bp,
               transactions_bp, users_bp, reports_bp, alerts_bp,
               admin_bp, recycle_bin_bp):
        app.register_blueprint(bp)

    # Verification / static file routes
    from flask import send_file as _send_file

    @app.route('/google8d9f89a8b245fc66.html')
    def google_verify():
        return _send_file(
            os.path.join(os.path.dirname(base_dir), 'google8d9f89a8b245fc66.html')
        )

    @app.route('/sitemap.xml')
    def sitemap():
        return _send_file(
            os.path.join(base_dir, 'frontend', 'templates', 'sitemap.xml')
        )

    # Context processor: inject pending_count into every template
    @app.context_processor
    def inject_pending_count():
        if 'user_id' in session and session.get('role') == 'admin':
            from app.database import get_db
            conn  = get_db()
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM pending_users WHERE status = 'pending'"
            ).fetchone()
            conn.close()
            return {'pending_count': count['c'] if count else 0}
        return {'pending_count': 0}

    # Initialise DB on first run
    from app.database import init_db
    with app.app_context():
        init_db()

    return app
