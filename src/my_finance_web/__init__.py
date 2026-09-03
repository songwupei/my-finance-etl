"""my_finance_web — Flask web service for financial data visualization."""


def create_app():
    """Create and configure the Flask application."""
    from flask import Flask

    from .config import _proj_dir

    app = Flask(
        __name__,
        template_folder=str(_proj_dir / "templates"),
        static_folder=str(_proj_dir / "static"),
    )

    from .routes import (tree_bp, treasury_bp, report_bp, geo_bp,
                         panreg_bp, penetration_bp)

    app.register_blueprint(tree_bp)
    app.register_blueprint(treasury_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(geo_bp)
    app.register_blueprint(panreg_bp)
    app.register_blueprint(penetration_bp)

    from .dashboard import build_dashboard

    build_dashboard(app)

    return app


def main():
    """CLI entry point for my-finance-web."""
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5001)
