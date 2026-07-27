import os
from flask import Flask, jsonify, session, render_template
from flask_mail import Mail

from .config import Config

mail = Mail()


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

    # Initialise extensions
    mail.init_app(app)

    # Register all blueprints
    from .routes.auth         import auth_bp
    from .routes.dashboard    import dashboard_bp
    from .routes.silos        import silos_bp
    from .routes.farmers      import farmers_bp
    from .routes.transactions import transactions_bp
    from .routes.users        import users_bp
    from .routes.reports      import reports_bp
    from .routes.alerts       import alerts_bp
    from .routes.admin        import admin_bp
    from .routes.recycle_bin  import recycle_bin_bp
    from .routes.inspections  import inspections_bp

    for bp in (auth_bp, dashboard_bp, silos_bp, farmers_bp,
               transactions_bp, users_bp, reports_bp, alerts_bp,
               admin_bp, recycle_bin_bp, inspections_bp):
        app.register_blueprint(bp)

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

    @app.context_processor
    def inject_pending_count():
        if 'user_id' in session and session.get('role') == 'admin':
            from .database import get_db
            conn  = get_db()
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM pending_users WHERE status = 'pending'"
            ).fetchone()
            conn.close()
            return {'pending_count': count['c'] if count else 0}
        return {'pending_count': 0}

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('403.html', role=session.get('role', '')), 403

    from .database import init_db
    with app.app_context():
        init_db()

    return app
